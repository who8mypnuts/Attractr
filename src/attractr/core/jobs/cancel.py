"""Cooperative cancellation shared by engines, workers and the CLI.

Two levels: :meth:`CancelToken.cancel` aborts (``check()`` raises :class:`Cancelled`),
:meth:`CancelToken.finish` is a *soft* stop — engines stop accumulating at the next pass
boundary and return what they have as a complete result, so a long render can be "finished
now" and still be developed, saved and reported.
"""

from __future__ import annotations

import threading


class Cancelled(Exception):
    """Raised by :meth:`CancelToken.check` when cancellation was requested."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._finish = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def finish(self) -> None:
        """Ask for a soft stop: keep the work done so far and wrap up."""
        self._finish.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def finishing(self) -> bool:
        return self._finish.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()

    def reset(self) -> None:
        self._event.clear()
        self._finish.clear()


NEVER = CancelToken()  # a token that is never cancelled (headless defaults)
