"""같은 git 저장소를 쓰는 다음 대화에만 작업 폴더를 나눈다.

첫 대화는 본 체크아웃을 유지한다. 본 트리로 병합하지 않는다.
ponytail: 표는 프로세스 메모리만. 재시작 뒤에도 디스크 worktree 는 남고, 자동으로 지우지 않는다.
업그레이드는 대화 id를 디스크에 남기는 것. 병합은 그 업그레이드가 아니다.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class _Claim:
    conversation_id: int
    common: str
    path: str
    main: str
    branch: str


_LOCK = threading.Lock()
_BY_CID: dict[int, _Claim] = {}
_HOLDER: dict[str, int] = {}


def reset_worktrees() -> None:
    """테스트가 표를 비운다. 디스크는 지우지 않는다."""
    with _LOCK:
        _BY_CID.clear()
        _HOLDER.clear()


def conversation_id_of(window: Any, args: dict[str, Any] | None = None) -> int:
    payload = args or {}
    raw = payload.get("conversation_id")
    if raw is not None and str(raw).strip():
        return int(raw)
    slot = getattr(window, "_bound_slot", None)
    cid = getattr(slot, "conversation_id", None)
    if cid:
        return int(cid)
    return int(getattr(window, "_conversation_id", 0) or 0)


def is_chat_worktree(path: str) -> bool:
    try:
        parts = Path(path).expanduser().resolve().parts
    except OSError:
        parts = Path(path).parts
    return any(part.endswith(".iris-worktrees") for part in parts)


def work_root_for(conversation_id: int, requested: str) -> str:
    """이 대화가 볼 폴더. git 이 아니거나 worktree 를 못 만들면 requested."""
    raw = (requested or "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.exists():
        return raw
    try:
        resolved = path.resolve()
    except OSError:
        return raw
    cid = int(conversation_id)
    if is_chat_worktree(str(resolved)) and resolved.name == f"chat-{cid}":
        return str(resolved)
    try:
        common = _common_dir(resolved)
    except Exception:
        return str(resolved)
    if common is None:
        return str(resolved)
    main = _main_checkout(common)
    key = str(common)
    with _LOCK:
        held = _BY_CID.get(cid)
        if held is not None and held.common == key:
            return held.path
        owner = _HOLDER.get(key)
        if owner in (None, cid):
            claim = _Claim(cid, key, str(resolved), str(main), "")
            _BY_CID[cid] = claim
            _HOLDER[key] = cid
            return claim.path
    try:
        made = _add_worktree(main, cid)
    except Exception:
        return str(resolved)
    if made is None:
        return str(resolved)
    claim = _Claim(cid, key, str(made), str(main), f"iris/chat-{cid}")
    with _LOCK:
        _BY_CID[cid] = claim
    return claim.path


def describe_for_main(conversation_id: int, *, confirm: bool = False) -> dict[str, Any]:
    """본 트리에 쓰지 않는다. merged 는 항상 거짓이다."""
    with _LOCK:
        claim = _BY_CID.get(int(conversation_id))
    if claim is None:
        return {"ok": False, "merged": False, "error": "worktree 없음"}
    uses_main = not claim.branch
    body: dict[str, Any] = {
        "ok": uses_main or bool(confirm),
        "merged": False,
        "confirmed": bool(confirm),
        "main": claim.main,
        "worktree": claim.path,
        "branch": claim.branch,
        "uses_main": uses_main,
    }
    if not uses_main and not confirm:
        body["ok"] = False
        body["error"] = "confirm required"
    return body


def register_worktree_status(reg: Any, window: Any) -> None:
    from iris.system.control_surface import err_result, ok_result

    def _status(args: dict[str, Any]) -> dict[str, Any]:
        body = describe_for_main(
            conversation_id_of(window, args),
            confirm=bool(args.get("confirm")),
        )
        if body.get("ok"):
            return ok_result("project.worktree_status", body)
        return err_result(
            "project.worktree_status",
            str(body.get("error") or "confirm required"),
            body,
        )

    reg.register(
        "project.worktree_status",
        _status,
        summary=(
            "이 대화의 작업 폴더 경로만 보여 준다. "
            "confirm=true 여도 본 트리에 합치지 않는다. 가져가기는 사용자가 한다."
        ),
    )


def _run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    from iris.system.win_subprocess import no_window_kwargs

    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        **no_window_kwargs(),
    )


def _common_dir(path: Path) -> Path | None:
    proc = _run_git(path, ["rev-parse", "--git-common-dir"])
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    common = Path(text)
    if not common.is_absolute():
        common = (path / common).resolve()
    else:
        common = common.resolve()
    return common


def _main_checkout(common: Path) -> Path:
    return common.parent if common.name == ".git" else common.parent


def _add_worktree(main: Path, conversation_id: int) -> Path | None:
    dest = main.parent / f"{main.name}.iris-worktrees" / f"chat-{conversation_id}"
    if dest.exists():
        if _common_dir(dest) == _common_dir(main):
            return dest.resolve()
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    branch = f"iris/chat-{conversation_id}"
    proc = _run_git(main, ["worktree", "add", "-b", branch, str(dest), "HEAD"])
    if proc.returncode != 0:
        proc = _run_git(main, ["worktree", "add", str(dest), branch])
    if proc.returncode != 0 or not dest.is_dir():
        return None
    return dest.resolve()


if __name__ == "__main__":
    assert conversation_id_of(type("W", (), {"_conversation_id": 4})()) == 4
    assert is_chat_worktree(r"C:\repo.iris-worktrees\chat-2") is True
    assert is_chat_worktree(r"C:\repo") is False
    body = describe_for_main(9, confirm=True)
    assert body["merged"] is False and body["ok"] is False
    print("chat_worktree self-check ok")
