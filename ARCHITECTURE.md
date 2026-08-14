# Architektur

## Datenfluss

1. GPS-Positionen liegen in Traccar vor.
2. `wohnmobil_route.py` liest den konfigurierten Zeitraum über `/api/positions`.
3. Die Punkte werden chronologisch sortiert.
4. Stationäre Heimataufenthalte werden erkannt.
5. Zwischen diesen Aufenthalten entstehen Touren.
6. Für jede Tour wird eine GPS-Distanz berechnet.
7. Nur abgeschlossene Touren werden optional gematcht.
8. Der Map-Matching-Wert wird im Cache gespeichert.
9. Das Skript gibt ein einziges JSON-Objekt aus.
10. Der Home-Assistant-`command_line`-Sensor übernimmt Zustand und Attribute.
11. Die Custom Card rendert die GeoJSON-Touren in Leaflet.
12. Tournamen werden über die kleine Custom Integration persistent gespeichert.

## Tourgrenzen

Ein 20-km-Radius allein würde bei einer Rückkehr bereits beim Eintritt in die Zone abschneiden. Die Lösung verwendet den großen Radius daher nur als grobe Heimat-Zone.

Ein Aufenthalt gilt erst als bestätigt, wenn das Fahrzeug innerhalb der Heimat-Zone über mehrere Stunden in einem kleinen Radius um einen Ankerpunkt bleibt. Dadurch sind Fahrten oder Erledigungen innerhalb der großen Zone kein Tourende.

## Frontend

Die Karte lädt eine eigene Leaflet-1.9.4-Instanz und stellt anschließend ein eventuell bereits vorhandenes globales `window.L` wieder her. Das verhindert Konflikte mit anderen Custom Cards, die ebenfalls Leaflet global registrieren.

Leaflet-Basis-CSS wird zusätzlich im Shadow DOM der Karte definiert. Dadurch werden Tile-Positionierung und Vektor-Layer auch dann korrekt dargestellt, wenn globale Stylesheets nicht in das Shadow DOM hineinwirken.

Die Karte rendert nur neu, wenn sich eine der tatsächlich verwendeten Entities ändert. Dadurch wird unnötiges Zerstören/Neuaufbauen der Karte bei beliebigen Home-Assistant-State-Updates vermieden.
