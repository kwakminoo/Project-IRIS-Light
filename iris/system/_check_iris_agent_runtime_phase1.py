"""Phase 1 Iris Agent 기준선 자검.

- pin 파일 == load_pinned_sha
- update 가 pin 밖 floating main 을 쓰지 않음
- 홈이 iris_agent_home / hermes_home 단일 경로
- ollama guard 는 present API 가 있고 gateway 경로가 부재 시 apply 1회
- 설치본이 있으면 HEAD == pin 이고 guard present (멱등)
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from unittest import mock

from iris.infrastructure.agent_runtime import (
    iris_agent_home,
    load_pinned_sha,
    load_upstream_url,
    product_agent_home,
    vendor_runtime_root,
)
from iris.infrastructure.hermes_credentials import hermes_home
from iris.system import hermes_gateway as gw
from iris.system import hermes_update as upd
from iris.system.hermes_ollama_guard import ollama_options_guard_present


def _main() -> None:
    pin = load_pinned_sha()
    assert pin == (vendor_runtime_root() / "PIN").read_text(encoding="utf-8").strip().split()[0]
    assert load_upstream_url().startswith("https://")
    assert "NousResearch/hermes-agent" in load_upstream_url()

    # update 목표 = pin (네트워크 floating main 추격 아님)
    assert upd.fetch_hermes_remote_sha(Path(".")) == pin
    src = inspect.getsource(upd.check_hermes_update)
    assert "ls-remote" not in src
    assert "load_pinned_sha" in inspect.getsource(upd)
    assert "refs/heads/main" not in inspect.getsource(upd)

    with tempfile.TemporaryDirectory(prefix="iris-agent-home-") as tmp:
        product = Path(tmp) / "agent"
        product.mkdir()
        with mock.patch.dict("os.environ", {"IRIS_AGENT_HOME": str(product)}, clear=False):
            assert iris_agent_home() == product
            assert hermes_home() == product
        legacy_only = Path(tmp) / "legacy-local"
        legacy_only.mkdir()
        (legacy_only / "hermes").mkdir()
        with mock.patch.dict(
            "os.environ",
            {"LOCALAPPDATA": str(legacy_only), "IRIS_AGENT_HOME": ""},
            clear=False,
        ):
            home = iris_agent_home()
            assert home == product_agent_home()
            assert home != legacy_only / "hermes"

    # credentials 와 sync 가 같은 홈
    from iris.system import hermes_iris_control_sync as sync

    assert hermes_home() == sync.hermes_home() == iris_agent_home()

    # gateway ensure: 부재 시 apply, 이미 있으면 False(멱등)
    gsrc = inspect.getsource(gw._apply_ollama_options_guard_now)
    assert "apply_ollama_options_guard" in gsrc
    assert "ollama_options_guard_present" in gsrc

    repo = upd.hermes_repo_dir()
    if repo is not None and (repo / ".git").exists():
        local = upd._git(repo, "rev-parse", "HEAD")
        status = upd.check_hermes_update(repo=repo)
        assert status.remote_sha.lower() == pin.lower()
        if local.lower() == pin.lower():
            assert not status.available
            assert status.detail == "최신"
            assert ollama_options_guard_present(repo), "pin checkout must carry absorbed guard"
            assert gw._apply_ollama_options_guard_now() is False
        else:
            assert status.available
            print("note: installed HEAD != pin; update would move to pin", local[:7], pin[:7])

    # present / bare / gateway apply-on-missing
    with tempfile.TemporaryDirectory(prefix="iris-guard-") as tmp:
        fake = Path(tmp)
        custom = fake / "plugins" / "model-providers" / "custom"
        custom.mkdir(parents=True)
        (custom / "__init__.py").write_text(
            "if ollama_num_ctx and _looks_like_ollama_endpoint(ctx.get('base_url')):\n    pass\n",
            encoding="utf-8",
        )
        assert ollama_options_guard_present(fake)
        bare = Path(tmp) / "bare"
        (bare / "plugins" / "model-providers" / "custom").mkdir(parents=True)
        (bare / "plugins" / "model-providers" / "custom" / "__init__.py").write_text(
            "if ollama_num_ctx:\n    x['options'] = {}\n",
            encoding="utf-8",
        )
        assert not ollama_options_guard_present(bare)
        with mock.patch.object(gw, "_hermes_agent_dir", return_value=bare):
            assert gw._apply_ollama_options_guard_now() is True
            assert ollama_options_guard_present(bare)
            assert gw._apply_ollama_options_guard_now() is False

    assert len(pin) >= 40
    print("iris_agent_runtime_phase1 ok", pin[:7], iris_agent_home())


if __name__ == "__main__":
    _main()
