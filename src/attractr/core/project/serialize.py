"""Generic dataclass ⇄ JSON-compatible dict conversion.

Rules: dataclasses recurse; tuples become lists (and back, guided by type hints);
objects exposing ``to_dict``/``from_dict`` (e.g. :class:`Gradient`) use them; ``None``
passes through; unions like ``float | None`` are handled; unknown keys are ignored so old
files keep loading after fields are added.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

T = TypeVar("T")


def to_dict(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return fields_to_dict(obj)
    if isinstance(obj, tuple | list):
        return [to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in obj.items()}
    return obj


def fields_to_dict(obj: Any) -> dict[str, Any]:
    """Serialise a dataclass field by field (ignores the object's own ``to_dict``, so a
    class may implement ``to_dict`` as ``fields_to_dict(self)`` plus tweaks)."""
    return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}


def from_dict(cls: type[T], data: Any) -> T:
    return _convert(cls, data)


def fields_from_dict(cls: type[T], data: dict[str, Any]) -> T:
    """Inverse of :func:`fields_to_dict` — builds ``cls`` from its fields, ignoring the
    class's own ``from_dict`` (so ``from_dict`` implementations can call this)."""
    hints = get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        if f.name in data:
            kwargs[f.name] = _convert(hints[f.name], data[f.name])
    return cls(**kwargs)


def _convert(tp: Any, data: Any) -> Any:
    if data is None:
        return None
    origin = get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return _convert(args[0], data)
        for a in args:  # first type that accepts the value
            try:
                return _convert(a, data)
            except (TypeError, ValueError, KeyError):
                continue
        return data
    if hasattr(tp, "from_dict") and isinstance(data, dict) and not dataclasses.is_dataclass(tp):
        return tp.from_dict(data)
    if dataclasses.is_dataclass(tp):
        if hasattr(tp, "from_dict"):
            return tp.from_dict(data)
        return fields_from_dict(tp, data)
    if origin is tuple:
        args = get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_convert(args[0], v) for v in data)
        if args:
            return tuple(_convert(a, v) for a, v in zip(args, data, strict=False))
        return tuple(data)
    if origin is list:
        (a,) = get_args(tp) or (Any,)
        return [_convert(a, v) for v in data]
    if origin is dict:
        k, v = get_args(tp) or (Any, Any)
        return {kk: _convert(v, vv) for kk, vv in data.items()}
    if tp is float:
        return float(data)
    if tp is int:
        return int(data)
    if tp is bool:
        return bool(data)
    if tp is str:
        return str(data)
    return data
