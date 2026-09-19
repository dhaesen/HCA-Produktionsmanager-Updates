# HCA Produktionsmanager – Notfall-Rollback

Stand: 19.09.2026  
Zielstand: **v0.13.66**

## Begründung

Die Versionen v0.13.67 und v0.13.68 führten auf dem betroffenen Windows-Client zunächst zu einem Abbruch während des Ladens und nach den Launcher-Hotfixes zu einer weißen WebView. Damit ist nicht der Launcher allein, sondern die ausgelieferte Frontend-Dateikombination beschädigt beziehungsweise inkompatibel.

v0.13.66 ist der letzte bekannte funktionierende Stand vor dieser Fehlerkette. Dieser Stand enthält bereits die Wiederherstellung des Merch-Tabellenimports, der Maschinenwahl im Produktionsmonitor, des einheitlichen Referenztarifs und der korrigierten Versionsanzeige.

## Inhalt des Rollbacks

- Vollständige kumulative Oberfläche aus dem Update v0.13.66.
- Unveränderte Basisressourcen aus der geprüften Windows-Vollinstallation.
- Ursprünglicher, vor den fehlgeschlagenen Launcher-Hotfixes verwendeter Windows-Launcher.
- SHA256-Prüfung jeder einzelnen enthaltenen Datei.
- Automatische Sicherung aller ersetzten Dateien.
- Reversibles Verschieben des WebView2-Zwischenspeichers, damit keine defekten JavaScript-Dateien aus v0.13.67/v0.13.68 geladen werden.

## Geschützte Daten

Das Paket enthält und überschreibt ausdrücklich keine `config.json`, keinen Ordner `data`, keine Datenbank, keine Dokumente, keine Anhänge, keine NAS-Konfiguration, keine Docker-Dateien und keine `HCA_Backend.exe`.

## Wiederherstellung bei einem Abbruch

Wenn Kopieren oder Prüfen fehlschlägt, stellt das Skript den unmittelbar vorher gesicherten Dateistand automatisch wieder her. Die Sicherung liegt unter `%LOCALAPPDATA%\HCA Produktionsmanager\rollback\`.
