# HCA Produktionsmanager – Projektstatus

Stand: 14. September 2026  
Aktuelle Testversion: **0.13.5.4**  
Quellbranch: `codex/v0.13.2-development`

## Aktueller Lieferumfang

- WPF/WebView2-Desktopclient mit eigenem HCA-Fenster und festem Branding
- CRM, Kundenkartei, Angebote, Aufträge, Rechnungen und Lieferscheine
- Dokumentbeziehungen, Entwürfe, Duplizieren, Direktdruck und Dokumentenvorschau
- Briefpapiervorlage mit zentral gepflegten Unternehmens- und Bankdaten
- Produkt- und Veredelungskalkulation aus WooCommerce-Daten
- Printprodukte als eigene Positionsart
- Mehrpostfach-E-Mail-Client mit HTML-/WYSIWYG-Nachrichten
- Lexware-Office-Übergabe von Rechnungen und Rechnungskorrekturen
- Sendcloud-, Produktions-, Lager- und Logistikfunktionen

## Version 0.13.5.4 – Einzelne Setup-EXE und einfacher Startbildschirm

- Der native Windows-Startbildschirm ist die einzige Startanzeige im Desktopclient.
- Der bisher anschließend sichtbare HTML-Startbildschirm wird ausschließlich im nativen WebView2-Host vor dem ersten Seitenbild ausgeblendet; der Webtest behält seine eigene Startanzeige.
- Vollinstallation als einzelne Inno-Setup-Datei mit eingebettetem HCA-Anwendungssymbol.
- Installation erfolgt benutzerbezogen nach `%LOCALAPPDATA%\Programs\HCA Produktionsmanager` und benötigt normalerweise keine Administratorrechte.
- HCA-Client und Backend werden vor dem Austausch kontrolliert beendet.
- Vorhandene `config.json` und lokale Daten werden weder überschrieben noch deinstalliert.
- Desktop-Verknüpfung ist auswählbar; Startmenüeintrag und reguläre Deinstallation werden angelegt.
- Setup-EXE, eingebettetes Icon und veröffentlichte SHA-256-Prüfsumme wurden im Windows-Build automatisiert geprüft.
- Download: `HCA_Produktionsmanager_Setup_v0.13.5.4.exe`
- SHA-256: `694b3cc73755ec1a32eaf6467ea917984bad9726136b4ce7b6885b8c8ae4f789`
- Das WooCommerce-Plugin wurde nicht verändert.

## Version 0.13.5.3 – Vollinstallation und nativer Startbildschirm

- Neue vollständige Clientinstallation auf Basis der korrigierten Vollinstallation 0.13.0 und sämtlicher Clientupdates bis 0.13.5.2.
- Der bisherige weiße WPF-Startbildschirm wurde durch einen nativen dunklen HCA-Startbildschirm mit Original-Logo ersetzt.
- Der Ladebalken folgt den tatsächlichen Startphasen: Konfiguration, lokaler Dienst, WebView2 und Oberfläche.
- Die Weboberfläche wird erst eingeblendet, nachdem die Navigation erfolgreich abgeschlossen wurde.
- Original-Firmenlogo und Original-App-Symbol sind fest im Paket enthalten.
- Vorhandene `config.json` und der lokale `data`-Ordner werden bei der Installation übernommen.
- Native Windows-EXE ohne Compilerfehler gebaut; JavaScript, Paketstruktur, ZIP-Integrität und veröffentlichte SHA-256-Prüfsumme automatisiert geprüft.
- Download: `HCA_Client_Vollinstallation_v0.13.5.3.zip`
- SHA-256: `1927fc2d53e484ee49120343a05a0fef6e7084f6c6846e64692a4119991dbd66`
- Voraussetzung für die Benutzeranmeldung bleibt der NAS-Login-Hotfix 0.13.5.1.
- Das WooCommerce-Plugin wurde nicht verändert.

## Version 0.13.5.2 – Login-Sperrfehler behoben

- Die gespeicherte Produktionsserver-Konfiguration wird vor der Authentifizierungsabfrage aus der lokalen API geladen.
- Die Anmeldung kann nicht mehr fälschlich wegen einer noch nicht geladenen Serveradresse sperren.
- Bei tatsächlich fehlender Serveradresse bietet die Anmeldeseite einen Notfallzugang zu den Servereinstellungen.
- Für bereits ausgesperrte Clients existiert ein separates Reparaturpaket, das nur drei Clientdateien ersetzt und Sicherungskopien anlegt.
- Konfiguration, Belege, lokale Produktionsdaten und NAS-Datenbank bleiben unverändert.
- Der NAS-Login-Hotfix 0.13.5.1 bleibt erforderlich.
- Das WooCommerce-Plugin wurde nicht verändert.

## Version 0.13.5

### Persönliche Benutzerkonten

- Ersteinrichtung ohne Standardkennwort: Der erste Benutzer wird vom Betreiber selbst als Administrator angelegt.
- Rollen: Administrator und Mitarbeiter
- Benutzer aktivieren und deaktivieren
- Passwörter durch Administrator neu setzen
- Eigenes Passwort im Benutzerprofil ändern
- Schutz gegen Deaktivierung oder Herabstufung des letzten aktiven Administrators
- Passwörter als PBKDF2-HMAC-SHA256 mit individuellem Salt und 600.000 Iterationen
- Zufällige Sitzungstoken; serverseitig ausschließlich als SHA-256-Hash gespeichert
- Normale Sitzung: 12 Stunden
- Option „angemeldet bleiben“: 30 Tage
- Mobile Lagerzugänge bleiben von der Desktop-Benutzeranmeldung getrennt.

### Persönliche E-Mail-Signatur

- Signatur wird je HCA-Benutzer zentral auf der NAS gespeichert.
- Bearbeitung im Benutzerprofil mit WYSIWYG-Formatierung
- Automatische Einfügung in jede neue Nachricht
- HTML-Signatur wird vor Anzeige und Versand auf erlaubte Elemente und Attribute begrenzt.
- Die bisherige postfachbezogene Signatur bleibt aus Kompatibilitätsgründen erhalten, die persönliche Benutzersignatur hat im neuen Editor Vorrang.

### Startbildschirm

- Der HTML-Startbildschirm mit Logo und Ladebalken ist vorhanden.
- Der davor sichtbare weiße native Startbildschirm gehört zur WPF-Hülle.
- Für dessen vollständigen Austausch wird der aktuelle WPF-Host-Quellcode oder die aktuelle Vollinstallation benötigt; ein `.hcaupdate` kann diesen Programmabschnitt nicht ersetzen.

## Installation 0.13.5

1. NAS-Erweiterung 0.13.5 installieren und NAS-Dienst neu starten.
2. Clientupdate 0.13.5 einspielen.
3. HCA schließen und neu starten.
4. Beim ersten Start den ersten Administrator anlegen.
5. Weitere Benutzer unter „Einstellungen → HCA-Benutzerverwaltung“ anlegen.
6. Persönliche Signatur unter „Einstellungen → Mein Benutzerprofil“ speichern.

## Sicherheit und Teststatus

- Build, Python-Syntax, JavaScript-Syntax, Paketstruktur, ZIP-Integrität und veröffentlichte SHA-256-Prüfsummen wurden automatisiert geprüft.
- Der Build ist als Testbuild veröffentlicht, da Windows-Anmeldung, produktive NAS-Sitzungen und E-Mail-Versand erst in der realen Installation vollständig getestet werden können.
- Vor Installation ist eine Sicherung der bestehenden `hca_shared.py` und der HCA-Datenbank empfohlen.
- Das WooCommerce-Plugin wurde für 0.13.5 nicht verändert.

## Nächste Ausbaustufen

- Windows Hello als zusätzliche Entsperrung eines vorhandenen HCA-Benutzerkontos
- NFC-Anmeldung über einen Arduino-/USB-NFC-Reader
- Feinere Rollen- und Modulberechtigungen
- Benutzerbezogene Audit-Protokolle für Änderungen an Belegen und Stammdaten
