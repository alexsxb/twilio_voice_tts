# Twilio Voice TTS – Version 2.0.0

Home-Assistant-Integration für Twilio-TTS-Anrufe und separate Alarmo-Benachrichtigungsziele.
Home Assistant 2026.3 oder neuer erforderlich. Das originale Twilio-Logo stammt aus
https://github.com/home-assistant/brands/tree/master/core_brands/twilio.

## Installation / Update

1. Den Ordner custom_components/twilio_voice_tts in das HA-Konfigurationsverzeichnis kopieren und die bisherigen Dateien ersetzen.
2. Home Assistant neu starten: `ha core restart`.
3. Browser neu laden; bei altem Logo Browser-Cache leeren.

## Eine API, mehrere Empfänger

Unter Einstellungen → Geräte & Dienste → Integration hinzufügen → Twilio Voice TTS
API-Zugangsdaten, Absender und Standardwerte für Stimme, Sprache und Wiederholungen konfigurieren.
Ein Twilio-Account wird nur einmal neu eingerichtet. Bereits konfigurierte Accounts werden erkannt.
In der Integrationsübersicht beim Twilio-Eintrag „Empfänger hinzufügen“ wählen.
Für jeden Empfänger nur Name und Telefonnummer (+..., E.164) eingeben.
Die Untereinträge zeigen Name und Nummer; sie können einzeln geändert oder gelöscht werden.
Die API-Einstellungen werden über Konfigurieren geändert. Der Account SID bleibt unverändert.
Alle Empfänger verwenden dieselben Zugangsdaten, denselben Absender und dieselben Ansage-Standardwerte.

## Alarmo

Jeder Empfänger bekommt einen eigenen Dienst: notify.twilio_voice_tts_<Name>_<Kennung>.
Die Kennung verhindert Namenskollisionen. Der Dienstname bleibt beim Ändern von Name oder Nummer erhalten.
In Alarmo → Aktionen → Benachrichtigungen für jeden gewünschten Empfänger eine Benachrichtigung
mit Ereignis „Alarm ausgelöst“ und seinem Notify-Dienst anlegen. Kein target nötig.
Die Nachricht wird gesprochen, der Titel ignoriert. loop=1 spricht einmal und legt danach auf.

## Bestehende Konfiguration

Jeder alte Integrationseintrag wird automatisch in einen API-Eintrag mit einem Empfänger-Unter­eintrag umgewandelt.
Zugangsdaten, Telefonnummern und alte nummerierte Notify-Dienste bleiben erhalten.
Mehrere bisherige API-Einträge werden nicht automatisch gelöscht oder zusammengeführt.
Falls bereits mehrere Einträge für denselben Account vorhanden sind: die zusätzlichen Empfänger
unter dem gewünschten Haupt-Eintrag hinzufügen, Alarmo auf diese neuen Ziele umstellen und anschließend
die nicht mehr benötigten alten API-Einträge über die HA-Oberfläche entfernen.
Bei einem API-Eintrag mit mehreren Empfängern werden diese durch Löschen des API-Eintrags ebenfalls entfernt.

Der bisherige Dienst notify.twilio_voice_tts sowie twilio_voice_tts.call bleiben vorhanden.
Ohne explizite Auswahl wird der erste Empfänger des ersten API-Eintrags verwendet.
Dies ist kein Sammelanruf. Für Alarmo immer den individuellen Empfängerdienst wählen.

## Direkter Dienst

```yaml
action: notify.twilio_voice_tts_alex_<Kennung>
data:
  message: "Attention ! Alerte intrusion ! Veuillez vérifier votre système d'alarme."
```

Optional unterstützt notify weiterhin target als Telefonnummernliste und data mit
from_number, voice, language, loop oder to als Overrides. Der ursprüngliche call-Dienst
unterstützt zusätzlich entry_id und subentry_id für die konkrete Auswahl.

## Prüfung

Syntax, JSON und PNG-Dateien geprüft. Isolierte Tests mit simulierten HA-Schnittstellen:
Migration eines alten Eintrags, zwei Empfänger mit gemeinsamen Zugangsdaten,
Übernahme geänderter Standardwerte, stabile Empfängerzuordnung, XML-Escaping,
Entfernen der Dienste beim Entladen, Empfängeranlage, Duplikatschutz und Änderung.
Kein Live-Test in Home Assistant oder Alarmo, kein Testanruf.
