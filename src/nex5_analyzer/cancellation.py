"""Thread-safe cooperative cancellation primitives."""

from __future__ import annotations

import threading


class CancelledError(Exception):
    """Raised when a task is cancelled by the user."""


class CancellationToken:
    """Thread-safe cancellation token for cooperative task cancellation."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def check(self) -> None:
        """Raise CancelledError if cancelled."""
        if self._cancelled.is_set():
            raise CancelledError("操作已被用户取消。")
