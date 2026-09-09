# HCA Release veröffentlichen

Der HCA Produktionsmanager nutzt dieses Repository als öffentliche Updatequelle.

## Automatischer Stable-Release

Die Release-Erstellung ist automatisiert:

1. Eine fertige `.hcaupdate`-Datei in den Ordner `incoming/` hochladen.
2. Die GitHub Action `HCA Update veröffentlichen` startet automatisch.
3. Sie liest `hca-update.json` aus der Update-Datei.
4. Sie prüft die Produktkennung `HCA Produktionsmanager` und die Version.
5. Sie berechnet automatisch die SHA256-Prüfsumme.
6. Sie legt bzw. aktualisiert das GitHub Release mit Tag `v<version>`.
7. `.hcaupdate` und `.sha256` werden als Release Assets veröffentlicht.
8. Der HCA Produktionsmanager findet das Release anschließend automatisch.

Ein separates manuelles Erstellen der `.sha256` auf GitHub ist nicht mehr nötig.

## Beta Release

Beta-Versionen werden weiterhin mit einer Versionskennung wie `0.9.5-beta.1` gebaut. Die aktuelle Automatik veröffentlicht Uploads zunächst als normalen Release. Eine automatische Kennzeichnung als Pre-Release kann ergänzt werden, sobald der Beta-Kanal tatsächlich genutzt wird.

## Pflichtinhalt

Jede `.hcaupdate`-Datei muss enthalten:

- `hca-update.json` im Root
- geänderte Programmdateien unter `payload/`
- `payload/version.json` mit der neuen Programmversion

`config.json` und `data/` dürfen nicht im Update enthalten sein.

## Prüfsumme

Die Action erstellt die `.sha256`-Datei automatisch. Der Produktionsmanager verweigert eine automatische GitHub-Installation, wenn die Prüfsumme fehlt oder nicht zur `.hcaupdate` passt.
