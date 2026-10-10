"""대화가 바뀔 때 세션 요약과 특성 노트를 백그라운드에서 남긴다."""

from __future__ import annotations

from PyQt6.QtCore import QThread

from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_session import SESSION_SYSTEM, close_session
from iris.storage.database import Database


class WikiSessionWorker(QThread):
    def __init__(
        self,
        db: Database,
        wiki: IrisWiki,
        conversation_id: int,
        messages: list,
        model: str,
        base_url: str,
        *,
        settings=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._wiki = wiki
        self._conversation_id = int(conversation_id or 0)
        self._messages = list(messages or [])
        self._model = model
        self._base_url = base_url
        self._settings = settings

    def run(self) -> None:
        try:
            from iris.runtime.backend_route import ask_selected_model, settings_for_model

            bound = settings_for_model(self._settings, self._base_url)

            def summarize(prompt: str) -> str:
                return ask_selected_model(
                    bound,
                    self._db,
                    self._model,
                    prompt,
                    system=SESSION_SYSTEM,
                    timeout_sec=90.0,
                )

            episode_dir = ""
            try:
                from iris.knowledge.project_wiki import project_episode_dir
                from iris.storage.chat_projects import project_for_conversation

                project = project_for_conversation(self._db, self._conversation_id)
                if project is not None:
                    episode_dir = project_episode_dir(project.wiki_slug)
            except Exception:
                episode_dir = ""
            close_session(
                self._db,
                self._wiki,
                conversation_id=self._conversation_id,
                messages=self._messages,
                summarize=summarize,
                model=self._model,
                episode_dir=episode_dir,
            )
        except Exception:
            return
