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

- NVDA mit aktivem Scratchpad (die Erweiterung arbeitet mit Dateien im Benutzerkonfigurationsbereich).
- Schreibrechte auf den NVDA-Benutzerordner.

## Globale Tastenkombinationen

- NVDA+Umschalt+0: Script-Manager-Fenster für die aktuell fokussierte Anwendung öffnen.
- NVDA+Umschalt+R: Beschriftungsregel für das aktuelle Navigator-Objekt erstellen und im AppModule speichern.
- nvda+Umschalt+r zweimal drücken: aktuell fokussiertes Element mit Auswahl der Beschriftungsmethode beschriften und Beschriftungsregel im Appmodul speichern.

## NVDA-Menüintegration

- NVDA-Menü > Werkzeuge > Script Manager: Öffnet den Script Manager für die aktuell fokussierte Anwendung.
- NVDA-Menü > Einstellungen > Script Manager labeling methods: Konfiguration der automatischen Beschriftungsmethoden und ihrer Priorität.

## Verhalten beim Öffnen mit NVDA+Umschalt+0

Beim Öffnen für die fokussierte Anwendung passiert automatisch Folgendes:

1. Der Prozessname der aktiven Anwendung wird ermittelt.
2. Wenn noch kein NVDA-AppModule existiert, wird im Scratchpad ein neues AppModule erstellt.
3. Wenn ein AppModule in NVDA/Add-on vorhanden ist, aber nicht im Benutzerordner, wird es in den Benutzerordner kopiert.
4. Das Ergebnis wird im Script-Manager-Editor geöffnet.

Dadurch kannst du vorhandene Logik schnell übernehmen und lokal anpassen.

## Script-Manager-Fenster

Das Fenster öffnet sich bildschirmfüllend und enthält einen mehrzeiligen Editor.

### Menü Datei

- Neu: Leere Datei
- Neu: AppModule-Vorlage
- Neu: GlobalPlugin-Vorlage
- Neu: BrailleDisplayDriver-Vorlage
- Neu: SynthDriver-Vorlage
- Neu: VisionEnhancementProvider-Vorlage
- Öffnen (Ctrl+O)
- Speichern (Ctrl+S)
- Speichern unter (Ctrl+Umschalt+S)
- Addon erstellen
- Beenden (Alt+F4)

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
- Neues Script erzeugen (Ctrl+E)
- Suchen (Ctrl+F)
- Weitersuchen (F3)
- Rückwärts suchen (Umschalt+F3)
- Ersetzen (Ctrl+H)
- Gehe zu Zeile (Ctrl+G)
- Nächster Fehler (Alt+Pfeil runter)
- Voriger Fehler (Alt+Pfeil hoch)
- Scriptfehler prüfen (Ctrl+Umschalt+E)

### Menü Hilfe

- Informationen über den Script Manager

## Assistent: Neues Script (Ctrl+E)

Der Assistent erzeugt eine fertige Script-Methode als Vorlage.

Erfasste Felder:

- Script-Name
- Beschreibung
- Geste (über Taste erfassen)
- Kategorie

Unterstützte Script-Kategorien umfassen u. a.:

- Miscellaneous
- Browse mode
- Text review
- Object navigation
- Mouse
- Speech
- Braille
- Vision
- Tools
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

## Labeling-Funktion für unbeschriftete Objekte (NVDA+Umschalt+R)

Für das aktuell fokussierte Objekt wird ein AppModule mit passender Labeling-Klasse erzeugt.

Dabei wird die Basisklasse automatisch passend zum NVDA-Objekttyp gewählt, z. B.:

- `NVDAObjects.UIA.UIA`
- `NVDAObjects.IAccessible.IAccessible`
- `NVDAObjects.NVDAObject` (Fallback)

Im Template ist eine `name`-Property enthalten, in die du die Beschriftung eintragen kannst.

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

- Add-on-Version in diesem Repository: 1.0-dev
- Zuletzt getestete NVDA-Version laut Manifest: 2025.3.3


