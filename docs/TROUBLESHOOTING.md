# Troubleshooting

## `sensor.wohnmobil_gesamtroute` existiert nicht

1. Prüfen, ob `homeassistant.packages` aktiviert ist.
2. Prüfen, ob `wohnmobil_tours.yaml` wirklich unter dem aktiven `/config/packages/` liegt.
3. Konfiguration prüfen.
4. Home Assistant neu starten.

## Sensor ist `unavailable`

Das Routenskript manuell ausführen:

```bash
python3 /config/scripts/wohnmobil_route.py \
  --config /config/wohnmobil_tours.private.json \
  --disable-map-matching \
  --pretty
```

Typische Ursachen:

- private JSON-Datei fehlt
- Traccar nicht erreichbar
- falsche interne Traccar-Device-ID
- falsche Traccar-Zugangsdaten
- `from` liegt außerhalb des verfügbaren Datenbereichs

## Karte meldet `Custom element doesn't exist`

Prüfen:

```text
/config/www/wohnmobil-tours-card.js
```

und Dashboard-Ressource:

```text
/local/wohnmobil-tours-card.js
Typ: JavaScript Module
```

Anschließend Ressourcen neu laden bzw. den Browser-Cache aktualisieren.

## Karte flackert ständig

Die mitgelieferte Karte rendert nur dann neu, wenn sich Routensensor, Namenssensor oder optionaler Tracker wirklich geändert haben. Wenn eine ältere JS-Version verwendet wird, die Datei unter `/config/www/` ersetzen und die Dashboard-Ressourcen neu laden.

## Karte zeigt Kacheln als einzelne Stücke

Die aktuelle Karte enthält die für das Shadow DOM erforderlichen Leaflet-CSS-Regeln. Prüfen, ob wirklich die mitgelieferte aktuelle Datei geladen wird.

## Leaflet-Fehler mit Clipping/Bounds

Die Karte verwendet absichtlich eine eigene Leaflet-Instanz und initialisiert Center/Zoom, bevor GeoJSON-Vektoren angelegt werden. Ältere Versionen der Karte sollten vollständig ersetzt werden.

## Erste oder letzte Kilometer fehlen

Prüfen, ob `home_radius_km`, `return_confirm_hours` und `home_stay_radius_km` sinnvoll gesetzt sind. Die aktuelle Tourlogik schneidet nicht am Eintritt/Austritt des großen Heimat-Radius ab, sondern an bestätigten stationären Aufenthalten.

## Es wird nur eine (aktive) Tour erkannt

Mehrere abgeschlossene Touren entstehen nur zwischen **bestätigten Heimataufenthalten**. Ein Aufenthalt gilt erst als bestätigt, wenn das Fahrzeug mindestens `return_confirm_hours` lang innerhalb von `home_stay_radius_km` um denselben Punkt steht.

Zur Ursachenanalyse das Skript mit `--explain` ausführen:

```bash
python3 /config/scripts/wohnmobil_route.py \
  --config /config/wohnmobil_tours.private.json \
  --disable-map-matching --explain > /tmp/route.json
```

Der Bericht erscheint auf `stderr` und zeigt pro Aufenthaltsfenster Dauer, Punktzahl, Spreizung um den Ankerpunkt und den Grund für eine Verwerfung:

- **Kein bestätigter Aufenthalt** → alles wird eine aktive Tour. Sendet der Tracker beim Parken zu Hause überhaupt Positionen? Ist `return_confirm_hours` zu hoch?
- **`moved_from_anchor` bei längeren Fenstern** → zu Hause wird an wechselnden Plätzen geparkt. `home_stay_radius_km` erhöhen (z. B. `2.0`–`3.0`).
- **Große Datenlücken** → der Tracker war zwischendurch aus; ein einzelner Aufenthaltsblock überspannt dann evtl. mehrere reale Rückkehren.
- **`from` zu spät** → im ausgewerteten Zeitraum liegt nur eine Reise.

## Map Matching zeigt Fehler

Im Detailbereich der Tour wird der Fehler angezeigt. Häufige Ursachen:

- OSRM-Dienst vorübergehend nicht erreichbar
- GPS-Punkte zu weit vom Straßennetz entfernt
- unplausibles Verhältnis zwischen Straßen- und GPS-Strecke
- Request-Limit des Servers

Nach einem Fehler wird standardmäßig erst nach 24 Stunden erneut versucht.

## Manuell aktualisieren

```yaml
action: homeassistant.update_entity
target:
  entity_id: sensor.wohnmobil_gesamtroute
```

## PAJ-Sync importiert nichts

- `paj.enabled` prüfen
- PAJ-Zugang lokal prüfen
- PAJ-Tracker-ID prüfen
- `traccar_ingest.unique_id` prüfen
- Traccar-OsmAnd-Port prüfen
- `paj_sync_state.json` nur dann löschen, wenn ein kompletter Neuimport bewusst gewünscht ist
