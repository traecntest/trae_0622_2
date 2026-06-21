from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal, QObject

from ui.api_client import ApiClient, ApiError


class ApiWorker(QThread):
    finished_ok = Signal(object)
    finished_err = Signal(str)
    started_request = Signal(str)
    cancelled = Signal()

    def __init__(self, func: Callable[..., Any], *args,
                 label: str = "", parent: QObject | None = None, **kwargs):
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._label = label
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        if self._label:
            self.started_request.emit(self._label)
        try:
            result = self._func(*self._args, **self._kwargs)
            if self._cancelled:
                self.cancelled.emit()
                return
            self.finished_ok.emit(result)
        except ApiError as e:
            if self._cancelled:
                self.cancelled.emit()
                return
            self.finished_err.emit(str(e))
        except Exception as e:
            if self._cancelled:
                self.cancelled.emit()
                return
            self.finished_err.emit(f"{type(e).__name__}: {e}")


def run_api(func: Callable[..., Any], on_ok: Callable[[Any], None],
            on_err: Callable[[str], None] | None = None,
            on_start: Callable[[str], None] | None = None,
            on_cancel: Callable[[], None] | None = None,
            label: str = "", parent: QObject | None = None,
            *args, **kwargs) -> ApiWorker:
    worker = ApiWorker(func, *args, label=label, parent=parent, **kwargs)
    worker.finished_ok.connect(on_ok)
    if on_err:
        worker.finished_err.connect(on_err)
    else:
        worker.finished_err.connect(lambda m: None)
    if on_start:
        worker.started_request.connect(on_start)
    if on_cancel:
        worker.cancelled.connect(on_cancel)
    worker.finished_ok.connect(worker.deleteLater)
    worker.finished_err.connect(worker.deleteLater)
    worker.cancelled.connect(worker.deleteLater)
    worker.start()
    return worker
