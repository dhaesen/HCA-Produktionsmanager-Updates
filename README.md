# HCA Produktionsmanager – Updates

Öffentliches Update-Repository für den **HCA Produktionsmanager**.

Dieses Repository enthält künftig ausschließlich veröffentlichte Update-Pakete und die dazugehörigen Release Notes. Der eigentliche Quellcode des Produktionsmanagers gehört nicht hierher.

## Update-Ablauf

1. Eine neue Version wird als GitHub Release veröffentlicht, z. B. `v0.9.3`.
2. Das Release enthält genau ein Stable-Update mit der Dateiendung `.hcaupdate`.
3. Der HCA Produktionsmanager prüft beim Start automatisch das neueste GitHub Release.
4. Ist eine neuere Version verfügbar, wird sie im Programm angezeigt.
5. Nach Bestätigung wird das `.hcaupdate` heruntergeladen, geprüft und über den vorhandenen HCA-Updater installiert.

## Namensschema

- Stable Release Tag: `vX.Y.Z`
- Beta Release Tag: `vX.Y.Z-beta.N`
- Update-Datei: `HCA_Update_vX.Y.Z.hcaupdate`
- SHA256-Datei: `HCA_Update_vX.Y.Z.sha256`

## Sicherheit

- `config.json` wird durch Updates nicht überschrieben.
- Der Ordner `data/` wird durch Updates nicht überschrieben.
- Produktionsdaten, COM-Zuordnungen, Pico-Adresse und Produktionsserver-Einstellungen bleiben erhalten.
- Der HCA Produktionsmanager installiert Updates nicht ungefragt; die Installation wird im Programm bestätigt.

## Updatequelle

Repository: `dhaesen/HCA-Produktionsmanager-Updates`

Der HCA Produktionsmanager verwendet die öffentliche GitHub-Releases-API. Dadurch muss kein GitHub-Token in der Anwendung gespeichert werden.
