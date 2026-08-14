# Security und Datenschutz

Dieses Projekt verarbeitet Standortdaten und Zugangsdaten. Ein öffentliches Repository darf daher nur den generischen Code und Beispielwerte enthalten.

## Niemals committen

- `wohnmobil_tours.private.json`
- echte Heimatkoordinaten
- PAJ-E-Mail-Adresse oder Passwort
- PAJ-Tracker-ID
- Traccar-Benutzername oder Passwort
- interne Traccar-IP/Hostnamen, wenn sie nicht veröffentlicht werden sollen
- interne oder eindeutige Device-IDs
- `paj_sync_state.json`
- `wohnmobil_tour_stats.json`
- exportierte GPS-Rohdaten
- Home-Assistant-Backups oder `.storage`-Inhalte

## Vor dem Push

```bash
python3 scripts/check_public_repo.py .
```

Zusätzlich immer `git diff --cached` kontrollieren.

## Bei versehentlichem Secret-Commit

Nur das Löschen in einem späteren Commit reicht nicht. Zugangsdaten sofort rotieren und den betroffenen Wert als kompromittiert behandeln. Falls erforderlich, muss die Git-Historie bereinigt werden.
