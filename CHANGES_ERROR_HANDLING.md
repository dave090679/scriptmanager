# Script Manager: Verbesserte Fehlerbehandlung und NVDA-Integration

## Zusammenfassung der Änderungen

Der NVDA Script Manager wurde überarbeitet, um eine nahtlose Integration mit NVDAs Fehlerbehandlungssystem zu erreichen. Die Befehle "nächster Fehler" und "voriger Fehler" (Alt+Pfeiltasten) funktionieren nun besser mit echten Laufzeitfehlern.

## Neue Features

### 1. **Automatische Fehlererfassung aus NVDAs Log**

Das System verfügt jetzt über einen `ScriptErrorCollector`, der sich in NVDAs Logging-System einklinkt und Fehler automatisch erfasst:

- **Datei**: `sm_backend.py`
- **Klasse**: `ScriptErrorCollector(logging.Handler)`
- **Funktion**: Erfasst ERROR und CRITICAL Log-Meldungen während des Plugin-Reload (NVDA+Ctrl+F3)

### 2. **Erweiterte Fehlerprüfung**

Die Fehlerprüfung wurde auf drei Ebenen erweitert:

1. **Syntaxfehler** - Die Python-`compile()` Funktion wird verwendet
2. **Kompilierungsfehler** - `py_compile.compile()` wird verwendet  
3. **Laufzeitfehler** - Neue Funktion `try_execute_script()` führt den Code aus und erfasst Import/Runtime-Fehler

### 3. **Intelligente Fehlernavigation**

Die Befehle "nächster Fehler" (Alt+Down) und "voriger Fehler" (Alt+Up) wurden aktualisiert:

- Wenn noch keine Fehler geprüft wurden, wird automatisch `check_script_for_errors()` aufgerufen
- Fehler werden zwischen ihnen zyklisch durchlaufen
- Automatisches Springen zur fehlerhaften Zeile mit Beschreibung

## Technische Details

### ScriptErrorCollector

```python
class ScriptErrorCollector(logging.Handler):
    """Ein Custom Log Handler, der Fehler für das aktuelle Script sammelt."""
    
    # Erfasst alle ERROR und CRITICAL Log-Meldungen
    # Kann aktiviert/deaktiviert werden
    # Speichert Fehler mit Zeilennummern und Zeitstempel
```

### Neue Funktionen in sm_backend.py

1. **`get_script_error_collector()`** - Gibt den globalen Error Collector zurück
2. **`activate_error_logging(script_file_path)`** - Aktiviert Error Logging für das aktuelle Script
3. **`deactivate_error_logging()`** - Deaktiviert Error Logging
4. **`collect_runtime_errors_from_log()`** - Sammelt all erfassten Fehler
5. **`try_execute_script(script_content, script_name)`** - Führt das Script aus und erfasst Runtime-Fehler

### Aktualisierte Funktionen

**`check_script_for_errors(script_content)`** - Jetzt mit vier Fehlerprüfungs-Stufen:

1. Syntaxfehler-Prüfung
2. Compilierungs-Fehler
3. Laufzeitfehler (Ausführung in Safe-Environment)
4. NVDA Log-Fehler (falls vorhanden)

## Workflow

### Beim Speichern des Scripts (Ctrl+S)

1. Error Logging wird aktiviert
2. Die Datei wird gespeichert
3. Der derzeitige Fehler-Index wird zurückgesetzt

### Beim Drücken von "Fehler prüfen" (Ctrl+Shift+E)

1. Error Logging wird aktiviert
2. Das Script wird auf Fehler überprüft (4 Stufen)
3. Die Fehler-Liste wird gefüllt
4. Der erste Fehler wird angezeigt

### Beim Drücken von "nächster Fehler" (Alt+Down) oder "voriger Fehler" (Alt+Up)

1. Falls noch keine Fehler geprüft wurden, werden sie jetzt geprüft
2. Der Fehler-Index wird erhöht/verringert
3. Zur fehlerhaften Zeile wird gesprungen
4. Die Fehlermeldung wird angezeigt

### Beim Plugin-Reload (NVDA+Ctrl+F3)

1. Der Error Collector ist aktiv und erfasst alle ERROR/CRITICAL Log-Meldungen
2. Wenn der Benutzer danach "Fehler prüfen" drückt oder Alt+Down/Up, werden diese Fehler berücksichtigt
3. Die echten Runtime-Fehler vom Plugin-Reload werden angezeigt

## Wichtige Hinweise

### Vorher: Nur statische Fehlerprüfung

- Nur Syntaxfehler wurden erkannt
- Nur Python `compile()` wurde verwendet
- Keine Integration mit NVDAs Fehlerbehandlung

### Nachher: Dynamische Fehlererfassung

- Syntaxfehler, Compile-Fehler UND Runtime-Fehler werden erkannt
- Integration mit NVDAs `logHandler` System
- Fehler vom Plugin-Reload (NVDA+Ctrl+F3) werden automatisch erfasst
- Keine Notwendigkeit mehr, das Script in Temp zu kopieren

## Kompatibilität

Die Änderungen sind vollständig abwärtskompatibel:

- Bestehende Scripts funktionieren unverändert
- Das Error-Logging ist optional (kann deaktiviert werden)
- Die UI bleibt identisch
- Nur die Fehlerprüfung wurde erweitert

## Beispiel-Workflow

```
1. Benutzer öffnet Script Manager (NVDA+Shift+0)
2. Benutzer bearbeitet ein Script
3. Benutzer drückt Alt+Down um zum nächsten Fehler zu springen
   → Automatisch wird das Script geprüft
   → Alle Fehler werden gefunden und angezeigt
4. Benutzer speichert das Script (Ctrl+S)
   → Error Logging wird für zukünftige Checks aktiviert
5. Benutzer drückt NVDA+Ctrl+F3 um Plugins neu zu laden
   → Der Error Collector erfasst alle Fehler automatisch
6. Benutzer drückt Ctrl+Shift+E um Fehler zu prüfen
   → Alle aufgezeichneten Fehler werden angezeigt
   → Auch Fehler vom Plugin-Reload sind sichtbar
```

## Debugging und Troubleshooting

Falls die Fehlererfassung nicht funktioniert:

1. Überprüfe, ob NVDA Fehler protokolliert (z.B. in NVDA.log)
2. Der Error Collector wird automatisch beim Öffnen des Script Managers Fensters aktiviert
3. Die Fehler werden 90 Tage in NVDAs Log gespeichert
4. Bei Problemen kann auch manuell `activate_error_logging()` aufgerufen werden

## Zukünftige Verbesserungen

Mögliche weitere Features:

- Fehler-Filter (z.B. nur kritische Fehler anzeigen)
- Fehler-Kategorisierung (Syntax, Runtime, Import, etc.)
- Export der Fehler in eine Datei
- Integration mit IDEs (LSP, DAP)
- Automatisches Speichern mit Fehlerprüfung
