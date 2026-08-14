# Installation

## Voraussetzungen

- Home Assistant mit Zugriff auf den aktiven Konfigurationspfad `/config`
- Python 3 im Home-Assistant-System bzw. in der Umgebung, in der `command_line` ausgeführt wird
- erreichbare Traccar-API
- optional: PAJ-GPS-Konto für den automatischen PAJ→Traccar-Sync
- Internetzugriff für OpenStreetMap-Kartenkacheln und optional OSRM Map Matching

## 1. Dateien kopieren

Kopiere die Dateien in den **aktiven Home-Assistant-Pfad `/config`**:

```text
/config/scripts/wohnmobil_route.py
/config/scripts/paj_sync_to_traccar.py          # optional
/config/www/wohnmobil-tours-card.js
/config/packages/wohnmobil_tours.yaml
/config/custom_components/wohnmobil_tour_names/__init__.py
/config/custom_components/wohnmobil_tour_names/manifest.json
/config/custom_components/wohnmobil_tour_names/services.yaml
/config/wohnmobil_tours.private.json
```

Wichtig: Entscheidend ist der Pfad, den Home Assistant zur Laufzeit als `/config` sieht. Bei externen Dateieditoren oder Mounts kann ein ähnlich benannter Pfad auf ein anderes Verzeichnis zeigen.

## 2. Private Konfiguration anlegen

```bash
cp config/wohnmobil_tours.example.json /config/wohnmobil_tours.private.json
```

Danach ausschließlich die lokale Datei bearbeiten. Sie enthält unter anderem:

- Traccar-Adresse
- Traccar-Device-ID
- Traccar-Benutzername und Passwort
- Heimatkoordinaten
- optional PAJ-Zugang und Tracker-ID

Die Datei ist absichtlich in `.gitignore` ausgeschlossen.

## 3. Packages aktivieren

Falls noch nicht vorhanden:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Danach Home-Assistant-Konfiguration prüfen.

## 4. Skript manuell testen

Auf dem System, auf dem Home Assistant die Befehle ausführt:

```bash
python3 /config/scripts/wohnmobil_route.py \
  --config /config/wohnmobil_tours.private.json \
  --disable-map-matching \
  --pretty
```

Der Test sollte ein JSON-Objekt mit `tour_count`, `tours` und `tour_01_geojson` bis `tour_50_geojson` ausgeben.

## 5. Home Assistant neu starten

Der Neustart lädt:

- das Package
- den `command_line`-Sensor
- die Custom Integration für Tournamen

Danach sollte mindestens folgende Entity vorhanden sein:

```text
sensor.wohnmobil_gesamtroute
sensor.wohnmobil_tour_names
```

## 6. Lovelace-Ressource registrieren

Unter **Einstellungen → Dashboards → Ressourcen**:

```text
URL: /local/wohnmobil-tours-card.js
Typ: JavaScript Module
```

`/local/...` entspricht Dateien unter `/config/www/...`.

## 7. Karte hinzufügen

```yaml
type: custom:wohnmobil-tours-card
entity: sensor.wohnmobil_gesamtroute
names_entity: sensor.wohnmobil_tour_names
title: Wohnmobil-Touren
height: 720
sidebar_width: 320
show_rename: true
```

Optional kann eine aktuelle Fahrzeugposition ergänzt werden:

```yaml
tracker_entity: device_tracker.DEIN_WOHNMOBIL
```

## 8. Manuelle Aktualisierung

```yaml
action: homeassistant.update_entity
target:
  entity_id: sensor.wohnmobil_gesamtroute
```

## 9. Optionalen PAJ-Sync aktivieren

In der privaten JSON-Datei:

```json
"paj": {
  "enabled": true
}
```

Zusätzlich müssen alle `CHANGE_ME`-Werte in `paj` und `traccar_ingest` gesetzt sein.

Das Package enthält eine auskommentierte Beispiel-Automation. Erst nach erfolgreichem manuellen Test aktivieren:

```bash
python3 /config/scripts/paj_sync_to_traccar.py \
  --config /config/wohnmobil_tours.private.json
```

## 10. Empfohlene Recorder-Konfiguration

Der Routensensor kann große GeoJSON-Attribute enthalten. Wer den Home-Assistant-Recorder klein halten möchte, sollte `sensor.wohnmobil_gesamtroute` vom Recorder ausschließen. Die genaue Einbindung hängt von der vorhandenen Recorder-Konfiguration ab.
