"""Cooperative cancellation shared by engines, workers and the CLI."""

from __future__ import annotations

import threading


class Cancelled(Exception):
    """Raised by :meth:`CancelToken.check` when cancellation was requested."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()

    def reset(self) -> None:
        self._event.clear()


NEVER = CancelToken()  # a token that is never cancelled (headless defaults)
