# Incoming HCA Updates

Fertige `.hcaupdate`-Dateien werden hier hochgeladen.

Sobald eine neue `.hcaupdate` in diesen Ordner gepusht wird, liest die GitHub Action `hca-update.json`, prüft die Produktkennung, erzeugt die SHA256-Datei und veröffentlicht automatisch ein GitHub Release mit Tag `v<version>`.

Der HCA Produktionsmanager bezieht Stable-Updates anschließend über die GitHub Releases API.
