from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    result = Signal(int, object)
    error = Signal(int, str)


class AnalysisWorker(QRunnable):
    def __init__(self, request_id: int, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.request_id = request_id
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.callback(*self.args, **self.kwargs)
        except Exception as exc:  # pragma: no cover - UI error path
            self.signals.error.emit(self.request_id, f"{exc}\n{traceback.format_exc()}")
            return
        self.signals.result.emit(self.request_id, result)


class TaskWorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(object)
    finished = Signal()


class TaskWorker(QRunnable):
    def __init__(
        self,
        callback: Callable[..., Any],
        *args: Any,
        inject_progress: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.inject_progress = inject_progress
        self.signals = TaskWorkerSignals()

    def run(self) -> None:
        try:
            call_kwargs = dict(self.kwargs)
            if self.inject_progress and "progress_callback" not in call_kwargs:
                call_kwargs["progress_callback"] = self.signals.progress.emit
            result = self.callback(*self.args, **call_kwargs)
        except Exception as exc:  # pragma: no cover - UI error path
            self.signals.error.emit(f"{exc}\n{traceback.format_exc()}")
            self.signals.finished.emit()
            return
        self.signals.result.emit(result)
        self.signals.finished.emit()
