# Konfiguration

Alle installationseigenen Werte liegen in `/config/wohnmobil_tours.private.json`.

## `traccar`

| Feld | Bedeutung |
|---|---|
| `base_url` | Traccar-HTTP(S)-Basisadresse inklusive API-Port |
| `device_id` | interne numerische Traccar-Device-ID |
| `username` | Traccar-Benutzername |
| `password` | Traccar-Passwort |
| `timeout_seconds` | Timeout für API-Anfragen |

## `tour_detection`

| Feld | Standard | Bedeutung |
|---|---:|---|
| `home_latitude` | – | Breitengrad des Heimatbezugspunkts |
| `home_longitude` | – | Längengrad des Heimatbezugspunkts |
| `home_radius_km` | `20.0` | großer Radius zur sicheren Trennung von Reisen |
| `return_confirm_hours` | `3.0` | Mindestdauer eines bestätigten Heimataufenthalts |
| `home_stay_radius_km` | `1.0` | maximale Bewegung um den Abstellpunkt während der Bestätigung |
| `from` | – | Beginn des auszuwertenden Traccar-Zeitraums in ISO-8601 |
| `max_tours` | `50` | maximale Zahl der an Home Assistant ausgegebenen Tour-Slots |

### Warum zwei Radien?

Der große Heimat-Radius trennt längere Reisen zuverlässig. Er darf daher großzügig sein. Würde jedoch jede Bewegung innerhalb dieses Radius sofort als „zu Hause“ gelten, würden die ersten und letzten Kilometer einer Reise abgeschnitten.

Darum wird ein Rückkehrpunkt erst bestätigt, wenn das Fahrzeug über die konfigurierte Zeit nahezu am selben Abstellpunkt bleibt. Die sichtbare Tour beginnt am letzten Punkt des vorherigen bestätigten Aufenthalts und endet am ersten Punkt des nächsten bestätigten Aufenthalts.

## `map_matching`

| Feld | Standard | Bedeutung |
|---|---:|---|
| `enabled` | `true` | Map Matching für abgeschlossene Touren |
| `url` | öffentlicher OSRM Match Service | OSRM-Endpunkt |
| `cache_file` | `/config/wohnmobil_tour_stats.json` | persistenter Ergebnis-Cache |
| `chunk_points` | `40` | gewünschte Chunk-Größe; bei `TooBig` wird automatisch weiter geteilt |
| `min_point_distance_m` | `100` | GPS-Punkte vor dem Matching ausdünnen |
| `default_radius_m` | `30` | Suchradius pro GPS-Punkt |
| `request_delay_seconds` | `1.05` | Pause zwischen Requests |
| `retry_after_hours` | `24` | Pause nach fehlgeschlagenem Matching |
| `min_ratio_to_gps` | `0.75` | untere Plausibilitätsgrenze Straße/GPS |
| `max_ratio_to_gps` | `1.5` | obere Plausibilitätsgrenze Straße/GPS |

## `paj`

Der Bereich ist optional. Mit `enabled: false` wird der PAJ-Sync übersprungen.

Die Zugangsdaten gehören ausschließlich in die lokale private Datei. Das Skript speichert das PAJ-Login-Token nicht dauerhaft.

## `traccar_ingest`

Ziel des optionalen PAJ-Syncs über das Traccar-OsmAnd-Protokoll.

`unique_id` ist die eindeutige Traccar-Gerätekennung für den eingehenden Datenstrom und ist **nicht** dasselbe wie die interne numerische `traccar.device_id` der REST-API.
