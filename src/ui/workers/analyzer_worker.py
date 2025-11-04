from __future__ import annotations

from typing import Iterable
from threading import Event

from PySide6.QtCore import QThread, Signal

from domain.models import AnalysisSummary, SymbolRecord
from services.analyzer import AnalyzerService


class AnalyzerWorker(QThread):
    progress = Signal(object, int, int, tuple)
    completed = Signal(tuple)
    failed = Signal(str)
    finished = Signal(bool, tuple)

    def __init__(
        self,
        service: AnalyzerService,
        symbols: Iterable[SymbolRecord],
        *,
        force_refresh: bool = False,
    ) -> None:
        super().__init__()
        self._service = service
        self._symbols = list(symbols)
        self._force_refresh = force_refresh
        self._cancel_event = Event()
        self._results: list[AnalysisSummary] = []

    def run(self) -> None:  # type: ignore[override]
        try:
            self._results = self._service.analyze_symbols(
                self._symbols,
                force_refresh=self._force_refresh,
                progress_callback=self._handle_progress,
                cancel_event=self._cancel_event,
            )
            self.completed.emit(tuple(self._results))
            self.finished.emit(self._cancel_event.is_set(), tuple(self._service.errors))
        except Exception as exc:  # pragma: no cover - runtime failure path
            self.failed.emit(str(exc))
            self.finished.emit(self._cancel_event.is_set(), tuple(self._service.errors))

    def cancel(self) -> None:
        self._cancel_event.set()

    def _handle_progress(
        self,
        summary: AnalysisSummary | None,
        completed: int,
        total: int,
        errors: tuple[str, ...],
    ) -> None:
        self.progress.emit(summary, completed, total, errors)
