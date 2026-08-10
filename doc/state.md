# Текущее состояние проекта Deck

## Выполнено

- ✅ Базовые операции: REPLACE, DELETE, INSERT, INSERT_HEAD
- ✅ Парсер колод с поддержкой маркеров @ и $
- ✅ Операция REPLACE_REGEX — regex-замена по sed-синтаксису
  - Поддерживает разделители: `/`, `|`, `#`, `~`
  - Поддерживает флаги: `g` (глобальная замена)
  - Адресация: `N`, `N-M`, `N-`
- ✅ Операция APPEND — добавление строк в конец файла
  - Без адреса, без SKIP
- ✅ Логирование
  - Модуль `deck_editor.logger`
  - По умолчанию отключено (`log_enabled: false` в config.yaml)
  - Включается настройкой `log_enabled: true`
  - Формат: `2026-08-10T14:32:11 GET file=... addr=... lines=... chars=...`
  - События: GET, APPLY, REPLACE, REPLACE_REGEX, APPEND, END
- ✅ 258 тестов (91%+ покрытие core-модулей)
- ✅ Документация: SKILL.md, README.md, README.ru.md, spec.md

## Текущая ветка

- `main` — основная ветка, все изменения слиты

## Известные ограничения

- REPLACE_REGEX не поддерживает многострочные regex (без re.MULTILINE / re.DOTALL)
- APPEND не поддерживает SKIP
