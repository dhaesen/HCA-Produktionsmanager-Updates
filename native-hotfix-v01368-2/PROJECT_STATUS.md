# HCA Produktionsmanager – Projektstatus

Stand: 19.09.2026  
Reparaturstand: **Launcher-Reparaturpaket v0.13.68.4**

## Korrektur v0.13.68.4

- Die native Ladeblende wartet nicht mehr zwingend auf `NavigationCompleted`.
- Die Oberfläche wird bereits bei `DOMContentLoaded` eingeblendet.
- Falls WebView2 keines der beiden Ereignisse meldet, wird die WebView nach acht Sekunden trotzdem sichtbar geschaltet.
- Ein expliziter WebView2-Navigationsfehler bleibt weiterhin ein echter Startfehler und wird mit Status protokolliert.
- Damit wird der Zustand `Arbeitsbereiche werden geladen` nicht mehr dauerhaft vor einer bereits erreichbaren HCA-Oberfläche angezeigt.

## Korrektur v0.13.68.3

- Fehlerhafte manuelle Pfadeingabe entfernt, durch die nur `C` uebernommen werden konnte.
- Installationsordner wird nun ueber den laufenden Prozess, Registry, das erfolgreiche Reparaturprotokoll v0.13.68, typische Benutzerprofile und Verknuepfungen ermittelt.
- Falls keine automatische Erkennung gelingt, wird eine grafische Ordnerauswahl statt einer Texteingabe angezeigt.
- Konsolenausgaben sind ASCII-kompatibel, damit Windows PowerShell keine defekten Umlaute anzeigt.
- Der enthaltene und bereits verifizierte Windows-Launcher bleibt Dateiversion `0.13.68.2`.

## Anlass

Nach der Oberflächenreparatur v0.13.68 blieb der native Windows-Client beim Start mit der irreführenden Meldung stehen, WebView2 könne nicht geladen werden.

Die ausgewerteten Protokolle belegen:

- Der lokale HCA-Dienst ist erreichbar.
- Microsoft Edge WebView2 Runtime 153.0.4234.32 wird erfolgreich erkannt und initialisiert.
- Der Launcher bricht exakt nach seinem fest codierten Navigationslimit von 25 Sekunden ab.
- Die 135 Oberflächendateien des Reparaturpakets v0.13.68 wurden vollständig geprüft und kopiert.

## Umgesetzte Korrektur

- Navigationslimit der HCA-Oberfläche von 25 auf 120 Sekunden erhöht.
- WebView2-Navigationsergebnis und konkreter Fehlerstatus werden protokolliert.
- Bei einem echten Timeout wird das erreichte 120-Sekunden-Limit ausdrücklich genannt.
- Die pauschale und in diesem Fall falsche Aufforderung zur WebView2-Installation wurde entfernt.
- Das Fehlerfenster verweist stattdessen auf das konkrete Startprotokoll.
- Dateiversion des Windows-Launchers: `0.13.68.2`.

## Reparaturpaket

Das eigenständige ZIP ersetzt ausschließlich `HCA_Produktionsmanager.exe`.

Unverändert bleiben:

- `config.json`
- Datenbank und Ordner `data/`
- Dokumente und Anhänge
- NAS-Konfiguration
- Docker-Compose-Konfiguration
- HCA-Backend und Oberflächendateien

Vor dem Austausch wird der bisherige Launcher unter `%LOCALAPPDATA%\HCA Produktionsmanager\recovery\` gesichert. Die neue Datei wird vor und nach dem Kopieren per SHA256 geprüft. Bei einer fehlgeschlagenen Prüfung wird die Sicherung automatisch zurückgespielt.

## Verifikation

- Windows-.NET-Framework-4.8-Build über GitHub Actions vorgesehen.
- Die Workflow-Prüfung verlangt exakt Dateiversion `0.13.68.2`.
- Das veröffentlichte ZIP und der enthaltene Launcher erhalten getrennte SHA256-Prüfsummen.
- Der Hotfix wird als zusätzliches Asset am bestehenden Release `v0.13.68` veröffentlicht; dadurch wird kein fehlerhaftes automatisches Client-Update ausgelöst.

## Noch zu prüfen

- Reparatur auf dem betroffenen Windows-Rechner ausführen.
- Erfolgreichen Start und Protokolleintrag `HCA-Oberfläche wurde geöffnet.` bestätigen.
- Falls selbst 120 Sekunden überschritten werden, das neue `hca-start.log` auswerten; es enthält dann den konkreteren Navigationsstatus.
