# План: Добавление логирования

## 1. Добавить настройку логирования в config.py ✅
- Добавить `log_enabled: bool = False` в `_DEFAULTS`
- Экспортировать `log_enabled` как публичную константу

## 2. Создать модуль logger ✅
- `deck_editor/logger.py` — модуль логирования
- Логгер по умолчанию отключён
- Включается через `log_enabled` из config
- Поддерживаемые события: GET, APPLY, REPLACE, REPLACE_REGEX, APPEND, END
- Формат: `2026-08-10T14:32:11 GET file=... addr=... lines=... chars=...`

## 3. Интегрировать логирование в точки входа ✅
- `mcp_server.py` — логирование включается при старте
- `cmd_get.py` — логировать GET
- `apply.py` — логировать APPLY и операции REPLACE, REPLACE_REGEX, APPEND, END

## 4. Написать юнит-тесты ✅
- 20 тестов на логгер (вкл/выкл, формат, disabled)
- Все 258 тестов проходят

## 5. Создать config.yaml ✅
- Файл с настройками по умолчанию
- `log_enabled: false` по умолчанию
