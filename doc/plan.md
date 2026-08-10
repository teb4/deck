# План: Добавление операций @REPLACE (regex) и @APPEND

## 1. Анализ текущего состояния
    1.1 Изучить текущую реализацию операций (parser.py, operations.py, apply.py)
    1.2 Определить точки расширения для новых операций
    1.3 Проверить существующие тесты

## 2. Добавить операцию @REPLACE (regex-замена)
    2.1 Добавить "REPLACE_REGEX" в OPERATION_NAMES в parser.py
    2.2 Добавить парсинг операции REPLACE_REGEX в _parse_operation
    2.3 Добавить валидацию операции в _validate_parsed_operations
    2.4 Добавить валидацию в operations.py (_validate_single)
    2.5 Реализовать _apply_replace_regex в operations.py
    2.6 Добавить форматирование в apply.py (_format_diff, _format_apply)

## 3. Добавить операцию @APPEND
    3.1 Добавить "APPEND" в OPERATION_NAMES в parser.py
    3.2 Добавить парсинг операции APPEND в _parse_operation
    3.3 Добавить валидацию операции в _validate_parsed_operations
    3.4 Добавить валидацию в operations.py (_validate_single)
    3.5 Реализовать _apply_append в operations.py
    3.6 Добавить форматирование в apply.py (_format_diff, _format_apply)

## 4. Написание тестов
    4.1 Тесты для REPLACE_REGEX (парсинг, применение, ошибки)
    4.2 Тесты для APPEND (парсинг, применение, ошибки)
    4.3 Интеграционные тесты

## 5. Обновление документации
    5.1 Обновить SKILL.md
    5.2 Обновить spec.md
    5.3 Обновить README.md / README.ru.md

## 6. Проверка
    6.1 Запуск всех тестов
    6.2 Проверка покрытия >90%
