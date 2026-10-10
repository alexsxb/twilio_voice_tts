import asyncio
import logging
import re
from types import MappingProxyType
from homeassistant.config_entries import ConfigSubentry
import xml.etree.ElementTree as ET
import aiohttp
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PHONE = re.compile(r"^\+[1-9]\d{6,14}$")
SERVICE_SCHEMA = vol.Schema({
    vol.Required("message"): cv.string,
    vol.Optional("to"): cv.string,
    vol.Optional("entry_id"): cv.string,
    vol.Optional("subentry_id"): cv.string,
    vol.Optional("from_number"): cv.string,
    vol.Optional("voice"): cv.string,
    vol.Optional("language"): cv.string,
    vol.Optional("loop"): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
})

NOTIFY_SCHEMA = vol.Schema({
    vol.Required("message"): cv.string,
    vol.Optional("title"): cv.string,
    vol.Optional("target"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("data", default=dict): dict,
})

async def async_notify_call(hass: HomeAssistant, call: ServiceCall, entry_id=None, subentry_id=None):
    """Bridge Alarmo's notification payload to the existing call service."""
    payload = dict(call.data.get("data", {}))
    payload["message"] = call.data["message"]
    if entry_id is not None:
        payload["entry_id"] = entry_id
    if subentry_id is not None:
        payload["subentry_id"] = subentry_id
    # A notification title is accepted, but only the message is spoken.
    targets = call.data.get("target", [])
    if any(not PHONE.fullmatch(number) for number in targets):
        raise HomeAssistantError("Telefonnummern müssen im E.164-Format sein")
    if not targets:
        payload = SERVICE_SCHEMA(payload)
        await hass.services.async_call(DOMAIN, "call", payload, blocking=True,
                                       context=call.context)
        return
    payload = SERVICE_SCHEMA(payload)
    for number in targets:
        await hass.services.async_call(DOMAIN, "call", {**payload, "to": number},
                                       blocking=True, context=call.context)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def make_call(call: ServiceCall):
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("Twilio Voice TTS ist nicht konfiguriert")
        entry = next((item for item in entries if item.entry_id == call.data.get("entry_id")), None) if call.data.get("entry_id") else entries[0]
        if entry is None:
            raise HomeAssistantError("Twilio-Konfiguration nicht gefunden")
        settings = {**entry.data, **entry.options}
        subentry_id = call.data.get("subentry_id")
        recipient = entry.subentries.get(subentry_id) if subentry_id else next(iter(entry.subentries.values()), None)
        if subentry_id and recipient is None:
            raise HomeAssistantError("Empfänger nicht gefunden")
        if recipient:
            settings.update({key: value for key, value in recipient.data.items()
                             if key in ("to_number", "voice", "language", "loop")})
        to = call.data.get("to", settings.get("to_number", ""))
        sender = call.data.get("from_number", settings["from_number"])
        if not PHONE.fullmatch(to) or not PHONE.fullmatch(sender):
            raise HomeAssistantError("Telefonnummern müssen im E.164-Format sein")
        message = call.data["message"].strip()
        if not message or len(message) > 2000:
            raise HomeAssistantError("Text muss 1 bis 2000 Zeichen enthalten")
        voice = call.data.get("voice", settings["voice"])
        language = call.data.get("language", settings["language"])
        loop = call.data.get("loop", settings["loop"])
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", voice) or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?", language):
            raise HomeAssistantError("Ungültige Stimme oder Sprache")
        root = ET.Element("Response")
        ET.SubElement(root, "Say", {"language": language, "voice": voice, "loop": str(loop)}).text = message
        ET.SubElement(root, "Hangup")
        twiml = ET.tostring(root, encoding="unicode")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings['account_sid']}/Calls.json"
        session = async_get_clientsession(hass)
        try:
            async with session.post(url, data={"To": to, "From": sender, "Twiml": twiml},
                                    auth=aiohttp.BasicAuth(settings["api_key"], settings["api_secret"]),
                                    timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status not in (200, 201):
                    _LOGGER.error("Twilio API error HTTP %s", response.status)
                    raise HomeAssistantError(f"Twilio API HTTP {response.status}; prüfe Twilio Call Logs")
                result = await response.json()
                _LOGGER.info("Twilio call created: %s", result.get("sid"))
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise HomeAssistantError("Twilio nicht erreichbar") from exc
    hass.services.async_register(DOMAIN, "call", make_call, schema=SERVICE_SCHEMA)
    return True

async def async_options_updated(hass: HomeAssistant, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_migrate_entry(hass: HomeAssistant, entry) -> bool:
    """Preserve each old recipient and its service as a child of its API entry."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        settings = {**entry.data, **entry.options}
        number = settings["to_number"]
        old_service = f"{DOMAIN}_{number.lstrip('+')}_{entry.entry_id[:8]}"
        data = {"name": "Empfänger", "to_number": number, "service_name": old_service}
        if not entry.subentries:
            hass.config_entries.async_add_subentry(entry, ConfigSubentry(
                data=MappingProxyType(data), subentry_type="recipient",
                title=f"Empfänger → {number}", unique_id=number,
            ))
        settings.pop("to_number", None)
        hass.config_entries.async_update_entry(entry, data=settings, options={},
            title=f"Twilio → {settings['from_number']}", version=2)
    return True

async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    settings = {**entry.data, **entry.options}
    hass.config_entries.async_update_entry(entry, title=f"Twilio → {settings['from_number']}")
    service_names = []
    for recipient in entry.subentries.values():
        if recipient.subentry_type != "recipient":
            continue
        service_name = recipient.data['service_name']
        # Bind both IDs per handler, rather than closing over the loop variable.
        def make_handler(subentry_id):
            async def notify_call(call: ServiceCall):
                await async_notify_call(hass, call, entry.entry_id, subentry_id)
            return notify_call
        hass.services.async_register("notify", service_name,
                                     make_handler(recipient.subentry_id), schema=NOTIFY_SCHEMA)
        service_names.append(service_name)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = service_names
    if not hass.services.has_service("notify", DOMAIN):
        async def legacy_notify(call: ServiceCall):
            await async_notify_call(hass, call)
        hass.services.async_register("notify", DOMAIN, legacy_notify, schema=NOTIFY_SCHEMA)
    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    return True

async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    services = hass.data.get(DOMAIN, {})
    for service_name in services.pop(entry.entry_id, []):
        hass.services.async_remove("notify", service_name)
    if not services:
        hass.services.async_remove("notify", DOMAIN)
    return True
