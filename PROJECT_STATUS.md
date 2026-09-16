# HCA Produktionsmanager – Projektstatus

Stand: 16. September 2026
Aktuelle Testversion: **0.13.25**
Quellbranch: `codex/v0.13.25`

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

## Version 0.13.13 – Veredelungspreise wiederhergestellt

- Die in 0.13.11 eingeführte automatische Neuzuordnung von Druckart-, Einrichtungs- und Bearbeitungskosten-IDs wurde zurückgenommen.
- Bereits im Angebot gespeicherte WooCommerce-IDs bleiben beim Öffnen und Neuberechnen unverändert und werden wieder direkt an die Druckpreisverwaltung übergeben.
- Fehlende IDs werden nur noch ergänzt, wenn die Zuordnung zu genau einer Veredelungsart eindeutig ist.
- Manuelle Veredelungen bleiben von der WooCommerce-Preisabfrage ausgeschlossen und verschieben die Zuordnung der automatisch berechneten Positionen nicht.
- Die Zahl der vom Shop gelieferten Preispositionen wird weiterhin geprüft; unvollständige Antworten werden nicht als erfolgreiche 0,00-Euro-Kalkulation angezeigt.
- Eine ausschließlich aus 0,00-Euro-Werten bestehende WooCommerce-Antwort wird als Zuordnungsfehler angezeigt und überschreibt keine zuvor geladenen Preise.
- Das WooCommerce-Plugin wurde nicht verändert.

## Version 0.13.14 – Beschädigte Preiszuordnungen repariert

- Die Wizard-Konfiguration wird vor der Veredelungskalkulation frisch aus WooCommerce geladen.
- Bereits auf 0 gesetzte oder falsch zugeordnete Druckart-, Einrichtungs- und Bearbeitungskosten-IDs werden anhand von Druckposition und Verfahren repariert.
- Die Preisabfrage verwendet die WooCommerce-ID des Hauptartikels und prüft Druck-, Einrichtungs- und Bearbeitungspreis einzeln.
- Unvollständige Shopantworten überschreiben keine vorhandenen Angebotswerte.
- Nach erfolgreicher Neuberechnung erscheinen Produkt, Veredelung, Einrichtung und Bearbeitung wieder als getrennte Angebotspositionen.
- Es ist kein NAS-Update erforderlich.
- Das WooCommerce-Plugin wurde nicht verändert.

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


## Version 0.13.15 – Rettungsupdate Preisberechnung und Produktionsgrößen

- Die fehlerhaften Client-Preisüberschreibungen aus 0.13.11 bis 0.13.14 werden nicht mehr geladen.
- Die WooCommerce-Preisberechnung verwendet wieder den bis 0.13.10 bewährten Ablauf.
- Produktpreis, Druckpreis, Einrichtungskosten und Bearbeitungskosten werden wieder getrennt aus der WooCommerce-Druckpreisverwaltung übernommen.
- Bereits bestehende Angebote mit Veredelungen werden beim Öffnen neu kalkuliert. Die gespeicherten Daten ändern sich erst, wenn der Benutzer selbst speichert.
- Die zusätzlich eingeführte Verpackungseinheit schneidet im Produktionsmonitor die Größenbezeichnung nicht mehr ab. Größen bleiben auch bei geringer Fensterhöhe sichtbar.
- Das Update verändert weder das WooCommerce-Plugin noch die HCA-Datenbank.

### Installation 0.13.15

1. Nur das Clientupdate 0.13.15 einspielen; eine NAS-Erweiterung ist nicht erforderlich.
2. HCA vollständig schließen und manuell neu starten.
3. Ein vorhandenes Angebot mit Veredelung öffnen und prüfen, dass Produkt, Veredelung, Einrichtung und Bearbeitung wieder einzeln erscheinen.
4. Einen Textil-Produktionsauftrag öffnen und die Größenanzeige prüfen.


## Version 0.13.16 – Exakte Preisrücksetzung auf v0.13.6.1

- Der vollständige Vergleich der Releases vom 14. und 15. September hat gezeigt: `app.js` und die NAS-Preisfunktionen blieben von 0.13.2 bis 0.13.10 unverändert; die erste eigene Preisüberschreibung wurde mit 0.13.11 eingeführt.
- Die Rücksetzung in 0.13.15 war nicht identisch mit dem funktionierenden Stand: Sie ordnete gespeicherte WooCommerce-Preis-IDs vor jeder Kalkulation erneut zu und konnte dadurch die gewählte Druckart sowie Einrichtungs- und Bearbeitungskosten ersetzen.
- 0.13.16 übernimmt die effektive `hca103ShopPrice`-Routine aus 0.13.6.1 wortgleich.
- Vorhandene `druckart_id`, `cost_id` und `bearbeitung_cost_id` bleiben erhalten.
- Druckpreis, Einrichtungskosten und Bearbeitungskosten werden wieder getrennt aus der WooCommerce-Antwort übernommen.
- Der Größenanzeige-Fix aus 0.13.15 bleibt erhalten.
- WooCommerce-Plugin, NAS-Server und Datenbank werden nicht verändert.

### Installation 0.13.16

1. Nur das Clientupdate 0.13.16 einspielen.
2. HCA vollständig schließen und manuell neu starten.
3. Zuerst ein gestern funktionierendes Angebot öffnen und „Shoppreise aktualisieren“ ausführen.
4. Prüfen, dass Produkt, Veredelung, Einrichtung und Bearbeitung wieder als vier Preisbestandteile erscheinen.


## Version 0.13.17 – NAS-Hotfix Veredelungspreise

- Nach der exakten Client-Rücksetzung 0.13.16 blieb der Fehler bestehen; die Ursache liegt damit in der NAS-Preisübergabe beziehungsweise in den dort verarbeiteten Daten.
- Der NAS-Server wertete den Textwert `"false"` bei `manual_override` durch `bool("false")` fälschlich als wahr und konnte dadurch reguläre Veredelungsschritte aus der WooCommerce-Preisanfrage entfernen.
- Druckart-, Einrichtungs- und Bearbeitungskosten-IDs werden serverseitig gegen die aktuelle, nur lesend abgerufene WooCommerce-Wizardkonfiguration geprüft und bei eindeutiger Zuordnung vervollständigt.
- Eine WooCommerce-Antwort mit 0,00 EUR für Druck, Einrichtung und Bearbeitung wird bei ausgewählter Veredelung nicht mehr als erfolgreiche Kalkulation akzeptiert.
- Fehlermeldungen enthalten die tatsächlich übertragenen IDs, damit eine verbleibende falsche Zuordnung eindeutig erkennbar ist.
- WooCommerce-Plugin und HCA-Datenbank werden nicht verändert.

### Installation 0.13.17

1. Bestehende `app/hca_shared.py` auf dem NAS sichern.
2. Die Datei aus dem NAS-Hotfix ersetzen.
3. HCA-NAS-Dienst beziehungsweise Container neu starten.
4. Client 0.13.16 verwenden, betroffenes Angebot öffnen und „Shoppreise aktualisieren“ ausführen.


## Version 0.13.18 – Rückbau Mengenfelder und Client-Preisreparatur

- Die mit 0.13.10 eingeführte Erweiterung für zusätzliche Angebotsmengen wurde vollständig aus dem Clientpaket entfernt.
- Der eigentliche Preisfehler lag zusätzlich im Client: Der Textwert `"false"` bei `manual_override` wurde durch JavaScript als wahr behandelt. Automatische Veredelungen wurden dadurch bereits vor dem NAS-Aufruf ausgesondert.
- `manual_override` wird nun typgerecht normalisiert. Nur echte Wahrwerte kennzeichnen eine manuelle Abweichung.
- Druckpreis, Einrichtungskosten und Bearbeitungskosten werden wieder vollständig aus der Preisantwort auf den jeweiligen Veredelungsschritt übertragen.
- Eine unvollständige Preisantwort wird nicht mehr stillschweigend akzeptiert.
- Bereits gespeicherte Dokumentpositionen und manuelle Positionen werden nicht gelöscht oder verändert.
- NAS, WooCommerce-Plugin und Datenbank werden durch das Clientupdate nicht verändert.

### Installation 0.13.18

1. Clientupdate 0.13.18 einspielen.
2. HCA vollständig schließen und manuell neu starten.
3. Ein betroffenes Angebot öffnen und „Shoppreise aktualisieren“ ausführen.
4. Prüfen, dass Produkt, Veredelung, Einrichtung und Bearbeitung wieder als getrennte Preisbestandteile erscheinen.


## Version 0.13.21 – Produktstaffeln, Mengenoptionen und Farbvarianten

- Die funktionierende Veredelungspreisberechnung aus 0.13.20 bleibt unverändert erhalten.
- Vor jeder Shopkalkulation lädt der Client die aktuelle WK-Produktkonfiguration neu.
- Artikelstaffelpreise werden für jede angefragte Menge durch den WK-Werbeartikelkonfigurator berechnet.
- Die unter „Mengenstaffel“ eingetragenen Zusatzmengen werden als echte optionale Angebotspositionen angelegt.
- Für jede Zusatzmenge werden Produktpreis, Druckpreis, Einrichtungskosten und Bearbeitungskosten separat neu berechnet.
- Automatische Mengenoptionen werden nicht in die Gesamtsumme des Angebots eingerechnet.
- Alte Staffel-Vorschauwerte werden beim Neuaufbau entfernt; manuell angelegte optionale Positionen bleiben erhalten.
- Die NAS-Erweiterung löst die vom WK-Konfigurator gespeicherten Farb-Bild-IDs über die WooCommerce-Produktbilder auf.
- Das einseitige Artikeldatenblatt kann dadurch alle gepflegten Farbvarianten darstellen.
- Das WooCommerce-Plugin und die HCA-Datenbank werden nicht verändert.

### Installation 0.13.21

1. Vorhandene `app/hca_shared.py` auf dem NAS sichern.
2. NAS-Erweiterung 0.13.21 installieren und den NAS-Dienst neu starten.
3. Clientupdate 0.13.21 einspielen.
4. HCA vollständig schließen und manuell neu starten.
5. Einen Werbeartikel mit Produkt- und Druckstaffeln öffnen, Zusatzmengen berechnen und Dokumentvorschau samt Datenblatt prüfen.
# HCA v0.13.22 – Positionsgruppen und Rückbau Mengenstaffel (16.09.2026)

- Der Angebotsbereich „Mengenstaffel“ ist vollständig entfernt.
- Automatisch erzeugte Mengenoptionen werden beim Öffnen bzw. Speichern entfernt; manuelle optionale Positionen bleiben erhalten.
- Produkt, Veredelung, Einrichtung und Bearbeitung werden in kaufmännischen PDFs als eine Positionsgruppe behandelt.
- Nummerierung innerhalb einer Gruppe: `1.1`, `1.2`, `1.3` usw.; nächste Gruppe: `2.1` usw.
- Innerhalb einer Gruppe gibt es keine waagerechten Trennlinien. Der Gruppenabschluss erhält eine stärkere Linie.
- Positionsgruppen werden nach Möglichkeit vollständig auf derselben PDF-Seite gehalten.
- Abwärtskompatibel für bestehende Angebote, Aufträge und Rechnungen; keine Datenmigration.
- WooCommerce-Plugin und HCA-Datenbank bleiben unverändert.

# HCA v0.13.23 – Positionen nachträglich optional stellen (16.09.2026)

- Jede bereits angelegte Angebotsposition erhält im Positionskopf einen Schalter „Optional“.
- Beim Aktivieren wird die gesamte Positionsgruppe einschließlich Veredelung, Einrichtung und Bearbeitung optional.
- Optionale Gruppen bleiben mit Preisen sichtbar, werden aber nicht in die Angebotssummen eingerechnet.
- Der Schalter kann wieder deaktiviert werden; die Position wird dann erneut regulär summiert.
- Festgeschriebene Angebote bleiben unveränderbar.
- WooCommerce-Plugin, NAS-Server und Datenbank bleiben unverändert.

# HCA v0.13.24 – Lieferadressen und personalisierte Serienproduktion (16.09.2026)

- Aus Kundenaufträgen erzeugte Produktionsaufträge übernehmen die dort gespeicherte Lieferadresse nun auch in die zentrale HCA-Versandverwaltung.
- Bei manuell angelegten Produktionsaufträgen sind „Auftragsnummer“ und „Kunde“ durchsuchbare Eingabefelder mit Trefferliste.
- Die Auswahl eines Kunden übernimmt dessen Standardlieferadresse; die Auswahl eines Auftrags übernimmt dessen Lieferadress-Snapshot und zugehörigen Kunden.
- Drei versehentlich als Text ausgelieferte `\n`-Zeichenfolgen werden aus `index.html` entfernt.
- Merch-, Einzelversand- und anderweitig personalisierte Produktionsaufträge erhalten eine eigene Serienansicht mit Fertig-/Offen-Zahlen je Größe.
- Nach Auswahl einer Größe wird das nächste offene Textil mit Personalisierung/Standort und vorgeschlagenem Dateinamen angezeigt.
- Vier Maschinen- beziehungsweise Transferplatz-Slots zeigen die aktuell laufenden Textilien.
- Erfolgreiche Stickdateiübertragungen werden dem gewählten Maschinenslot zugeordnet.
- Ein Klick auf einen belegten Slot verwendet die bestehende Fertigmeldelogik einschließlich Artikeletikett und Versandvorbereitung.
- Standort- und Teamnamen werden pro physischem Textil im vorhandenen Personalisierungsfeld gespeichert. Damit sind beispielsweise drei Textilien „Berlin“ und vier Textilien „Köln“ getrennt nachvollziehbar.
- Das WooCommerce-Plugin wird nicht verändert.

### Installation 0.13.24

1. Vorhandene `app/hca_shared.py` auf dem NAS sichern.
2. NAS-Erweiterung 0.13.24 installieren und den NAS-Dienst/Container neu starten.
3. Clientupdate 0.13.24 einspielen.
4. HCA vollständig schließen und manuell neu starten.

# HCA v0.13.25 – Einheitliche Positionserfassung und automatische Shoppreise (16.09.2026)

- Auftrag und Kundenrechnung verwenden wieder denselben vollständigen Positionsrenderer wie das Angebot.
- Artikelsuche, Farbauswahl, Größen und Mengen, mehrere Veredelungen, Druckpositionen, Veredelungsarten, Druckfarben und die Preisaufschlüsselung sind damit in Angebot, Auftrag und Rechnung einheitlich.
- Das Hinzufügen oder Entfernen einer Veredelung löst automatisch eine neue Shopkalkulation aus.
- Änderungen an Menge, Größenmengen, Druckposition, Veredelungsart oder Druckfarben lösen die Kalkulation ebenfalls automatisch und zeitverzögert aus.
- Die funktionierende WooCommerce-Preiszuordnung aus v0.13.20/v0.13.21 wurde nicht verändert.
- „Shoppreise aktualisieren“ bleibt als manuelle Rückfallebene erhalten.
- WooCommerce-Plugin, NAS-Server und Datenbank werden nicht verändert.

### Installation 0.13.25

1. Nur das Clientupdate 0.13.25 einspielen; ein NAS-Update ist nicht erforderlich.
2. HCA vollständig schließen und manuell neu starten.
3. Im Angebot eine Veredelung hinzufügen und danach die Menge ändern.
4. Prüfen, dass Druckpreis, Einrichtungskosten und Bearbeitungskosten ohne Betätigung von „Shoppreise aktualisieren“ neu erscheinen.
5. Danach je eine neue Auftrag- und Rechnungsposition öffnen und die identische Positionsmaske prüfen.

# HCA NAS v0.13.26 – Textilbilder im Artikeldatenblatt (16.09.2026)

- Ursache: Werbeartikel speichern ihre Farbbilder am Hauptartikel; variable Textilien speichern das jeweilige Bild dagegen an den WooCommerce-Varianten. Die PDF-Erzeugung wertete bisher nur die Hauptartikel-Farbliste zuverlässig aus.
- Beim Erzeugen eines Artikeldatenblatts liest der NAS-Server für variable Textilien nun die Variantenbilder aus WooCommerce ein.
- Varianten derselben Farbe und desselben Bildes werden zusammengeführt, damit Größenvarianten keine Bildduplikate erzeugen.
- Alle eindeutigen Farbbilder werden im Bereich „Farbvarianten“ des weiterhin einseitigen Datenblatts ausgegeben.
- Die Ergänzung funktioniert auch für ältere Angebote, weil die Bilder beim Erzeugen der PDF nachgeladen werden.
- Der Bildabruf unterstützt typische WebP-/AVIF-Konvertierungen besser und probiert bei konvertierten Dateinamen zusätzlich das ursprüngliche JPEG-/PNG-Bild.
- Lieferantendaten werden weiterhin nicht auf dem kundenseitigen Artikeldatenblatt ausgegeben; sichtbar bleibt ausschließlich Hersteller beziehungsweise Marke.
- Client v0.13.25, WooCommerce-Plugin, Druckpreise, Angebotsberechnung und Datenbank bleiben unverändert.

### Installation 0.13.26

1. Vorhandene `app/hca_shared.py` auf dem NAS sichern.
2. NAS-Erweiterung 0.13.26 über die bestehende NAS-Installation kopieren.
3. HCA-Dienst beziehungsweise Container auf der Synology neu starten.
4. Ein Angebot mit einem variablen Textil und Artikeldatenblatt in der Dokumentenvorschau prüfen.

# HCA v0.13.27 – schnelle und kompatible Textilbilder (16.09.2026)

- Das Containerprotokoll belegt für v0.13.26 einen Vorschauaufruf von rund 54 Sekunden. Ursache waren synchrone WooCommerce-Variantenabfragen und mehrere nacheinander ausgeführte Bildabrufe.
- Die PDF-Erzeugung fragt beim Vorschauaufbau keine WooCommerce-Varianten mehr live ab. Sie verwendet die bereits im Angebotseditor geladenen und gespeicherten Produktdetails.
- WebP-/AVIF-Textilbilder werden im WebView2-Client in PDF-kompatible JPEGs umgewandelt.
- Die JPEGs werden persistent unter `/data/hca_datasheet_images` auf der NAS zwischengespeichert. Spätere Vorschauen verwenden den Cache direkt.
- Verarbeitet werden nur Hauptbild, höchstens fünf tatsächlich dargestellte Galeriebilder, die eindeutigen Farbvarianten und die dargestellten Veredelungsbilder. Unbenutzte Größen- und Variantendubletten werden nicht geladen.
- Ein nicht erreichbares Einzelbild blockiert die Dokumentenvorschau nicht mehr; externe Bildabrufe besitzen kurze feste Zeitgrenzen.
- Lieferantendaten bleiben im Kundendatenblatt ausgeschlossen.
- WooCommerce-Plugin, Druckpreislogik, Produktdaten und HCA-Datenbank werden nicht verändert.

### Installation 0.13.27

1. Vorhandene `app/hca_shared.py` auf der NAS sichern.
2. NAS-Erweiterung 0.13.27 installieren und den HCA-Container neu starten.
3. Clientupdate 0.13.27 einspielen.
4. HCA vollständig schließen und manuell neu starten.
5. Ein Textilangebot mit aktiviertem Artikeldatenblatt öffnen und die Dokumentenvorschau erzeugen. Der erste Lauf baut den Bildcache auf; weitere Vorschauen verwenden diesen Cache.

### Prüfsummen-Korrektur 0.13.27

- Der erste Release enthielt sowohl für das Clientupdate als auch für die NAS-Erweiterung eine Datei mit der Endung `.sha256`.
- Der bestehende HCA-Updater unterscheidet diese Prüfsummendateien nicht zuverlässig und konnte deshalb die NAS-Prüfsumme gegen das Clientupdate prüfen.
- Im Release bleibt künftig ausschließlich die Client-Prüfsumme als `.sha256` erhalten. Die NAS-Prüfsumme wird als `HCA_NAS_Erweiterung_v0.13.27_CHECKSUM.txt` veröffentlicht.
- Client- und NAS-Paket selbst werden durch diese Korrektur nicht verändert.
