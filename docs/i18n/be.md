# Code Grinder — Кіраўніцтва карыстальніка

[Code Grinder / GitHub](https://github.com/musikfed/Code-Grinder) · [Live project showcase / UI concept](https://musikfed.github.io/view_my_prj/projects/Code-Grinder/?lang=be) · v2.2 / Stage 2

Лакальнае ядро з аднаўленнем для ператварэння адказаў невялікіх мадэляў ШІ ў кіраваныя змены праекта. v2.2, этап 2 завершаны.

## 1. Усталяванне і тэсты

```bash
git clone https://github.com/musikfed/Code-Grinder.git
cd Code-Grinder
uv sync
uv run pytest -q
uv run ruff check .
```

## 2. Стварэнне праекта

```bash
uv run python main.py init --name my_project --language python --architecture Minimal --directory .
# Available stacks: python, node, go, rust, java, cpp, csharp, noop
# The interactive wizard: uv run python main.py init
```

## 3. Адказ мадэлі: TARGET / MODE

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

## 4. Рэжымы зменаў

- CREATE — ствараць толькі калі файла няма
- OVERWRITE — замяніць пасля праверкі існай версіі
- APPEND — дадаць і праверыць увесь выніковы файл
- PATCH — замяніць адно дакладнае супадзенне SEARCH/REPLACE

PASS — праверана; FAIL — памылка кода; SKIPPED — не праверана; ERROR — памылка правяральніка.

## 5. Выкарыстанне ядра праз Python

Падрыхтаваць змену і паглядзець Diff; без яўнага пацвярджэння не запісваць:

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

# Каментар па-беларуску: змены запісваюцца толькі пасля праверкі і пацвярджэння.
# After explicit approval only:
# manager.commit(preview, approved=True, allow_skipped=False)
```

## 6. Аднаўленне і бяспека

SHA-256 выяўляе ручныя змены. Перапыненую транзакцыю трэба праверыць перад працягам або адкатам. Змены некалькіх файлаў можна аднавіць, але яны не з’яўляюцца адной атамарнай аперацыяй. На Windows абарона шляхоў не гарантуе бяспекі ад варожай адначасовай падмены.

Калі залежнасці ўжо ўсталяваныя, ужывайце `python -m pytest` без інтэрнэту. `uv run --offline pytest` патрабуе гатовага кэша uv.

## 7. Вэб-інтэрфейс і выявы

Ніжэй — макеты UI, а НЕ скрыншоты дзейнага FastAPI. Каманда serve, API апрацоўкі, пацвярджэнні ў браўзеры і Project Map яшчэ не рэалізаваны. Дэма не запісвае файлы.

![UI concept — editor](../screenshots/editor.png)

![UI concept — diff](../screenshots/diff.png)

![UI concept — history](../screenshots/history.png)

![UI concept — settings](../screenshots/settings.png)

### Diagrams / Схемы

![Core flow](../diagrams/flow.svg)

![Recovery](../diagrams/transaction.svg)

![Adapters](../diagrams/adapters.svg)
