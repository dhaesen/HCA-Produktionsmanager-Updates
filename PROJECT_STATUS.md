# HCA Produktionsmanager – Projektstatus

Stand: 14. September 2026  
Aktuelle Testversion: **0.13.5**  
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

- Native Startanzeige ab dem ersten WPF-Frame
- Windows Hello als zusätzliche Entsperrung eines vorhandenen HCA-Benutzerkontos
- NFC-Anmeldung über einen Arduino-/USB-NFC-Reader
- Feinere Rollen- und Modulberechtigungen
- Benutzerbezogene Audit-Protokolle für Änderungen an Belegen und Stammdaten
