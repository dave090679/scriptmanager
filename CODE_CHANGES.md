# Code-Änderungen Übersicht

Stand: März 2026

Dieses Dokument fasst die aktuell wichtigsten strukturellen Änderungen im Projekt zusammen.

## addon/globalPlugins/scriptmanager/__init__.py

- GlobalPlugin initialisiert zusätzliche Menüintegration in NVDA:
  - NVDA-Menü > Werkzeuge > Script Manager
  - NVDA-Menü > Einstellungen > Script Manager labeling methods
- Neue gemeinsame Öffnungsroutine `_openScriptManagerForCurrentFocus()`:
  - wird von Tastenkürzel und Werkzeuge-Menüeintrag genutzt
  - reduziert duplizierte Logik
- Labeling-Logik erweitert und konfigurierbar gemacht:
  - automatische Methoden A/B/C
  - methodenspezifische Auswahl und Priorisierung
  - manuelle Methoden D/E

## addon/globalPlugins/scriptmanager/sm_backend.py

- Fehlererfassung für Runtime-Probleme über NVDA-Logging ergänzt (`ScriptErrorCollector`).
- Fehlerprüfung in mehreren Stufen konsolidiert:
  - Syntax
  - Kompilierung
  - Laufzeit
  - NVDA-Logfehler
- Hilfsfunktionen für Add-on-Build/Packaging aus dem Scratchpad ergänzt.

## addon/globalPlugins/scriptmanager/sm_frontend.py

- Script-Assistent erweitert:
  - zusätzliche Gesten
  - erweiterte Script-Optionen (`canPropagate`, `bypassInputHelp`, `allowInSleepMode`, `resumeSayAllMode`, `speakOnDemand`)
- Script-Template-Generierung auf dynamische Decorator-Argumente umgestellt.
- Fehlernavigation und Fehlerprüfung enger mit Backend-Fehlererfassung gekoppelt.

## Dokumentation

- Nutzerdokumentation und Projekt-README auf aktuellen Bedienstand gebracht:
  - Werkzeuge-Menüeintrag dokumentiert
  - Labeling-Kürzel auf NVDA+Umschalt+R korrigiert
  - Versionsstand auf `1.0-dev` aktualisiert

## Test-Hinweise

1. NVDA starten und Menü prüfen: Werkzeuge > Script Manager vorhanden.
2. Script Manager per Menü öffnen und schließen.
3. NVDA+Umschalt+0 testen (gleiches Verhalten wie Menüeintrag).
4. NVDA+Umschalt+R testen (Labeling-Dialog/Regelerzeugung).
5. Fehlerprüfung mit Ctrl+Umschalt+E sowie Alt+Pfeil hoch/runter testen.

## Checkliste: Datei/Neu und Speichern unter

1. Datei > Neu > Leere Datei wählen und danach Datei > Speichern unter öffnen.
2. Prüfen: Startordner ist das Scratchpad-Hauptverzeichnis.
3. Datei > Neu > Appmodule wählen und danach Datei > Speichern unter öffnen.
4. Prüfen: Startordner ist Scratchpad/appModules.
5. Datei > Neu > Global Plugin wählen und danach Datei > Speichern unter öffnen.
6. Prüfen: Startordner ist Scratchpad/globalPlugins.
7. Datei > Neu > Braille Display Driver wählen und danach Datei > Speichern unter öffnen.
8. Prüfen: Startordner ist Scratchpad/brailleDisplayDrivers.
9. Datei > Neu > Speech Synthesizer Driver wählen und danach Datei > Speichern unter öffnen.
10. Prüfen: Startordner ist Scratchpad/synthDrivers.
11. Datei > Neu > Visual Enhancement Provider wählen und danach Datei > Speichern unter öffnen.
12. Prüfen: Startordner ist Scratchpad/visionEnhancementProviders.
13. Jeweils einmal speichern, Datei erneut mit Datei > Öffnen laden und erneut Datei > Speichern unter öffnen.
14. Prüfen: Es wird das Verzeichnis der geöffneten Datei als Startordner angeboten.

### Mini-Checkliste: Scratchpad-Policy = Nein

1. NVDA-Einstellungen > Script Manager öffnen und "Scratchpad bei Bedarf aktivieren" auf "Nein" setzen.
2. Sicherstellen, dass Scratchpad in NVDA deaktiviert ist.
3. Menü öffnen und prüfen: Scratchpad-pflichtige Einträge sind ausgegraut (z. B. Datei > Neu > Appmodule, Add-on bauen).
4. Erwartung: Aktionen bleiben gesperrt, bis Scratchpad wieder aktiviert oder die Policy geändert wird.
