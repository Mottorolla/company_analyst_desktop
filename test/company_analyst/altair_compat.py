from __future__ import annotations

import inspect
import typing


def _ensure_closed_typeddict_support() -> bool:
    """Make Altair's generated ``TypedDict(..., closed=True)`` portable.

    Some Python releases expose ``typing.TypedDict`` without the PEP 728
    ``closed`` keyword while Altair selects that implementation.  The current
    typing-extensions backport supports the keyword, so it is safe to use as a
    compatibility bridge before importing Altair.
    """
    meta = getattr(typing, "_TypedDictMeta", None)
    if meta is None:
        return False
    try:
        supports_closed = "closed" in inspect.signature(meta.__new__).parameters
    except (TypeError, ValueError):
        supports_closed = False
    if supports_closed:
        return False

    from typing_extensions import TypedDict as ExtendedTypedDict

    typing.TypedDict = ExtendedTypedDict
    return True


def load_altair():
    _ensure_closed_typeddict_support()
    try:
        import altair
    except Exception as exc:
        raise RuntimeError(
            "Не удалось загрузить Altair. Закройте приложение и запустите "
            "repair_windows.bat, затем повторите запуск. "
            f"Техническая причина: {exc}"
        ) from exc
    return altair
