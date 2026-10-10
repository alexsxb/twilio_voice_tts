import re
import uuid
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify
from .const import DOMAIN, DEFAULT_VOICE

PHONE = r'^\+[1-9]\d{6,14}$'

def api_schema(defaults=None):
    d = defaults or {}
    return vol.Schema({
        vol.Required('account_sid', default=d.get('account_sid', '')): str,
        vol.Required('api_key', default=d.get('api_key', '')): str,
        vol.Required('api_secret', default=d.get('api_secret', '')): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        vol.Required('from_number', default=d.get('from_number', '')): str,
        vol.Required('voice', default=d.get('voice', DEFAULT_VOICE)): str,
        vol.Required('language', default=d.get('language', 'fr-FR')): str,
        vol.Required('loop', default=d.get('loop', 1)): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    })

def valid_api(data):
    return (bool(re.fullmatch(r'AC[0-9a-fA-F]{32}', data['account_sid']))
            and bool(re.fullmatch(r'SK[0-9a-fA-F]{32}', data['api_key']))
            and bool(data['api_secret'].strip())
            and bool(re.fullmatch(PHONE, data['from_number']))
            and bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', data['voice']))
            and bool(re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?', data['language'])))

def recipient_schema(defaults=None):
    d = defaults or {}
    return vol.Schema({
        vol.Required('name', default=d.get('name', '')): str,
        vol.Required('to_number', default=d.get('to_number', '')): str,
    })

def recipient_title(data):
    return f"{data['name']} → {data['to_number']}"

class TwilioVoiceTTSFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if valid_api(user_input):
                # Existing migrated accounts can keep their old unique IDs.
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if entry.data['account_sid'] == user_input['account_sid']:
                        return self.async_abort(reason='already_configured')
                await self.async_set_unique_id(user_input['account_sid'])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Twilio → {user_input['from_number']}", data=user_input)
            errors['base'] = 'invalid_config'
        return self.async_show_form(step_id='user', data_schema=api_schema(user_input), errors=errors)

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry):
        return {'recipient': RecipientFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TwilioOptionsFlow()

class TwilioOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            if valid_api(user_input) and user_input['account_sid'] == self.config_entry.data['account_sid']:
                return self.async_create_entry(title='', data=user_input)
            errors['base'] = 'invalid_config'
        return self.async_show_form(step_id='init', data_schema=api_schema(user_input or current), errors=errors)

class RecipientFlow(config_entries.ConfigSubentryFlow):
    async def async_step_user(self, user_input=None):
        return await self._form('user', user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._form('reconfigure', user_input)

    async def _form(self, step_id, user_input):
        entry = self._get_entry()
        existing = self._get_reconfigure_subentry() if step_id == 'reconfigure' else None
        errors = {}
        if user_input is not None:
            if not user_input['name'].strip() or not re.fullmatch(PHONE, user_input['to_number']):
                errors['base'] = 'invalid_recipient'
            elif any(sub.subentry_id != (existing.subentry_id if existing else None)
                     and sub.data['to_number'] == user_input['to_number']
                     for sub in entry.subentries.values()):
                errors['base'] = 'duplicate_recipient'
            else:
                data = dict(existing.data) if existing else {}
                data.update(user_input)
                data['name'] = data['name'].strip()
                if existing:
                    # Listener reloads the parent; preserve the notify service name.
                    return self.async_update_and_abort(entry, existing, data=data,
                        title=recipient_title(data), unique_id=data['to_number'])
                data['service_name'] = f"{DOMAIN}_{slugify(data['name']) or 'recipient'}_{uuid.uuid4().hex[:8]}"
                return self.async_create_entry(title=recipient_title(data), data=data,
                                               unique_id=data['to_number'])
        defaults = user_input or (dict(existing.data) if existing else {})
        return self.async_show_form(step_id=step_id, data_schema=recipient_schema(defaults), errors=errors)
