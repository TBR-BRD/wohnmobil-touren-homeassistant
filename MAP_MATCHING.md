# Map Matching

## Zweck

Die direkte GPS-Strecke summiert die Luftlinien zwischen aufeinanderfolgenden Messpunkten. Für Reisestatistiken kann das von der tatsächlich gefahrenen Straßenstrecke abweichen.

Das optionale Map Matching über OSRM ordnet GPS-Punkte einem plausiblen Straßennetz zu und verwendet die daraus resultierende Routenlänge als `distance_road_km`.

## Nur abgeschlossene Touren

Aktive Touren werden nicht gematcht. Erst wenn ein neuer bestätigter Heimataufenthalt die Tour beendet, wird einmalig ein Matching-Versuch gestartet.

## Cache

Erfolgreiche Ergebnisse werden standardmäßig hier gespeichert:

```text
/config/wohnmobil_tour_stats.json
```

Bei späteren Sensor-Aktualisierungen wird das Ergebnis aus dem Cache gelesen. Die abgeschlossene Tour erzeugt dadurch keine wiederholten OSRM-Anfragen.

## Schutzmaßnahmen

- GPS-Punkte werden vor dem Matching ausgedünnt.
- große Tracks werden in überlappende Chunks geteilt.
- meldet der Server `TooBig`, wird rekursiv weiter geteilt.
- zwischen Requests liegt eine Pause.
- nach Fehlern gilt eine Retry-Sperre.
- Straßen- und GPS-Distanz müssen innerhalb konfigurierbarer Plausibilitätsgrenzen liegen.

## Matching manuell neu ausführen

Alle abgeschlossenen Touren unabhängig vom Cache erneut matchen:

```bash
python3 /config/scripts/wohnmobil_route.py \
  --config /config/wohnmobil_tours.private.json \
  --force-rematch \
  > /tmp/wohnmobil_route.json
```

Danach den Home-Assistant-Sensor normal aktualisieren:

```yaml
action: homeassistant.update_entity
target:
  entity_id: sensor.wohnmobil_gesamtroute
```

## Ohne Map Matching testen

```bash
python3 /config/scripts/wohnmobil_route.py \
  --config /config/wohnmobil_tours.private.json \
  --disable-map-matching \
  --pretty
```

## Öffentlicher OSRM-Dienst

Der Default nutzt den öffentlichen OSRM-Demo-Service. Für häufige, große oder produktive Lasten ist ein eigener OSRM-Dienst die robustere Lösung. Die Caching- und Drosselungslogik dieses Projekts ist bewusst darauf ausgelegt, unnötige Requests zu vermeiden.
