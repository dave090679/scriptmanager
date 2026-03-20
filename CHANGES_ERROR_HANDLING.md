# Script Manager: Fehlerbehandlung und NVDA-Integration

Stand: März 2026

## Ziel

Dieses Dokument beschreibt den aktuellen Stand der Fehlerbehandlung im Script Manager und die Integration mit NVDA-Logging.

## Kernpunkte

1. Mehrstufige Fehlerprüfung in `sm_backend.py`:
   - Syntaxprüfung
   - Kompilierungsprüfung
   - Laufzeitprüfung
   - zusätzliche Fehler aus NVDA-Log (ERROR/CRITICAL)
2. Laufzeitfehler werden über einen `ScriptErrorCollector` erfasst.
3. Fehlernavigation in der Oberfläche arbeitet zyklisch und startet bei Bedarf automatisch eine Prüfung.

## Relevante Funktionen

- `get_script_error_collector()`
- `activate_error_logging(script_file_path)`
- `deactivate_error_logging()`
- `collect_runtime_errors_from_log()`
- `try_execute_script(script_content, script_name)`
- `check_script_for_errors(script_content)`

## Bedienablauf

1. Script im Script Manager öffnen (NVDA+Umschalt+0 oder über Werkzeuge-Menü).
2. Mit Ctrl+Umschalt+E prüfen.
3. Mit Alt+Pfeil runter und Alt+Pfeil hoch durch Fehler springen.
4. Nach Speichern und Plugin-Reload (NVDA+Ctrl+F3) erneut prüfen, um Laufzeit-/Reload-Fehler zu sehen.

## Hinweise

- Erfasst werden nur ERROR- und CRITICAL-Einträge aus dem NVDA-Log.
- Je nach Umgebung können zusätzliche Logfehler auftauchen, die nicht direkt vom bearbeiteten Script stammen.
- Für sehr große Skripte kann die Laufzeitprüfung spürbar länger dauern.

## Schneller Test

1. Datei mit absichtlichem Syntaxfehler öffnen.
2. Ctrl+Umschalt+E drücken und prüfen, ob ein Fehler gemeldet wird.
3. Alt+Pfeil runter drücken und prüfen, ob zur Fehlerzeile gesprungen wird.
4. Fehler korrigieren, erneut prüfen, erwartetes Ergebnis: keine Fehler.
