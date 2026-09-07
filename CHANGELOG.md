# Changelog

## Unreleased

- `wohnmobil_route.py --explain` ergänzt: erklärt auf stderr, welche Heimataufenthalte bestätigt bzw. verworfen wurden (mit Dauer, Ankerpunkt-Spreizung, Grund), zeigt Datenlücken und die resultierenden Tourgrenzen. Hilft bei „es wird nur eine Tour erkannt".

## 1.0.0 - 2026-08-14

- erste öffentliche, bereinigte Repository-Version
- generische Traccar-Konfiguration ohne feste private Werte
- Tour-Trennung über bestätigte Heimataufenthalte
- Start-/Endpunkte innerhalb des Heimat-Radius bleiben erhalten
- bis zu 50 Tour-Slots
- einmaliges OSRM Map Matching für abgeschlossene Touren mit Cache
- dynamische Leaflet-Karte inklusive Shadow-DOM- und Re-Render-Fixes
- persistente Tournamen als Home-Assistant-Custom-Integration
- optionaler PAJ→Traccar-Sync
- Installations-, Konfigurations-, Map-Matching- und Troubleshooting-Dokumentation
- Secret-/Privacy-Check und CI
