"""Phase 4: 제품 홈·마이그레이션·채팅 정본·핀 계약 자검."""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path
from unittest import mock

from iris.infrastructure import agent_runtime as ar
from iris.infrastructure.agent_runtime import (
    ensure_iris_agent_home,
    iris_agent_home,
    legacy_agent_home,
    load_pinned_sha,
    migrate_legacy_agent_home,
    product_agent_home,
    vendor_runtime_root,
)
from iris.infrastructure.hermes_credentials import hermes_home
from iris.runtime.chat_canonical import (
    AGENT_SESSION_DB_ROLE,
    CHAT_PRODUCT_OF_RECORD,
    is_chat_product_of_record,
)
from iris.system import hermes_install as install
from iris.system import hermes_update as upd


def _check_pin_contract() -> None:
    pin = load_pinned_sha()
    assert pin == (vendor_runtime_root() / "PIN").read_text(encoding="utf-8").strip().split()[0]
    assert upd.fetch_hermes_remote_sha(Path(".")) == pin
    assert "load_pinned_sha" in inspect.getsource(upd)
    assert "ls-remote" not in inspect.getsource(upd.check_hermes_update)
    assert "load_pinned_sha" in inspect.getsource(install)


def _check_home_prefers_product() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-p4-home-") as tmp:
        root = Path(tmp)
        product = root / "agent"
        legacy = root / "hermes"
        legacy.mkdir()
        (legacy / ".env").write_text("API_SERVER_KEY=phase4-test-key-xxxxxxxxxxxxxxxx\n", encoding="utf-8")
        (legacy / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (legacy / "memories").mkdir()
        (legacy / "memories" / "note.md").write_text("hi\n", encoding="utf-8")

        env = {
            "IRIS_AGENT_HOME": str(product),
            "LOCALAPPDATA": str(root),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            assert product_agent_home() == product
            assert iris_agent_home() == product
            assert hermes_home() == product
            # 레거시가 있어도 활성 홈은 제품 경로 (폴백 금지)
            assert legacy_agent_home() == legacy
            assert iris_agent_home() != legacy

            dry = migrate_legacy_agent_home(dry_run=True)
            assert dry.ok and dry.dry_run
            assert not product.exists() or not (product / ".env").exists()
            assert ".env" in dry.copied or "config.yaml" in dry.copied

            live = migrate_legacy_agent_home(dry_run=False)
            assert live.ok
            assert (product / ".env").is_file()
            assert (product / "config.yaml").is_file()
            assert (product / "memories" / "note.md").is_file()
            assert (product / ar._MIGRATE_STAMP).is_file()
            # 원본 보존
            assert (legacy / ".env").is_file()

            again = migrate_legacy_agent_home(dry_run=False)
            assert again.ok and again.message == "already migrated"

            home = ensure_iris_agent_home()
            assert home == product
            assert home.is_dir()


def _check_no_legacy_active_writer() -> None:
    """iris_agent_home 본문이 레거시 폴백 없이 product 만 반환한다."""
    body = inspect.getsource(ar.iris_agent_home).split('"""', 2)[-1]
    assert "product_agent_home" in body
    assert "legacy_agent_home" not in body
    assert "os.environ" not in body
    assert "LOCALAPPDATA" not in body


def _check_chat_canonical() -> None:
    assert CHAT_PRODUCT_OF_RECORD == "iris_sqlite_chat_messages"
    assert is_chat_product_of_record(CHAT_PRODUCT_OF_RECORD)
    assert not is_chat_product_of_record("hermes_session_db")
    assert AGENT_SESSION_DB_ROLE.startswith("runtime_")
    # ChatSession 모듈이 정본 모듈을 문서화
    from iris.runtime import chat_session as cs

    assert "chat_canonical" in (cs.__doc__ or "")


def _check_ensure_wired() -> None:
    from iris.system import hermes_gateway as gw

    src = inspect.getsource(gw.ensure_hermes_gateway_running)
    assert "ensure_iris_agent_home" in src


def _main() -> None:
    _check_pin_contract()
    _check_home_prefers_product()
    _check_no_legacy_active_writer()
    _check_chat_canonical()
    _check_ensure_wired()
    print(
        "iris_agent_home_phase4 ok",
        load_pinned_sha()[:7],
        iris_agent_home(),
        CHAT_PRODUCT_OF_RECORD,
    )


if __name__ == "__main__":
    _main()
