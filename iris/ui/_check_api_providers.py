"""API providers + OpenAI compat + 라우팅 id self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.infrastructure.openai_compat_client import normalize_base_url
from iris.infrastructure.ollama_client import OllamaModelInfo
from iris.storage.api_providers import (
    ApiProvider,
    is_api_runtime_model,
    load_api_providers,
    parse_runtime_model_id,
    runtime_model_id,
    save_api_providers,
)
from iris.storage.database import Database


def main() -> int:
    assert normalize_base_url("https://api.openai.com") == "https://api.openai.com/v1"
    assert parse_runtime_model_id("api:ab12:gpt-4o") == ("ab12", "gpt-4o")
    assert is_api_runtime_model("api:x:y")
    assert not is_api_runtime_model("llama3")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = Database(Path(td) / "t.db")
        p = ApiProvider(
            name="Demo",
            base_url="https://example.com/v1",
            api_key="sk-test",
            models=["gpt-4o"],
            status="ok",
        )
        save_api_providers(db, [p])
        loaded = load_api_providers(db)
        assert len(loaded) == 1
        assert loaded[0].name == "Demo"
        assert loaded[0].status == "ok"
        rid = runtime_model_id(loaded[0].id, "gpt-4o")
        info = OllamaModelInfo(name=rid, catalog_name=f"{loaded[0].name} · gpt-4o")
        assert info.catalog_name.startswith("Demo")
        assert is_api_runtime_model(info.name)
        try:
            db._conn.close()
        except Exception:
            pass

    print("api_provider_integration self-check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
