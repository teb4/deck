# Deck Editor

Транзакционный текстовый редактор, спроектированный специально для LLM-агентов.

Модель не видит и не правит файл напрямую — она получает от редактора пронумерованные фрагменты и отвечает пакетом («колодой») команд, который применяется к файлу атомарно, за один проход.

Для контроля целостности и защиты от гонок версий используется xxhash (`xxh64`). `REV` — это 16-символьный hex-хэш текущего содержимого файла.

## Содержание

- [Установка](#установка)
- [CLI](#cli)
- [Чтение строк (GET)](#чтение-строк-get)
- [Создание файла (CREATE)](#создание-файла-create)
- [Применение колоды (APPLY)](#применение-колоды-apply)
- [Структура колоды](#структура-колоды)
- [Операции колоды](#операции-колоды)
- [Адресация](#адресация)
- [Маркеры `@` и `$`](#маркеры--и-)
- [Модификатор `SKIP`](#модификатор-skip)
- [Версии, REV и version conflict](#версии-rev-и-version-conflict)
- [Лимиты](#лимиты)
- [Безопасность и атомарная запись](#безопасность-и-атомарная-запись)
- [MCP-сервер](#mcp-сервер)
- [Рекомендуемый workflow для LLM-агентов](#рекомендуемый-workflow-для-llm-агентов)
- [Ошибки](#ошибки)
- [Быстрый старт](#быстрый-старт)
- [Полная спецификация](#полная-спецификация)
- [Структура проекта](#структура-проекта)

## Установка

Требования:

- Python 3.10+
- виртуальное окружение рекомендуется

Шаги:

```bash
# 1. Клонировать репозиторий
git clone https://github.com/teb4/deck.git
cd deck

# 2. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate

# 3. Установить пакет
pip install -e .

# 4. (Опционально) Установить MCP-зависимости
pip install -e '.[mcp]'
```

После установки доступны:

| Команда | Описание |
|---|---|
| `deck-editor` | CLI для ручного использования |
| `deck-editor-mcp` | MCP-сервер для Qwen Code и других MCP-клиентов |

## CLI

Основные команды:

```bash
deck-editor get <file> <addr>
deck-editor create <file> [<rev>]
deck-editor apply <file> -
```

В примерах ниже колода передаётся через stdin. Символ `-` означает чтение колоды из стандартного потока ввода.

## Чтение строк (GET)

Команда:

```bash
deck-editor get file.py 1-50
```

Ответ:

```text
REV: a3f5b7c9d1e2f405
000001:def foo():
000002:    pass
000003e
000004:def bar():
```

Формат:

- `REV: <hash>` — 16-символьный хэш xxh64 текущего состояния файла.
- `NNNNNN:текст` — непустая строка, минимум 6 разрядов.
- `NNNNNNe` — пустая строка, суффикс `e`.

Номера строк появляются только в ответах `GET` и `CREATE`. В самом файле на диске номеров нет.

Для абсолютно пустого файла `GET` возвращает только `REV`:

```text
REV: a3f5b7c9d1e2f405
```

## Создание файла (CREATE)

`CREATE` — внешняя CLI-команда. Она не является частью колоды.

`CREATE` читает содержимое нового файла или полную замену существующего файла из `stdin` до EOF.

### Создание нового файла

Для нового файла `REV` указывать нельзя:

```bash
printf 'строка одна\nстрока две\n' | deck-editor create newfile.txt
```

Ответ:

```text
REV: a3f5b7c9d1e2f406
000001:строка одна
000002:строка две
```

### Перезапись существующего файла

Для перезаписи существующего файла `REV` обязателен:

```bash
printf 'новое содержимое\n' | deck-editor create existing.txt a3f5b7c9d1e2f405
```

Ответ:

```text
REV: a3f5b7c9d1e2f406
000001:новое содержимое
```

Правила:

- если файл не существует, `REV` указывать нельзя;
- если файл существует, `REV` обязателен;
- при успешном `CREATE` возвращается полный нумерованный листинг результата, включая новый `REV`;
- содержимое `stdin` не сканируется как колода;
- строки вида `@END`, `@REPLACE`, `$END`, `$VAR` в `CREATE` безопасны и воспринимаются как обычный текст.

Пример ошибки:

```bash
printf 'text\n' | deck-editor create newfile.txt a3f5b7c9d1e2f405
```

Ожидаемая ошибка:

```text
ERROR: <rev> must not be specified for new file
```

## Применение колоды (APPLY)

Колода предназначена для модификации существующего файла.

Применение колоды к несуществующему файлу — ошибка. Для создания файла используйте `CREATE`.

Колода имеет три режима:

| Режим | Описание | Запись на диск |
|---|---|---|
| `@DRY` | предпросмотр в формате unified diff | нет |
| `@DRY_ALL` | предпросмотр полного нумерованного листинга | нет |
| `@APPLY` | атомарное применение изменений | да |

### Пример `@DRY`

```bash
deck-editor apply file.py - <<'EOF'
@DRY a3f5b7c9d1e2f405
@REPLACE 2
    1.1 Обработка параметров и файлов
@END
EOF
```

Ответ:

```text
REV: a3f5b7c9d1e2f406 (would be new)
Original: a3f5b7c9d1e2f405 → Modified: a3f5b7c9d1e2f406
--- original
+++ modified
@@ -2,1 +2,1 @@
-    1.1 Обработка параметров
+    1.1 Обработка параметров и файлов
Operations applied:
- REPLACE lines 2-2 (1 line replaced with 1 line)
```

Если изменённый блок больше 50 строк, показываются первые 10 строк, затем `... скрыто ...`, затем последние 10 строк.

### Пример `@DRY_ALL`

```bash
deck-editor apply file.py - <<'EOF'
@DRY_ALL a3f5b7c9d1e2f405
@REPLACE 2
    1.1 Обработка параметров и файлов
@END
EOF
```

Ответ:

```text
REV: a3f5b7c9d1e2f406 (would be new)
000001:# План
000002:    1.1 Обработка параметров и файлов
000003:
000004:## Детали
```

Для абсолютно пустого результата `DRY_ALL` возвращает:

```text
REV: a3f5b7c9d1e2f406 (would be new)
(Empty file: 0 lines)
```

### Пример `@APPLY`

```bash
deck-editor apply file.py - <<'EOF'
@APPLY a3f5b7c9d1e2f405
@REPLACE 2
    1.1 Обработка параметров и файлов
@END
EOF
```

Ответ:

```text
APPLIED successfully
REV: a3f5b7c9d1e2f406 (new)
Operations applied:
- REPLACE lines 2-2 (1 line replaced with 1 line)
```

## Структура колоды

Колода состоит из заголовка, тела и терминатора.

```text
заголовок      := маркер ("DRY" | "DRY_ALL" | "APPLY") <rev>
маркер         := "@" | "$"
тело           := одна или несколько операций
терминатор     := маркер "END"
```

Пример:

```text
@APPLY a3f5b7c9d1e2f405
@REPLACE 2
    1.1 Обработка параметров и файлов
@END
```

Обязательные правила:

- заголовок должен начинаться с `@DRY`, `@DRY_ALL` или `@APPLY`;
- `<rev>` обязателен для существующего файла;
- `<rev>` должен быть 16-символьным хэшем xxh64;
- терминатор должен быть последней строкой колоды;
- строки после терминатора запрещены;
- маркер терминатора должен совпадать с маркером заголовка;
- смешивание маркеров `@` и `$` в одной колоде запрещено.

Пример с маркером `$`:

```text
$APPLY a3f5b7c9d1e2f405
$REPLACE 10
@END
$END
```

Здесь payload содержит строку `@END`, но она не является командой, потому что маркер колоды — `$`.

## Операции колоды

| Команда | Адрес | Payload | `SKIP` | Описание |
|---|---|---|---|---|
| `@REPLACE <addr>` | `N`, `N-M`, `N-` | да | допускается | Заменить строки |
| `@DELETE <addr>` | `N`, `N-M`, `N-` | нет | запрещён | Удалить строки |
| `@INSERT <N>` | только `N` | да | допускается | Вставить после строки `N` |
| `@INSERT_HEAD` | нет | да | допускается | Вставить перед строкой 1 |
| `@REPLACE_REGEX <addr>` | `N`, `N-M`, `N-` | да | допускается | Regex-замена по sed |
| `@APPEND` | нет | да | запрещён | Добавить строки в конец |

Важно:

- payload всегда передаётся без номеров строк;
- операции в колоде выполняются последовательно;
- каждая следующая операция работает с результатом предыдущей;
- номера строк могут сдвигаться после `REPLACE`, `INSERT`, `INSERT_HEAD` и `DELETE`;
- `DELETE` строго не имеет payload;
- `DELETE` не поддерживает `SKIP`;
- `REPLACE_REGEX` использует синтаксис sed: `s/pattern/replacement/flags`;
- `APPEND` не имеет адреса и не поддерживает `SKIP`.

Пример ошибки:

```text
@APPLY a3f5b7c9d1e2f405
@DELETE 2
лишний payload
@END
```

Ожидаемая ошибка:

```text
ERROR: unexpected payload after DELETE
```

## Новые операции: `REPLACE_REGEX` и `APPEND`

### `REPLACE_REGEX` — regex-замена

Применяет sed-выражение к строкам в указанном диапазоне.

```text
# Заменить "foo" на "bar" в строках 4–50
@APPLY a3f5b7c9d1e2f405
@REPLACE_REGEX 4-50
s/foo/bar/g
@END

# Замена с захватом групп
@APPLY a3f5b7c9d1e2f405
@REPLACE_REGEX 10-20
s/(temp)/\1_celsius/g
@END
```

Поддерживаемые разделители: `/`, `|`, `#`, `~`.
Флаги: `g` (все совпадения), без флага — только первое совпадение.

### `APPEND` — добавление строк в конец файла

```text
# Добавить JSON-запись в лог
@APPLY a3f5b7c9d1e2f405
@APPEND
{"sensor": "temp", "value": 30.0, "unit": "C"}
@END

# Добавить несколько строк
@APPLY a3f5b7c9d1e2f405
@APPEND
{"sensor": "humidity", "value": 65.0}
{"sensor": "pressure", "value": 1013.0}
@END
```

Без адреса, без `SKIP`.

## Адресация

| Формат | Описание |
|---|---|
| `N` | Одна строка |
| `N-M` | Строки с `N` по `M` включительно |
| `N-` | От строки `N` до конца файла |

Ограничения:

- нумерация строк начинается с 1;
- для диапазона `N-M` должно выполняться `N ≤ M`;
- `INSERT` принимает только одиночный адрес `N`;
- `INSERT_HEAD` не принимает адрес.

Пример ошибки:

```text
@APPLY a3f5b7c9d1e2f405
@INSERT 2-5
текст
@END
```

Ожидаемая ошибка:

```text
ERROR: INSERT requires single line address
```

## Маркеры `@` и `$`

Основной маркер — `@`.

По умолчанию колоды формируются так:

```text
@APPLY a3f5b7c9d1e2f405
@REPLACE 2
новый текст
@END
```

Альтернативный маркер — `$`.

Он используется, если payload содержит валидные команды Deck с маркером `@` в нулевой колонке, например:

```text
@END
@REPLACE 1
@INSERT 5
```

В таком случае можно использовать колоду с маркером `$`:

```text
$APPLY a3f5b7c9d1e2f405
$REPLACE 10
@END
@REPLACE 1
$END
```

Если payload содержит и `@`, и `$` команды в нулевой колонке, следует использовать основной маркер `@`, а конфликтную операцию поставить в конец колоды с модификатором `SKIP`.

## Правило распознавания управляющей строки

Строка признаётся командой Deck только при одновременном выполнении условий:

1. маркер `@` или `$` стоит в нулевой колонке;
2. сразу после маркера следует зарезервированное слово;
3. сразу после слова идёт конец строки или пробел.

Зарезервированные слова:

```text
DRY
DRY_ALL
APPLY
REPLACE
DELETE
INSERT
INSERT_HEAD
END
```

Поэтому обычные декораторы и аннотации не являются командами Deck:

```python
@app.route
@property
@staticmethod
@Override
```

Переменные bash тоже не являются командами:

```bash
$VAR
$END
```

Отступленный код физически не может быть спутан с командой, потому что маркер находится не в нулевой колонке.

## Модификатор `SKIP`

`SKIP` используется только тогда, когда payload содержит строки, которые парсер обязан распознать как команды Deck.

Например, если вы генерируете документацию по Deck и payload содержит literal-строки:

```text
@END
@REPLACE 1
@INSERT 5
```

Тогда нужна операция с `SKIP`.

Правила:

- `SKIP` — булевый флаг;
- `SKIP` не принимает аргументов;
- операция с `SKIP` должна быть последней в колоде;
- любая операция после `SKIP` — ошибка;
- `DELETE` не поддерживает `SKIP`;
- обычные декораторы, аннотации и переменные не требуют `SKIP`.

Пример ошибки:

```text
@APPLY a3f5b7c9d1e2f405
@REPLACE 1 SKIP 3
текст
@END
```

Ожидаемая ошибка:

```text
ERROR: SKIP takes no arguments
```

Пример ошибки:

```text
@APPLY a3f5b7c9d1e2f405
@INSERT 1 SKIP
текст
@INSERT 5
ещё текст
@END
```

Ожидаемая ошибка:

```text
ERROR: operation after SKIP
```

## Версии, REV и version conflict

`REV` защищает от применения правок к устаревшему контексту.

Типовой цикл:

1. прочитать файл через `GET`;
2. получить актуальный `REV`;
3. сформировать колоду с этим `REV`;
4. применить колоду через `DRY`, `DRY_ALL` или `APPLY`.

Если между чтением и применением файл изменился, Deck отклонит колоду:

```text
ERROR: version conflict — file changed
```

После `version conflict` запрещено:

- угадывать новые номера строк;
- применять старую колоду повторно;
- переписывать файл целиком в обход `GET`.

Нужно:

1. выполнить новый `GET`;
2. получить актуальный `REV`;
3. пересобрать колоду.

## Лимиты

| Лимит | Значение по умолчанию | Описание |
|---|---:|---|
| `MAX_DECK_LINES` | 5000 | суммарный лимит строк payload в колоде |
| `MAX_CREATE_LINES` | 50000 | лимит для внешнего `CREATE` |

При превышении лимита колода или `CREATE` отклоняются.

## Безопасность и атомарная запись

Все файловые операции ограничены рамками рабочей директории — workspace root.

Правила:

- для CLI workspace root — текущая рабочая директория;
- для MCP-сервера workspace задаётся при запуске через `--workspace` или переменную окружения `WORKSPACE`;
- если workspace не задан, используется текущая рабочая директория процесса MCP-сервера;
- попытки выхода за пределы workspace отклоняются;
- символические ссылки разрешаются до реального абсолютного пути;
- файл не может быть изменён вне workspace через symlink.

Пример ошибки:

```text
ERROR: access denied — path outside working directory
```

Запись результата `APPLY` или `CREATE` выполняется атомарно.

Используется safe-write:

1. временный файл создаётся в той же директории, что и целевой;
2. данные записываются и сбрасываются через `fsync`;
3. права доступа оригинального файла сохраняются;
4. целевой файл атомарно заменяется через `os.replace()`;
5. при ошибке временный файл удаляется;
6. целевой файл остаётся нетронутым.

Файл на диске никогда не должен оказаться в частично записанном, повреждённом или пустом промежуточном состоянии.

## MCP-сервер

Deck Editor может работать как MCP-сервер и подключаться к Qwen Code и другим MCP-клиентам.

### Настройка в Qwen Code

Добавьте в `.qwen/settings.json`:

```json
{
  "mcpServers": {
    "deck-editor": {
      "command": "/path/to/deck/.venv/bin/deck-editor-mcp",
      "args": [
        "--workspace",
        "/path/to/project"
      ]
    }
  }
}
```

Или используйте относительный путь от проекта:

```json
{
  "mcpServers": {
    "deck-editor": {
      "command": ".venv/bin/deck-editor-mcp",
      "args": [
        "--workspace",
        "."
      ]
    }
  }
}
```

Альтернативно workspace можно задать через переменную окружения:

```json
{
  "mcpServers": {
    "deck-editor": {
      "command": ".venv/bin/deck-editor-mcp",
      "env": {
        "WORKSPACE": "/path/to/project"
      }
    }
  }
}
```

### Доступные тулзы

| Тулза | Описание |
|---|---|
| `get` | Прочитать строки файла. Возвращает `REV` и пронумерованный листинг |
| `create` | Создать новый файл или перезаписать существующий |
| `apply` | Применить колоду к файлу. Поддерживает `@DRY`, `@DRY_ALL`, `@APPLY` |

### Пример вызова `get`

Запрос:

```json
{
  "name": "get",
  "arguments": {
    "file": "src/main.py",
    "addr": "1-50"
  }
}
```

Ответ:

```text
REV: a3f5b7c9d1e2f405
000001:def main():
000002:    config = load_config()
000003:    result = process(config)
000004:    return result
000005e
000006:def process(config):
...
```

### Работа с файлами из других проектов

Согласно спецификации, workspace задаётся на уровне запуска MCP-сервера, а не в аргументах отдельной тулзы.

Для другого проекта запустите отдельный MCP-сервер с другим workspace:

```json
{
  "mcpServers": {
    "deck-editor-other-project": {
      "command": ".venv/bin/deck-editor-mcp",
      "args": [
        "--workspace",
        "/home/user/projects/other_project"
      ]
    }
  }
}
```

Для CLI достаточно выполнить команду из нужной рабочей директории:

```bash
cd /home/user/projects/other_project
deck-editor get src/main.py 1-50
```

## Рекомендуемый workflow для LLM-агентов

Deck спроектирован под Unix-way и делегирует поиск внешним инструментам.

Рекомендуемый цикл:

1. Текстовый поиск через `ripgrep`:

```bash
rg -n "calculate_total" src/
```

2. Структурный поиск через `ast-grep`, если нужно найти функцию, класс или другой синтаксический блок целиком.

3. Чтение контекста через Deck:

```bash
deck-editor get src/main.py 120-160
```

4. Применение колоды:

```bash
deck-editor apply src/main.py - <<'EOF'
@APPLY a3f5b7c9d1e2f405
@REPLACE 125-130
новый код
@END
EOF
```

Жёсткие правила для агента:

- никогда не применять `REPLACE` или `DELETE` к файлу, который не был прочитан через `GET` в текущей сессии;
- никогда не пропускать `REV` в заголовке колоды;
- никогда не угадывать номера строк;
- при `version conflict` обязательно выполнить новый `GET`;
- не использовать `SKIP` для обычных декораторов вроде `@app.route`;
- использовать `SKIP` только если payload содержит literal-команды Deck;
- операцию с `SKIP` ставить последней в колоде;
- payload всегда передавать без номеров строк.

## Ошибки

При любой ошибке файл на диске не изменяется. Колода откатывается целиком.

Основные ошибки:

| Ошибка | Причина |
|---|---|
| `ERROR: deck not terminated by END` | Последняя строка колоды не является `@END` или `$END` |
| `ERROR: trailing lines after END` | После терминатора есть строки |
| `ERROR: terminator does not match deck marker` | Заголовок использует `@`, а терминатор `$`, или наоборот |
| `ERROR: deck must start with DRY, DRY_ALL or APPLY` | Неверный заголовок колоды |
| `ERROR: <rev> is mandatory for existing files` | В заголовке колоды отсутствует `REV` |
| `ERROR: unexpected payload after DELETE` | После `DELETE` передан payload |
| `ERROR: SKIP takes no arguments` | `SKIP` указан с аргументами |
| `ERROR: operation after SKIP` | После операции с `SKIP` есть другая операция |
| `ERROR: INSERT requires single line address` | `INSERT` вызван с диапазоном |
| `ERROR: INSERT_HEAD takes no address` | `INSERT_HEAD` вызван с адресом |
| `ERROR: version conflict — file changed` | `REV` в колоде не совпадает с текущим хэшем файла |
| `ERROR: invalid address range — start > end` | В адресе `N-M` значение `M` меньше `N` |
| `ERROR: address out of file range` | Адрес выходит за пределы файла |
| `ERROR: file does not exist, use CREATE` | `APPLY` применён к несуществующему файлу |
| `ERROR: deck size limit exceeded` | Превышен `MAX_DECK_LINES` |
| `ERROR: access denied — path outside working directory` | Путь выходит за пределы workspace |
| `ERROR: file exists, <rev> required to overwrite` | `CREATE` существующего файла без `REV` |
| `ERROR: <rev> must not be specified for new file` | `CREATE` несуществующего файла с `REV` |

Полная таблица ошибок и этапы валидации описаны в `spec.md`.

## Быстрый старт

### Для разработчиков (CLI)

```bash
# Установить
pip install -e .

# Прочитать файл
deck-editor get src/main.py 1-20
```

Пример ответа:

```text
REV: a3f5b7c9d1e2f405
000001:def main():
000002:    config = load_config()
000003:    result = process(config)
000004:    return result
```

Предпросмотр изменений:

```bash
deck-editor apply src/main.py - <<'EOF'
@DRY a3f5b7c9d1e2f405
@REPLACE 3
    result = process(config, strict=True)
@END
EOF
```

Пример ответа:

```text
REV: a3f5b7c9d1e2f406 (would be new)
Original: a3f5b7c9d1e2f405 → Modified: a3f5b7c9d1e2f406
--- original
+++ modified
@@ -3,1 +3,1 @@
-    result = process(config)
+    result = process(config, strict=True)
Operations applied:
- REPLACE lines 3-3 (1 line replaced with 1 line)
```

Применить изменения:

```bash
deck-editor apply src/main.py - <<'EOF'
@APPLY a3f5b7c9d1e2f405
@REPLACE 3
    result = process(config, strict=True)
@END
EOF
```

Пример ответа:

```text
APPLIED successfully
REV: a3f5b7c9d1e2f406 (new)
Operations applied:
- REPLACE lines 3-3 (1 line replaced with 1 line)
```

Проверить результат:

```bash
deck-editor get src/main.py 1-20
```

### Для LLM-агентов (MCP)

1. Настройте MCP-сервер в `.qwen/settings.json`.
2. Укажите workspace через `--workspace` или `WORKSPACE`.
3. LLM-агент получит доступ к тулзам `get`, `create`, `apply`.
4. Агент читает файл через `get`, фиксирует `REV`, формирует колоду и применяет её через `apply`.

Минимальный безопасный сценарий:

```text
get → получить REV и номера строк
apply @DRY → проверить diff
apply @APPLY → применить изменения
get → проверить результат
```

## Полная спецификация

Полная спецификация языка колод, архитектура и детали реализации — в [`spec.md`](spec.md).

Дополнительная документация для LLM-агентов — в [`agents.md`](agents.md).

## Структура проекта

```text
deck/
 ├── deck_editor/
 │   ├── __init__.py          — версия пакета
 │   ├── __main__.py          — CLI (get, create, apply)
 │   ├── mcp_server.py        — MCP-сервер
 │   ├── parser.py            — парсер колод
 │   ├── cmd_get.py           — команда GET
 │   ├── cmd_create.py        — команда CREATE
 │   ├── operations.py        — REPLACE, DELETE, INSERT
 │   ├── apply.py             — DRY, DRY_ALL, APPLY
 │   └── utils.py             — xxhash, atomic_write, ошибки
 ├── tests/                   — тесты
 ├── spec.md                  — полная спецификация
 ├── agents.md                — правила для LLM-агентов
 ├── pyproject.toml           — конфигурация пакета
 └── README.md                — этот файл
```
