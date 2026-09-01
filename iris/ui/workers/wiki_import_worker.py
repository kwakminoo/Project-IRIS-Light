"""백그라운드 위키 import (추출·요약·저장)."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.knowledge.wiki_import_ops import import_to_wiki
from iris.knowledge.wiki_summarize import summarize_for_wiki
from iris.knowledge.iris_wiki import IrisWiki


class WikiImportWorker(QThread):
    finished_ok = pyqtSignal(dict)
    finished_err = pyqtSignal(str)

    def __init__(
        self,
        wiki: IrisWiki,
        *,
        source: str,
        mode: str = "raw",
        title: str | None = None,
        rel_path: str | None = None,
        model: str = "",
        ollama_base_url: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._wiki = wiki
        self._source = source
        self._mode = mode
        self._title = title
        self._rel_path = rel_path
        self._model = model
        self._ollama_base_url = ollama_base_url

    def run(self) -> None:
        try:
            summarize_fn = None
            if self._mode == "summarize":
                model = (self._model or "").strip()
                if not model:
                    raise RuntimeError("요약 모드에는 모델 선택이 필요합니다.")
                base = (self._ollama_base_url or "http://127.0.0.1:11434/v1").strip()

                def _sum(text: str) -> str:
                    return summarize_for_wiki(
                        text,
                        model=model,
                        ollama_base_url=base,
                    )

                summarize_fn = _sum
            result = import_to_wiki(
                self._wiki,
                source=self._source,
                title=self._title,
                mode=self._mode,
                rel_path=self._rel_path,
                summarize_fn=summarize_fn,
            )
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))
            return
        self.finished_ok.emit(result)
