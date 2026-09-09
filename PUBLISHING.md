# HCA Release veröffentlichen

Der HCA Produktionsmanager nutzt dieses Repository als öffentliche Updatequelle.

## Stable Release

1. Auf GitHub **Releases → Draft a new release** öffnen.
2. Tag im Format `vX.Y.Z` anlegen, z. B. `v0.9.4`.
3. Einen kurzen Titel und die Änderungen als Release Notes eintragen.
4. Genau eine `.hcaupdate`-Datei als Asset hochladen.
5. Zusätzlich die passende `.sha256`-Datei hochladen.
6. Release veröffentlichen.

## Beta Release

Für Beta-Versionen einen Tag wie `v0.9.4-beta.1` verwenden und das Release als **pre-release** markieren.

## Pflichtinhalt

Jede `.hcaupdate`-Datei muss enthalten:

- `hca-update.json` im Root
- geänderte Programmdateien unter `payload/`
- `payload/version.json` mit der neuen Programmversion

`config.json` und `data/` dürfen nicht im Update enthalten sein.

## Prüfsumme

Die `.sha256`-Datei enthält die 64-stellige SHA256-Prüfsumme, z. B.:

```text
0123456789abcdef...  HCA_Update_v0.9.4.hcaupdate
```

Der Produktionsmanager verweigert eine automatische GitHub-Installation, wenn die SHA256-Datei fehlt oder die Prüfsumme nicht stimmt.
