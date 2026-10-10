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
        content: str = "",
        db=None,
        project_root: str = "",
        settings=None,
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
        self._content = content
        self._db = db
        self._project_root = project_root
        self._settings = settings

    def run(self) -> None:
        try:
            from iris.knowledge.page_vision import transcribe_images
            from iris.knowledge.wiki_import_ops import save_answer_to_wiki

            model = (self._model or "").strip()
            base = (self._ollama_base_url or "http://127.0.0.1:11434/v1").strip()
            summarize_fn = None
            vision = None
            if model:
                from iris.runtime.backend_route import vision_endpoint

                spec = vision_endpoint(self._db, model, ollama_base_url=base)

                def _sum(text: str) -> str:
                    return summarize_for_wiki(
                        text,
                        model=model,
                        ollama_base_url=base,
                        settings=self._settings,
                        db=self._db,
                    )

                def vision(pngs: list[bytes]) -> str:
                    return transcribe_images(pngs, **spec)

                summarize_fn = _sum
            filing = {}
            if self._db is not None:
                from iris.knowledge.wiki_filing import filing_kwargs
                from iris.storage.failover_prefs import load_history_settings

                filing = filing_kwargs(
                    db=self._db,
                    base_url=self._ollama_base_url,
                    history_settings=load_history_settings(self._db),
                    model=self._model,
                    project_root=self._project_root,
                    settings=self._settings,
                )
            if (self._content or "").strip():
                result = save_answer_to_wiki(
                    self._wiki,
                    title=self._title or "검색 결과",
                    content=self._content,
                    summarize_fn=summarize_fn,
                    **filing,
                )
            else:
                result = import_to_wiki(
                    self._wiki,
                    source=self._source,
                    title=self._title,
                    mode=self._mode,
                    rel_path=self._rel_path,
                    summarize_fn=summarize_fn,
                    vision_reader=vision,
                    **filing,
                )
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))
            return
        self.finished_ok.emit(result)


class WikiCommandWorker(QThread):
    """요약·문단 번역이 필요한 위키 명령. 모델 호출은 UI 스레드 밖."""

    finished_ok = pyqtSignal(dict)
    finished_err = pyqtSignal(str)

    def __init__(
        self,
        wiki: IrisWiki,
        command: object,
        *,
        model: str = "",
        ollama_base_url: str = "",
        db=None,
        project_root: str = "",
        settings=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._wiki = wiki
        self._command = command
        self._model = model
        self._ollama_base_url = ollama_base_url
        self._db = db
        self._project_root = project_root
        self._settings = settings

    def run(self) -> None:
        try:
            from iris.knowledge.wiki_command import WikiCommand
            from iris.knowledge.wiki_ops import execute_wiki_command
            from iris.knowledge.wiki_summarize import summarize_for_wiki, translate_for_wiki

            command = self._command
            if not isinstance(command, WikiCommand):
                raise RuntimeError("wiki command required")
            model = (self._model or "").strip()
            base = (self._ollama_base_url or "http://127.0.0.1:11434/v1").strip()
            if command.needs_model() and not model:
                raise RuntimeError("요약·번역에는 모델 선택이 필요합니다.")

            from iris.knowledge.page_vision import transcribe_images
            from iris.runtime.backend_route import vision_endpoint

            spec = vision_endpoint(self._db, model, ollama_base_url=base)

            def _sum(text: str) -> str:
                return summarize_for_wiki(
                    text, model=model, ollama_base_url=base,
                    settings=self._settings, db=self._db,
                )

            def _tr(text: str) -> str:
                return translate_for_wiki(
                    text, model=model, ollama_base_url=base,
                    settings=self._settings, db=self._db,
                )

            def _vision(pngs: list[bytes]) -> str:
                return transcribe_images(pngs, **spec)

            filing: dict = {}
            if self._db is not None:
                from iris.knowledge.wiki_filing import filing_kwargs
                from iris.storage.failover_prefs import load_history_settings

                filing = filing_kwargs(
                    db=self._db,
                    base_url=base,
                    history_settings=load_history_settings(self._db),
                    model=model,
                    project_root=self._project_root,
                    settings=self._settings,
                )
            result = execute_wiki_command(
                self._wiki,
                command,
                summarize_fn=_sum if model else None,
                translate_fn=_tr if command.translate else None,
                vision_reader=_vision if model else None,
                filing=filing,
            )
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))
            return
        self.finished_ok.emit(result)
