# Code Grinder — Benutzerhandbuch

[Code Grinder / GitHub](https://github.com/musikfed/Code-Grinder) · [Live project showcase / UI concept](https://musikfed.github.io/view_my_prj/projects/Code-Grinder/?lang=de) · v2.2 / Stage 2

Ein lokaler, wiederherstellbarer Kern, der Antworten kleiner KI-Modelle in kontrollierte Projektänderungen verwandelt. v2.2, Phase 2 abgeschlossen.

## 1. Installation und Tests

```bash
git clone https://github.com/musikfed/Code-Grinder.git
cd Code-Grinder
uv sync
uv run pytest -q
uv run ruff check .
```

## 2. Projekt erstellen

```bash
uv run python main.py init --name my_project --language python --architecture Minimal --directory .
# Available stacks: python, node, go, rust, java, cpp, csharp, noop
# The interactive wizard: uv run python main.py init
```

## 3. Modellantwort: TARGET / MODE

````text
TARGET: src/hello.py
MODE: CREATE
```python
print("Hello, Code Grinder!")
```

TARGET: src/hello.py
MODE: PATCH
```text
<<<<<<< SEARCH
print("Hello, Code Grinder!")
=======
print("Hello, version 2.2!")
>>>>>>> REPLACE
```
````

## 4. Änderungsmodi

- CREATE — nur erstellen, wenn die Datei fehlt
- OVERWRITE — vorhandene Version prüfen und ersetzen
- APPEND — anhängen und das gesamte Ergebnis prüfen
- PATCH — eine exakt eindeutige SEARCH/REPLACE-Stelle ersetzen

PASS — geprüft; FAIL — ungültiger Code; SKIPPED — nicht geprüft; ERROR — Fehler des Prüfwerkzeugs.

## 5. Kernbibliothek verwenden

Änderung vorbereiten und Diff prüfen; niemals ohne ausdrückliche Freigabe schreiben:

```python
from pathlib import Path
from grinder.database import Database
from grinder.file_ops import FileManager
from grinder.parser import parse_response

root = Path("my_project").resolve()
db = Database(root / ".grinder" / "grinder.db")
manager = FileManager(root, db)
answer = (
    "TARGET: src/new.py\n"
    "MODE: CREATE\n"
    "```python\nprint('Hello!')\n```\n"
)
preview = manager.prepare(parse_response(answer))
for item in preview:
    print(item.diff, item.validation.status)

# Deutscher Kommentar: Änderungen erst nach Prüfung und Freigabe schreiben.
# After explicit approval only:
# manager.commit(preview, approved=True, allow_skipped=False)
```

## 6. Wiederherstellung und Sicherheit

SHA-256 erkennt manuelle Änderungen. Unterbrochene Transaktionen müssen vor Wiederaufnahme oder Zurücksetzen geprüft werden. Mehrere Dateien lassen sich wiederherstellen, aber nicht gemeinsam atomar umschalten. Unter Windows schützt die Pfadprüfung nicht vollständig gegen böswillige parallele Änderungen.

Sind die Abhängigkeiten installiert, funktioniert `python -m pytest` ohne Netzwerk. `uv run --offline pytest` benötigt alle Pakete im uv-Cache.

## 7. Weboberfläche und Bilder

Die Abbildungen sind UI-Entwürfe, KEINE Screenshots eines laufenden FastAPI-Servers. serve, Verarbeitungs-API, Browser-Freigaben und Project Map sind noch nicht implementiert. Die Demo schreibt keine Dateien.

![UI concept — editor](../screenshots/editor.png)

![UI concept — diff](../screenshots/diff.png)

![UI concept — history](../screenshots/history.png)

![UI concept — settings](../screenshots/settings.png)

### Diagrams / Схемы

![Core flow](../diagrams/flow.svg)

![Recovery](../diagrams/transaction.svg)

![Adapters](../diagrams/adapters.svg)
