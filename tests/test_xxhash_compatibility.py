"""Регрессионный тест на совместимость xxhash (зависит от версии).

Почему он нужен:
    deck_editor.utils.compute_content_hash() вызывает xxhash.xxh64() со
    СТРОКОЙ. В старых версиях xxhash (например 3.8.1) это работало, но в
    новых (4.0.2 и выше) C-расширение требует bytes и падает с ошибкой
    "Strings must be encoded before hashing". Из-за этого падали ВСЕ
    операции записи (apply/create).

    Этот тест ловит именно такую несовместимость: он должен УПАДАТЬ, если
    installed xxhash не принимает строку, и РАБОТАТЬ на любой версии.

Запуск:
    - pytest:   python -m pytest tests/test_xxhash_compatibility.py
    - без pytest: python tests/test_xxhash_compatibility.py
    Второй способ полезен, если pytest ещё не установлен в окружении.
"""

from __future__ import annotations

import re

import xxhash

from deck_editor.utils import compute_content_hash

_HEX16 = re.compile(r"^[0-9a-f]{16}$")


def _canonical(content: str) -> str:
    """Этлонный хэш: то, что даёт явная передача bytes в utf-8."""
    return xxhash.xxh64(content.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Тесты (именуются test_* — их видит pytest)
# --------------------------------------------------------------------------
def test_content_hash_accepts_str():
    """compute_content_hash принимает СТРОКУ и возвращает 16-значный hex.

    Прямой регресс: на несовместимой xxhash эта строка падает с TypeError.
    """
    h = compute_content_hash("hello")
    assert isinstance(h, str), "хэш должен быть строкой"
    assert _HEX16.match(h), f"ожидается 16 hex-символов, получено: {h!r}"


def test_content_hash_matches_bytes_canonical():
    """Результат равен каноническому хэту через bytes.

    Гарантирует кросс-версионную корректность: на любой версии xxhash
    compute_content_hash даёт тот же результат, что явный .encode("utf-8").
    """
    for s in ["hello", "Привет 🚀", "", "a" * 5000]:
        assert compute_content_hash(s) == _canonical(s), f"расхождение для {s!r}"


def test_content_hash_utf8_stable():
    """Юникод/эмодзи хешируются без ошибок и стабильно (повторно)."""
    s = "Привет мир 🚀🎉"
    first = compute_content_hash(s)
    second = compute_content_hash(s)
    assert _HEX16.match(first)
    assert first == second


# --------------------------------------------------------------------------
# Автономный запуск без pytest (на случай, если pytest не установлен)
# --------------------------------------------------------------------------
def _run_standalone() -> int:
    tests = [
        name
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]
    tests.sort()
    failures = 0
    for name in tests:
        try:
            globals()[name]()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001 — хотим увидеть любую проблему
            failures += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} прошло")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
