# HCA Produktionsmanager – Updates

Öffentliches Update-Repository für den **HCA Produktionsmanager**.

Dieses Repository enthält veröffentlichte Update-Pakete, Release Notes und die kleine GitHub-Action zur automatischen Release-Erstellung. Der eigentliche Quellcode des Produktionsmanagers gehört nicht hierher.

## Update-Ablauf

1. Eine fertige `.hcaupdate`-Datei wird unter `incoming/` hochgeladen.
2. Die GitHub Action liest die Version aus `hca-update.json`, berechnet SHA256 und veröffentlicht automatisch das passende GitHub Release, z. B. `v0.9.4`.
3. Der HCA Produktionsmanager prüft beim Start automatisch das neueste GitHub Release.
4. Ist eine neuere Version verfügbar, wird sie im Programm angezeigt.
5. Nach Bestätigung wird das `.hcaupdate` heruntergeladen, gegen die SHA256-Datei geprüft und über den vorhandenen HCA-Updater installiert.

## Namensschema

- Stable Release Tag: `vX.Y.Z`
- Beta Release Tag: `vX.Y.Z-beta.N`
- Update-Datei: `HCA_Update_vX.Y.Z.hcaupdate`
- SHA256-Datei: wird von der GitHub Action automatisch erzeugt

## Sicherheit

- `config.json` wird durch Updates nicht überschrieben.
- Der Ordner `data/` wird durch Updates nicht überschrieben.
- Produktionsdaten, COM-Zuordnungen, Pico-Adresse und Produktionsserver-Einstellungen bleiben erhalten.
- Der HCA Produktionsmanager installiert Updates nicht ungefragt; die Installation wird im Programm bestätigt.

## Updatequelle

Repository: `dhaesen/HCA-Produktionsmanager-Updates`

Der HCA Produktionsmanager verwendet die öffentliche GitHub-Releases-API. Dadurch muss kein GitHub-Token in der Anwendung gespeichert werden.
