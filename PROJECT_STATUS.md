# HCA Produktionsmanager – Projektstatus

Stand: 15. September 2026  
Aktuelle Testversion: **0.13.11**  
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


## Version 0.13.6.1 – Angebot, Produktion und Versand

- WooCommerce-Artikel werden im HCA-Artikelstamm anhand der Kombination aus Produkt-ID und exakter SKU identifiziert. Gleiche Artikelnamen führen nicht mehr zur Zusammenführung verschiedener SKUs.
- Die WooCommerce-Suche dedupliziert ausschließlich über technische Identitäten, nicht über den Artikelnamen.
- Angebote unterstützen alternative Mengenstaffeln. Staffelpreise werden je Angebotsposition gespeichert und im PDF als Netto-, Steuer- und Bruttosumme ausgewiesen. Bei der Umwandlung zum Auftrag wird die tatsächlich beauftragte Staffelmenge ausgewählt.
- Die Kundenauswahl in der Angebotserfassung ist nach Kundennummer, Firma, Person und E-Mail durchsuchbar.
- Veredelungsdaten werden beim Übergang vom Angebot zum Auftrag serverseitig normalisiert und vollständig als Produktionsschritte übernommen.
- Bei Aufträgen mit Veredelung wird zwischen Eigenproduktion und Lieferantenproduktion gewählt.
- Eigenproduktion erzeugt einen sichtbaren Vorschlag für Produktionsaufträge; bei Lieferantenproduktion wird kein interner Produktionsauftrag vorgeschlagen.
- Produktionspositionen führen eine Verpackungseinheit. Eine Fertigmeldung kann mehrere Stück buchen und erzeugt dabei genau ein Etikett für die Verpackungseinheit.
- Erzeugte Produktionsaufträge erhalten die Standardlieferadresse aus dem kaufmännischen Auftrag.
- Deutsche Versandadressen werden auf fünfstellige PLZ und passende Ortsnamen geprüft. Ortsnamen werden automatisch ergänzt; Straßenvorschläge werden, soweit verfügbar, über OpenPLZ geladen. Ein Ausfall des externen Dienstes blockiert die Erfassung nicht.
- Lieferschein und Sendung werden über eine bestehende technische Verknüpfung wiederverwendet. Das Erzeugen eines Labels aus dem Lieferschein sowie eines Lieferscheins aus der Sendung erzeugt keinen zweiten Beleg.
- Client- und NAS-Paket wurden mit Python-/JavaScript-Syntaxprüfung, Strukturprüfung, ZIP-Test und SHA-256-Verifikation veröffentlicht.
- Das WooCommerce-Plugin wurde nicht verändert.

### Installation 0.13.6.1

1. NAS-Erweiterung 0.13.6.1 installieren und den NAS-Dienst neu starten.
2. Clientupdate 0.13.6.1 einspielen.
3. HCA manuell schließen und neu starten.
4. Zuerst mit einem Testangebot und einer Testsendung prüfen.


## Version 0.13.7 – Kundensuche, Artikelbilder und Angebotsdatenblätter

- Die Kundenauswahl im Angebotsformular ist jetzt ein einziges durchsuchbares Kombinationsfeld an der bisherigen Dropdown-Position. Es kann weiterhin aufgeklappt oder direkt nach Kundennummer, Firma, Vorname, Nachname und E-Mail durchsucht werden.
- Die zuvor zusätzlich oberhalb des Dropdowns angelegte Suchzeile wurde entfernt.
- Die Artikelsuche in Angebot, Auftrag und Kundenrechnung zeigt zu jedem Treffer ein Produktbild zur eindeutigen Identifikation.
- WooCommerce-Produktdaten liefern neben dem Hauptbild bis zu zehn Produktbilder, vollständige Beschreibung, Kurzbeschreibung, Hersteller, Lieferant, Maße, Gewicht, Kategorien und Attribute an HCA.
- Für jede Angebotsposition kann ein Artikeldatenblatt wahlweise aktiviert und mit ein bis fünf Produktbildern zusammengestellt werden.
- Das Datenblatt enthält die vollständigen gespeicherten Artikeldetails und die komplette Produktbeschreibung.
- Datenblattseiten werden als Bestandteil derselben Angebots-PDF hinter das Angebot angehängt; E-Mails enthalten damit automatisch das vollständige Angebot einschließlich Datenblättern.
- Im nativen WebView2-Client wird der HTML-Ladebildschirm bereits während des Dokumentaufbaus unterdrückt. Dadurch bleibt nur der erste native Startbildschirm sichtbar; der Webtest behält seinen eigenen Ladebildschirm.
- Client- und NAS-Paket werden mit Syntax-, Struktur-, ZIP- und SHA-256-Prüfung veröffentlicht.
- Das WooCommerce-Plugin wurde nicht verändert.

### Installation 0.13.7

1. NAS-Erweiterung 0.13.7 installieren und den NAS-Dienst neu starten.
2. Clientupdate 0.13.7 einspielen.
3. HCA manuell schließen und neu starten.
4. Ein Testangebot mit ausgewähltem Artikeldatenblatt erstellen und dessen PDF prüfen.


## Version 0.13.8 – Robuste Kundensuche und vollständige Artikeldatenblätter

- Das Kundenfeld im Angebotsformular wird unabhängig vom verwendeten Renderpfad als direkt beschreibbares Kombinationsfeld aktiviert.
- Die Suche liest die tatsächlich im Dropdown vorhandenen Kunden und findet Kundennummer, Firma, Vorname, Nachname und E-Mail; Treffer mit passenden Anfangsbuchstaben stehen zuerst.
- Der Lieferant wird in Artikeldatenblättern grundsätzlich nicht mehr ausgegeben, auch nicht bei älteren gespeicherten Angebotsdaten.
- Als Herkunftsangabe erscheint ausschließlich Hersteller beziehungsweise Marke aus WooCommerce.
- Hauptbild und ausgewählte Galeriebilder werden getrennt von den Farbvarianten dargestellt.
- Sämtliche in WooCommerce hinterlegten Farbvarianten werden mit Namen und kleinen Bildern in das Datenblatt übernommen.
- Veredelungspositionen, zulässige Veredelungsarten und vorhandene Positionsbilder werden aus der WooCommerce-Wizard-Konfiguration übernommen.
- Client- und NAS-Paket wurden nach Veröffentlichung erneut per SHA-256 und ZIP-Integritätsprüfung verifiziert.
- Das WooCommerce-Plugin wurde nicht verändert.

### Installation 0.13.8

1. NAS-Erweiterung 0.13.8 installieren und den NAS-Dienst neu starten.
2. Clientupdate 0.13.8 einspielen.
3. HCA vollständig schließen und neu starten.
4. Ein neues Testangebot mit farbigem Artikel und aktiviertem Artikeldatenblatt prüfen.


## Version 0.13.9 – Alte Angebote, Positionsstaffeln und einseitiges Datenblatt

- Der DOM-Fehler beim Öffnen älterer Angebote wurde behoben. Die Kundenauswahl ersetzt das bestehende Feld nun ohne unsichere `insertBefore`-Operation.
- Bestehende Angebotsdaten werden weder verändert noch migriert.
- Jede normale Angebotsposition besitzt eine eigene sichtbare Eingabe für mehrere Mengenstaffeln, beispielsweise 500, 1000 und 1500 Stück.
- Staffelpreise werden positionsbezogen berechnet, tabellarisch angezeigt und zusammen mit der jeweiligen Position gespeichert.
- Das globale, missverständliche Mengenstaffelfeld im Angebotskopf wurde entfernt.
- Pro ausgewähltem Artikel wird genau eine Artikeldatenblattseite erzeugt.
- Das Hauptbild steht links, die Produkteigenschaften und Beschreibung rechts, bis zu fünf Galeriebilder klein darunter.
- Farbvarianten werden kompakt dargestellt; Veredelungspositionen, Verfahren und Positionsbilder stehen im unteren Seitenbereich.
- Der Lieferant wird weiterhin niemals auf dem Artikeldatenblatt ausgegeben.
- Client- und NAS-Paket wurden nach Veröffentlichung mit SHA-256 und ZIP-Integritätsprüfung verifiziert.
- Das WooCommerce-Plugin wurde nicht verändert.

### Installation 0.13.9

1. NAS-Erweiterung 0.13.9 installieren und den NAS-Dienst neu starten.
2. Clientupdate 0.13.9 einspielen.
3. HCA vollständig schließen und neu starten.
4. Ein älteres Angebot sowie ein neues Angebot mit mehreren Positionsstaffeln und Artikeldatenblatt prüfen.


## Version 0.13.10 – Alternative Angebotsmengen und neues Datenblatt

- Die in 0.13.9 eingeführte separate Mengenstaffeltabelle wurde vollständig aus dem Client und der PDF-Ausgabe entfernt.
- Bei normalen Werbeartikelpositionen können direkt am vorhandenen Mengenbereich beliebig viele weitere Angebotsmengen ergänzt werden.
- Jede weitere Menge erzeugt automatisch eine optionale Zusatzposition.
- Die Zusatzposition übernimmt Artikel, Farbe, Beschreibung und sämtliche Veredelungsschritte der Ausgangsposition.
- Produkt-, Druck-, Einrichtungs- und Bearbeitungspreise werden für jede zusätzliche Menge erneut über die vorhandene WooCommerce-Preislogik berechnet.
- Automatisch erzeugte Mengenoptionen sind als optionale Positionen gekennzeichnet und werden nicht in die Angebotssumme eingerechnet.
- Beim Speichern werden Mengenoptionen nochmals aus der aktuellen Ausgangsposition aufgebaut, damit nachträgliche Änderungen an Artikel oder Veredelung übernommen werden.
- Das Artikeldatenblatt wurde vollständig neu aufgebaut und erzeugt pro ausgewähltem Artikel genau eine Seite.
- Seitenaufteilung: Hauptbild links, Eigenschaften und Beschreibung rechts, kleine Galeriebilder direkt darunter, kompakte Farbvariantenübersicht sowie Veredelungspositionen mit Bildern und möglichen Verfahren im unteren Seitenbereich.
- Der Lieferant wird niemals auf dem Artikeldatenblatt ausgegeben; zulässig ist ausschließlich Hersteller beziehungsweise Marke.
- Das PDF-Layout wurde vor Veröffentlichung als A4-Seite gerendert und visuell geprüft.
- Client- und NAS-Paket wurden nach Veröffentlichung mit SHA-256 und ZIP-Integritätsprüfung verifiziert.
- Das WooCommerce-Plugin wurde nicht verändert.

### Installation 0.13.10

1. NAS-Erweiterung 0.13.10 installieren und den NAS-Dienst neu starten.
2. Clientupdate 0.13.10 einspielen.
3. HCA vollständig schließen und neu starten.
4. Einen Werbeartikel auswählen, über „Weitere Menge“ mindestens zwei Alternativmengen anlegen und das PDF einschließlich Datenblatt prüfen.


## Version 0.13.11 – Zuverlässige Veredelungspreise

- Gleichzeitige beziehungsweise verspätete WooCommerce-Preisabfragen können neuere Mengen-, Druckpositions- oder Veredelungseingaben nicht mehr überschreiben.
- Vor jeder Preisberechnung werden Druckposition und Veredelungsart erneut mit der WooCommerce-Wizard-Konfiguration abgeglichen.
- Eine Preisantwort gilt nur als vollständig, wenn für jeden automatisch kalkulierten Veredelungsschritt eine Preisposition zurückgegeben wurde.
- Kurzzeitige Fehler der WooCommerce-Druckkalkulation werden einmal automatisch wiederholt.
- Bei gewählten Veredelungen gibt es keinen stillen Rückfall mehr auf den reinen Artikelpreis mit 0,00-Euro-Veredelungen.
- Ladezustand, erfolgreicher Abruf und Fehler erscheinen direkt an der betroffenen Dokumentposition.
- Eine fehlgeschlagene Kalkulation kann mit „Erneut laden“ gezielt wiederholt werden; vorhandene gültige Preise werden bei einem Fehler nicht gelöscht.
- Der reine WooCommerce-Artikelpreis bleibt nur für Positionen ohne Veredelung als zulässiger Fallback erhalten.
- Client- und NAS-Paket wurden nach Veröffentlichung mit Funktionstest, Python-/JavaScript-Syntaxprüfung, SHA-256 und ZIP-Integritätsprüfung verifiziert.
- Das WooCommerce-Plugin wurde nicht verändert.

### Installation 0.13.11

1. NAS-Erweiterung 0.13.11 installieren und den NAS-Dienst neu starten.
2. Clientupdate 0.13.11 einspielen.
3. HCA vollständig schließen und neu starten.
4. Einen Artikel mit mindestens einer Veredelung auswählen, Menge und Veredelungsart wechseln und prüfen, ob der grüne Hinweis zur vollständigen Preisübernahme erscheint.
