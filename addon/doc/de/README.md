# NVDA Script Manager

Der NVDA Script Manager ist eine NVDA-Erweiterung mit eigenem Editor zum Erstellen und Bearbeiten von Python-Skripten (AppModules und weitere NVDA-Modultypen).

Diese Dokumentation beschreibt den gesamten Funktionsumfang aus Sicht von Benutzerinnen und Benutzern.

## Zweck der Erweiterung

Mit dem Script Manager kannst du:

- das AppModule der aktuell fokussierten Anwendung sofort öffnen,
- neue NVDA-Modulvorlagen erzeugen,
- bestehende Skripte bearbeiten und speichern,
- Funktionen/Methoden mit Hilfe-Text einfügen,
- neue Script-Methoden per Assistent erstellen,
- Fehler im Skript prüfen und direkt zur fehlerhaften Zeile springen.

## Voraussetzungen

- NVDA (Scratchpad wird bei Bedarf je nach Einstellung automatisch aktiviert oder es wird nachgefragt).
- Schreibrechte auf den NVDA-Benutzerordner.

## Globale Tastenkombinationen

- NVDA+Umschalt+0: Script-Manager-Fenster für die aktuell fokussierte Anwendung öffnen.
- NVDA+Umschalt+R: Beschriftungsregel für das aktuelle Navigatorobjekt erstellen und im AppModule speichern.

## NVDA-Menü-Integration

- NVDA-Menü → Werkzeuge → Script Manager: öffnet den Script Manager direkt mit einer leeren Datei.
- NVDA-Menü → Einstellungen → Script Manager-Beschriftungsmethoden: Dialog zur Konfiguration und Priorisierung der automatischen Beschriftungsmethoden.
- NVDA-Einstellungen → Script Manager: Einstellungskategorie für den Script Manager.

## Verhalten beim Öffnen mit NVDA+Umschalt+0

Beim Öffnen für die fokussierte Anwendung passiert automatisch Folgendes:

1. Der Prozessname der aktiven Anwendung wird ermittelt.
2. Wenn noch kein NVDA-AppModule existiert, wird im Scratchpad ein neues AppModule erstellt.
3. Wenn ein AppModule in NVDA/Add-on vorhanden ist, aber nicht im Benutzerordner, wird es in den Benutzerordner kopiert.
4. Das Ergebnis wird im Script-Manager-Editor geöffnet.

Dadurch kannst du vorhandene Logik schnell übernehmen und lokal anpassen.

Wenn Scratchpad deaktiviert ist, greift die Scratchpad-Policy aus den Script-Manager-Einstellungen:

- Nachfragen (Standard): Es erscheint eine Sicherheitsabfrage mit Ja/Nein und "Diese Nachfrage nicht erneut anzeigen".
- Ja: Scratchpad wird aktiviert.
- Ja + "nicht erneut anzeigen": Scratchpad wird ab jetzt bei Bedarf automatisch aktiviert.
- Nein: Scratchpad bleibt deaktiviert.
- Nein + "nicht erneut anzeigen": Scratchpad bleibt dauerhaft deaktiviert und die Nachfrage erscheint nicht mehr.

## Script-Manager-Fenster

Das Fenster öffnet sich bildschirmfüllend und enthält einen mehrzeiligen Editor.

### Menü Datei

- Neu: Leere Datei (Ctrl+N)
- Neu: AppModule-Vorlage
- Neu: GlobalPlugin-Vorlage
- Neu: BrailleDisplayDriver-Vorlage
- Neu: SynthDriver-Vorlage
- Neu: VisionEnhancementProvider-Vorlage
- Öffnen (Ctrl+O)
- Speichern (Ctrl+S)
- Speichern unter (Ctrl+Umschalt+S)
- Add-on erstellen…
- Beenden (Alt+F4)

**Add-on erstellen (zweistufig):**

1. Der Assistent fragt Manifest-Daten ab und bereitet einen temporären Add-on-Ordner vor.
2. Anschließend wirst du gefragt: „Jetzt abschließen" oder „Ordner öffnen" (um vor dem Verpacken zusätzliche Dateien einzufügen). Nach dem Öffnen erscheint ein Hinweisdialog, der sich dauerhaft deaktivieren lässt.
3. Nach dem Abschließen wird das fertige `.nvda-addon`-Paket erstellt; du kannst es direkt zum Testen installieren.

Bei ungespeicherten Änderungen wirst du vor Neu/Öffnen/Beenden gefragt, ob gespeichert werden soll.

### Menü Bearbeiten

- Rückgängig (Ctrl+Z)
- Wiederholen (Ctrl+Y)
- Ausschneiden (Ctrl+X)
- Kopieren (Ctrl+C)
- Einfügen (Ctrl+V)
- Alles markieren (Ctrl+A)
- Löschen
- Funktion einfügen (Ctrl+I)
- Suchen (Ctrl+F)
- Weitersuchen (F3)
- Rückwärts suchen (Umschalt+F3)
- Ersetzen (Ctrl+H)
- Gehe zu Zeile (Ctrl+G)


### Menü Scripts

- Neues Script erzeugen (Ctrl+E)
- Nächste Scriptdefinition (F2)
- Nächster Fehler (Alt+Pfeil runter)
- Voriger Fehler (Alt+Pfeil hoch)
- Scriptfehler prüfen (Ctrl+Umschalt+E)
- Vorige Scriptdefinition (Umschalt+F2)

### Menü Hilfe

- Informationen über den Script Manager

## Assistent: Neues Script (Ctrl+E)

Der Assistent erzeugt eine fertige Script-Methode als Vorlage.

Erfasste Felder:

- Script-Name
- Beschreibung
- Tastenkombinationen (Gesten-Liste mit Hinzufügen/Bearbeiten/Löschen)
- Kategorie

**Mehrere Gesten:** Du kannst beliebig viele Tastenkombinationen pro Script hinzufügen. „Hinzufügen (Ins)" aktiviert den Erfassungsmodus – drücke dann die gewünschte Taste. Mit „Bearbeiten" oder Doppelklick änderst du eine bestehende Geste, mit „Löschen (Entf)" entfernst du sie. Im Listenfeld sind Einfg, Entf und Eingabe als Tastaturkürzel belegt.

**Erweiterte Script-Optionen** (eigener Bereich im Dialog):

- Script kann an Fokus-Vorfahren weitergegeben werden (`canPropagate`)
- Eingabehilfe umgehen (`bypassInputHelp`)
- Im Schlaf-Modus erlaubt (`allowInSleepMode`)
- Im Auf-Anfrage-Modus sprechen (`speakOnDemand`)
- Alles-Lesen-Modus fortsetzen (`resumeSayAllMode`): leer, `sayAll.CURSOR_CARET` oder `sayAll.CURSOR_REVIEW`

Unterstützte Script-Kategorien:

- Miscellaneous
- Browse mode
- Emulated system keyboard keys
- Text review
- Object navigation
- System caret
- Mouse
- Speech
- Configuration
- Configuration profiles
- Braille
- Vision
- Tools
- Touch screen
- System focus
- System status
- Input
- Document formatting

Aus den Eingaben wird automatisch ein `@script`-Dekorator samt Methodenstub erstellt.

## Dialog: Funktion einfügen (Ctrl+I)

Der Einfüge-Dialog zeigt geladene Python-Module als Baumstruktur.

Du kannst auswählen:

- Module (Import-Zeile wird eingefügt),
- Funktionen,
- Klassen,
- Methoden.

Zusätzlich wird zu selektierten Elementen vorhandene Dokumentation (Docstring) angezeigt.

Über die Script-Manager-Einstellungen kann der Dialog erweitert werden:

- Modul-Blacklist in "Funktion einfügen" einschließen: zeigt auch standardmäßig ausgeblendete Module im Baum an.
- Docstrings übersetzen: übersetzt die angezeigten Docstrings automatisch mit Google Translate (Quellsprache: automatisch, Zielsprache: NVDA-Oberflächensprache).

Hinweis: Das Einblenden geblacklisteter Module kann die Performance im Dialog verschlechtern.

## Einstellungen (NVDA-Einstellungen → Script Manager)

Im NVDA-Einstellungsdialog gibt es die Kategorie "Script Manager" mit folgenden Optionen:

- Scratchpad bei Bedarf aktivieren:
  Nachfragen (Standard)
  Ja (immer automatisch aktivieren)
  Nein (nie aktivieren)
- Modul-Blacklist in "Funktion einfügen" einschließen
- Docstrings übersetzen
- Add-on-Ordner-Hinweis anzeigen: zeigt beim Öffnen des temporären Add-on-Ordners (während der Add-on-Erstellung) einen Hinweisdialog an; kann dauerhaft deaktiviert werden.

Wenn "Scratchpad bei Bedarf aktivieren" auf "Nein" steht und Scratchpad deaktiviert ist, werden alle Scratchpad-pflichtigen Menüpunkte automatisch ausgegraut.

## Fehlerprüfung und Fehlernavigation

Die Fehlerprüfung ist mehrstufig:

1. Syntaxprüfung mit Python `compile()`
2. Kompilierungsprüfung mit `py_compile`
3. Laufzeitprüfung durch kontrollierte Ausführung
4. Zusätzliche Fehler aus NVDAs Logging (ERROR/CRITICAL)

Wenn Fehler gefunden werden:

- wird die Anzahl gemeldet,
- zur jeweiligen Zeile gesprungen,
- die Meldung in Statusleiste und Sprachausgabe ausgegeben,
- mit Alt+Pfeil runter/hoch zyklisch durch alle Fehler navigiert.

Hinweis: Wenn du direkt Alt+Pfeil runter/hoch drückst, ohne vorher manuell zu prüfen, startet die Prüfung automatisch.

## Beschriftungsfunktion für unbeschriftete Objekte (NVDA+Umschalt+R)

Mit `NVDA+Umschalt+R` wird eine Beschriftungsregel für das aktuelle **Navigatorobjekt** erstellt und direkt im AppModule der fokussierten Anwendung gespeichert. Das NVDA-Navigatorobjekt ist das Objekt, auf dem du dich mit der NVDA-Objektnavigation befindest (nicht zwingend das Tastaturfokus-Objekt).

Wichtig: Wenn der Navigator dem Tastaturfokus folgt, löse ihn vor dem Beschriften zuerst mit `NVDA+7` (obere Ziffernreihe) vom Fokus. Dadurch werden die Vorschau-Namen korrekt ermittelt und die manuellen Beschriftungsmethoden funktionieren zuverlässig.

### Beschriftungsmethoden

Die Erweiterung versucht automatisch, die beste Methode zu ermitteln.

**Einmaliges Drücken (NVDA+Umschalt+R):**
Die beste verfügbare automatische Methode wird sofort angewendet – auch wenn das Objekt bereits einen Namen hat. Ist keine automatische Methode verfügbar, erscheint eine Auswahlliste mit den manuellen Methoden.

**Doppeltes Drücken (NVDA+Umschalt+R, NVDA+Umschalt+R):**
Es erscheint immer das vollständige Auswahlmenü mit allen verfügbaren automatischen Methoden (jeweils mit Vorschau des ermittelten Textes) sowie den manuellen Methoden – unabhängig davon, ob das Objekt bereits einen Namen hat. So lässt sich jedes Objekt auch dann neu beschriften, wenn es schon einen (möglicherweise ungeeigneten) Namen trägt.

#### Automatische Methoden (werden ohne Rückfrage angewendet, wenn verfügbar)

| Code | Beschreibung |
|------|--------------|
| A | Text-Kindobjekte (liest untergeordnete Textobjekte aus) |
| B | OneCore OCR (liest den Text per optischer Zeichenerkennung) |
| C | UIA Automation ID (nutzt die eindeutige Steuerelement-ID) |

Welche automatischen Methoden aktiv sind und in welcher Priorität sie angewendet werden, lässt sich unter NVDA → Einstellungen → Beschriftungsmethoden konfigurieren.

#### Manuelle Methoden (erscheinen nur in der Auswahlliste oder wenn keine automatische Methode greift)

| Code | Beschreibung |
|------|--------------|
| D | Statischer Beschriftungstext (du gibst den Text selbst ein; nur verfügbar, wenn das Objekt eine eindeutige Steuerelement-ID hat) |
| E | Objektpfad-basiert (du definierst den Pfad zum Zielobjekt per Navigationsschritten) |

### Dialog „Objektpfad definieren" (Methode E)

Beim Wählen von Methode E öffnet sich ein Dialog, in dem du schrittweise den Navigationspfad zum Zielobjekt aufbaust.

**Schaltflächen im Dialog:**

- ← previous: Geschwisterobjekt davor
- → next: Geschwisterobjekt danach
- ↑ parent: Elternobjekt
- ↓ firstChild: Erstes Kindobjekt
- ↓ lastChild: Letztes Kindobjekt
- Letzten Schritt entfernen
- Pfad leeren

**Tastaturkürzel im Dialog (dialogweit, kein Fokus auf einer Schaltfläche erforderlich):**

| Taste | Aktion |
|-------|--------|
| Pfeil rechts | Schritt „next" (nächstes Geschwisterobjekt) hinzufügen |
| Pfeil links | Schritt „previous" (vorheriges Geschwisterobjekt) hinzufügen |
| Pfeil runter | Schritt „firstChild" (erstes Kind) hinzufügen |
| Umschalt+Pfeil runter | Schritt „lastChild" (letztes Kind) hinzufügen |
| Pfeil hoch | Schritt „parent" (Elternobjekt) hinzufügen |
| Eingabe / Numpad-Eingabe | Pfad bestätigen (OK); nur aktiv wenn mindestens ein Schritt vorhanden ist |
| Entf | Gesamten Pfad leeren |
| Rücktaste | Letzten Schritt entfernen |
| Esc | Abbrechen |

Nach jedem Navigationsschritt gibt NVDA den Namen des aktuellen Zielobjekts aus. So kannst du den Pfad aufbauen, ohne auf den Bildschirm schauen zu müssen.

Das Vorschaufeld „Name des Zielobjekts" zeigt jederzeit den ermittelten Namen an. Ist das Objekt nicht erreichbar, erscheint `(Objekt nicht erreichbar)`; hat es keinen Namen, erscheint `(kein Name)`.

**Hinweis:** Die Schaltflächen „OK", „Letzten Schritt entfernen" und „Pfad leeren" sind deaktiviert, solange noch kein Navigationsschritt hinzugefügt wurde.

## Typischer Arbeitsablauf

1. Zielanwendung fokussieren.
2. NVDA+Umschalt+0 drücken.
3. Code bearbeiten oder Vorlage anpassen.
4. Mit Ctrl+Umschalt+E auf Fehler prüfen.
5. Mit Alt+Pfeil runter/hoch durch Fehler gehen und korrigieren.
6. Mit Ctrl+S speichern.
7. Mit NVDA+Ctrl+F3 Plugins neu laden und Verhalten testen.

## Bekannte Hinweise

- Der Editor ist auf schnelle NVDA-Scriptbearbeitung ausgelegt und kein vollwertiger IDE-Ersatz.
- Fehler aus dem NVDA-Log werden auf Fehlerlevel ERROR/CRITICAL gesammelt.

## Version und Kompatibilität

- Add-on-Version in diesem Repository: 1.0.13-dev
- Zuletzt getestete NVDA-Version laut Manifest: 2025.3.3
