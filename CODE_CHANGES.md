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
