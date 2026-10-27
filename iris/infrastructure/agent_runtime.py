"""Iris Agent 런타임 기준선 — 홈·pin·install-time overlay (Phase 1+4).

기준선 선택: ``vendor/iris-agent-runtime`` (GitHub fork 아님).
전체 Hermes 트리를 모노레포에 넣지 않고, pin SHA + Iris soft-patch 흡수
계약만 제품이 소유한다. 설치는 업스트림을 pin 에만 checkout 한 뒤 overlay 를
한 번 적용한다. gateway 기동 경로에서는 소스 문자열 치환을 하지 않는다.

Phase 4: 활성 홈은 제품 경로만. 레거시 ``%LOCALAPPDATA%\\hermes`` 는
마이그레이션 원본이며 더 이상 쓰이지 않는다.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Lifetime policy (Phase 4b / §10.1 gate 4): keep-background.
# Iris quit does not stop the agent gateway process. login warm, HealthWorker,
# and setup may start it; co-terminate is not the product rule.

# 문서 §10 / 2026-10-27 런타임과 동일. vendor/iris-agent-runtime/PIN 이 우선.
IRIS_AGENT_PIN_SHA = "a382af23f4c067d23463b5781958684c2cda82bc"
IRIS_AGENT_UPSTREAM_URL = "https://github.com/NousResearch/hermes-agent.git"

_MIGRATE_STAMP = ".iris-agent-migrated-from"
# config / .env / memories only — hermes-agent checkout 은 pin 재설치.
_MIGRATE_FILES = (".env", "config.yaml", "MEMORY.md", "USER.md")
_MIGRATE_DIRS = ("memories", "skills")


def vendor_runtime_root() -> Path:
    return Path(__file__).resolve().parents[2] / "vendor" / "iris-agent-runtime"


def load_pinned_sha() -> str:
    pin_file = vendor_runtime_root() / "PIN"
    if pin_file.is_file():
        raw = pin_file.read_text(encoding="utf-8").strip().splitlines()
        if raw:
            sha = raw[0].strip().split()[0]
            if len(sha) >= 7 and all(c in "0123456789abcdefABCDEF" for c in sha):
                return sha
    return IRIS_AGENT_PIN_SHA


def load_upstream_url() -> str:
    url_file = vendor_runtime_root() / "UPSTREAM"
    if url_file.is_file():
        raw = url_file.read_text(encoding="utf-8").strip().splitlines()
        if raw and raw[0].strip().startswith("http"):
            return raw[0].strip()
    return IRIS_AGENT_UPSTREAM_URL


def product_agent_home() -> Path:
    """제품 홈 목표 경로. ``IRIS_AGENT_HOME`` 또는 ``~/.iris-light/agent``."""
    override = (os.environ.get("IRIS_AGENT_HOME") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".iris-light" / "agent"


def legacy_agent_home() -> Path:
    """구 Hermes 홈 (마이그레이션 원본만). 활성 쓰기에 쓰지 않는다."""
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        return Path(local) / "hermes"
    return Path.home() / ".hermes"


def iris_agent_home() -> Path:
    """활성 런타임 홈 하나. gateway·sync·install·warm 이 이 경로만 쓴다.

    Phase 4: 레거시 ``%LOCALAPPDATA%/hermes`` 로 폴백하지 않는다.
    이전 데이터는 ``migrate_legacy_agent_home`` / ``ensure_iris_agent_home`` 으로 복사한다.
    """
    return product_agent_home()


def iris_agent_repo_dir(home: Path | None = None) -> Path:
    return (home or iris_agent_home()) / "hermes-agent"


@dataclass
class AgentHomeMigrateResult:
    ok: bool
    dry_run: bool
    product: Path
    legacy: Path | None
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    message: str = ""


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _copy_file(src: Path, dst: Path, *, dry_run: bool) -> None:
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path, *, dry_run: bool) -> None:
    if dry_run:
        return
    if dst.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=False)


def migrate_legacy_agent_home(*, dry_run: bool = False) -> AgentHomeMigrateResult:
    """레거시 홈 → 제품 홈. 복사 후 전환. 원본 삭제 없음. 멱등.

    제품에 이미 같은 이름 파일이 있으면 skip (덮어쓰지 않음).
    stamp 가 있으면 재실행은 no-op.
    """
    product = product_agent_home()
    legacy = legacy_agent_home()
    stamp = product / _MIGRATE_STAMP

    if stamp.is_file() and not dry_run:
        return AgentHomeMigrateResult(
            ok=True,
            dry_run=dry_run,
            product=product,
            legacy=legacy if legacy.is_dir() else None,
            message="already migrated",
        )

    if not legacy.is_dir():
        return AgentHomeMigrateResult(
            ok=True,
            dry_run=dry_run,
            product=product,
            legacy=None,
            message="no legacy home",
        )

    if _same_path(product, legacy):
        return AgentHomeMigrateResult(
            ok=True,
            dry_run=dry_run,
            product=product,
            legacy=legacy,
            message="product is legacy path (IRIS_AGENT_HOME override)",
        )

    copied: list[str] = []
    skipped: list[str] = []

    if not dry_run:
        product.mkdir(parents=True, exist_ok=True)

    for name in _MIGRATE_FILES:
        src = legacy / name
        dst = product / name
        if not src.is_file():
            continue
        if dst.exists():
            skipped.append(name)
            continue
        try:
            _copy_file(src, dst, dry_run=dry_run)
            copied.append(name)
        except OSError as exc:
            return AgentHomeMigrateResult(
                ok=False,
                dry_run=dry_run,
                product=product,
                legacy=legacy,
                copied=copied,
                skipped=skipped,
                message=f"copy fail {name}: {exc}",
            )

    for name in _MIGRATE_DIRS:
        src = legacy / name
        dst = product / name
        if not src.is_dir():
            continue
        if dst.exists():
            skipped.append(name + "/")
            continue
        try:
            _copy_tree(src, dst, dry_run=dry_run)
            copied.append(name + "/")
        except OSError as exc:
            return AgentHomeMigrateResult(
                ok=False,
                dry_run=dry_run,
                product=product,
                legacy=legacy,
                copied=copied,
                skipped=skipped,
                message=f"copy fail {name}/: {exc}",
            )

    if not dry_run:
        try:
            stamp.write_text(str(legacy.resolve()) + "\n", encoding="utf-8")
        except OSError as exc:
            return AgentHomeMigrateResult(
                ok=False,
                dry_run=dry_run,
                product=product,
                legacy=legacy,
                copied=copied,
                skipped=skipped,
                message=f"stamp fail: {exc}",
            )

    return AgentHomeMigrateResult(
        ok=True,
        dry_run=dry_run,
        product=product,
        legacy=legacy,
        copied=copied,
        skipped=skipped,
        message="migrated" if copied else "nothing to copy",
    )


def ensure_iris_agent_home(*, dry_run: bool = False) -> Path:
    """마이그레이션 후 제품 홈을 돌려준다. 기동 입구 한곳용 (멱등)."""
    result = migrate_legacy_agent_home(dry_run=dry_run)
    if not result.ok:
        log.warning("iris agent home migrate: %s", result.message)
    home = product_agent_home()
    if not dry_run:
        try:
            home.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("iris agent home mkdir: %s", exc)
    return home


@dataclass
class IrisAgentRuntimeEnsureResult:
    """Supervisor ensure 결과. home 은 항상 제품 경로."""

    ok: bool
    home: Path
    gateway_ok: bool
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentLoopStandinResult:
    """Phase 5 Prove 0 — in-process loop stand-in outcome (stub, not product speak).

    mode is always ``stub`` until Merge replaces this with the real loop.
    Does not speak over HTTP gateway; product gateway path stays untouched.
    """

    ok: bool
    pin: str
    home: Path
    mode: str
    thread_name: str
    messages: tuple[str, ...] = ()


# Phase 5 Prove 2 — worker containment policy (documented domain, not ad-hoc ifs).
# Exception → failed payload / error result. These BaseExceptions still propagate.
AGENT_LOOP_PROPAGATE_BASE: tuple[type[BaseException], ...] = (
    SystemExit,
    KeyboardInterrupt,
)

# failed.emit / error-dict wire format: agent_failed|<ExcType>|<message>
AGENT_LOOP_FAILED_PREFIX = "agent_failed|"


def format_agent_loop_failure(exc: BaseException) -> str:
    """Clear failed payload for worker→UI (Prove 2). Prefer typed prefix over bare str."""
    msg = str(exc).replace("\n", " ").strip() or repr(exc)
    return f"{AGENT_LOOP_FAILED_PREFIX}{type(exc).__name__}|{msg}"


def ensure_agent_loop_no_console() -> bool:
    """Reuse product no-console contract on the agent prove / future loop path.

    Idempotent. Does not spawn a console; only installs CREATE_NO_WINDOW injection
    for any subprocess the agent path may open later.
    """
    from iris.system.win_subprocess import install_no_console_subprocess_patch

    return bool(install_no_console_subprocess_patch())


def run_agent_loop_standin(
    *,
    prompt: str = "prove0",
    force_fail: bool = False,
) -> AgentLoopStandinResult:
    """Minimal in-process agent-loop stand-in for Phase 5 Prove 0–3.

    Safe on a worker thread: no UI widgets, no sync UI calls, no gateway HTTP.
    UI may observe results only via QThread signals from
    ``IrisAgentLoopStandinWorker`` (never call this from a MainWindow slot body
    that does long work). Uses vendor pin + ``iris_agent_home`` only.
    Prove 2: installs no-console patch; ``force_fail`` returns ok=False (dict-like
    result) instead of requiring process kill. Prove 3: call via a handle that
    ``reset_agent_loop`` can replace while the UI host stays alive.
    """
    ensure_agent_loop_no_console()
    pin = load_pinned_sha()
    home = iris_agent_home()
    text = (prompt or "").strip() or "prove0"
    thread_name = threading.current_thread().name
    if force_fail:
        return AgentLoopStandinResult(
            ok=False,
            pin=pin,
            home=home,
            mode="stub",
            thread_name=thread_name,
            messages=(
                "mode=stub",
                format_agent_loop_failure(
                    RuntimeError("phase5-prove2 standin force_fail")
                ),
            ),
        )
    messages = (
        f"pin={pin[:12]}",
        f"home={home}",
        f"prompt_len={len(text)}",
        "mode=stub",
        "no_console=ensured",
    )
    return AgentLoopStandinResult(
        ok=True,
        pin=pin,
        home=home,
        mode="stub",
        thread_name=thread_name,
        messages=messages,
    )


# Phase 5 Prove 3 — hot-restart substitute (UI host stays; worker/loop replaced).
# Keys match the validation-plan "엔진만 핫리스타트" table.
AGENT_LOOP_RESET_COVERED = "covered_by_reset"
AGENT_LOOP_RESET_PROCESS = "needs_process_restart"
AGENT_LOOP_RESET_OUT_OF_SCOPE = "out_of_scope"

AGENT_LOOP_RESET_COVERAGE: dict[str, str] = {
    "gateway_hang": AGENT_LOOP_RESET_COVERED,
    "config_reload": AGENT_LOOP_RESET_COVERED,
    "soft_hang": AGENT_LOOP_RESET_COVERED,
    "mcp_skill_resync": AGENT_LOOP_RESET_COVERED,
    "pin_code_swap": AGENT_LOOP_RESET_PROCESS,
    "ollama_down": AGENT_LOOP_RESET_OUT_OF_SCOPE,
}


@dataclass
class AgentLoopHost:
    """UI-facing host identity. Fake for prove; real MainWindow later.

    Not a QWidget. Reset must keep the same object (``id`` stable).
    """

    label: str = "iris-agent-loop-host"


@dataclass
class AgentLoopHandle:
    """Single in-process loop session: sticky host + replaceable worker generation."""

    host: object
    generation: int = 0
    worker: object | None = None
    ephemeral: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentLoopResetResult:
    """Outcome of ``reset_agent_loop`` / ``replace_agent_loop_worker``."""

    ok: bool
    generation: int
    host_id: int
    host_same: bool
    pin: str
    pin_matches_vendor: bool
    messages: tuple[str, ...] = ()


_HANDLE_LOCK = threading.RLock()
_AGENT_LOOP_HANDLE: AgentLoopHandle | None = None


def pin_matches_vendor_pin() -> bool:
    """True when ``load_pinned_sha()`` equals the first token of vendor ``PIN``."""
    pin_file = vendor_runtime_root() / "PIN"
    loaded = load_pinned_sha()
    if not pin_file.is_file():
        return loaded == IRIS_AGENT_PIN_SHA and len(loaded) >= 7
    raw = pin_file.read_text(encoding="utf-8").strip().splitlines()
    if not raw:
        return False
    file_sha = raw[0].strip().split()[0]
    return loaded == file_sha and len(file_sha) >= 7


def ensure_agent_loop_handle(host: object | None = None) -> AgentLoopHandle:
    """Lazy single handle. Host is sticky once bound (Prove 3: UI survives reset)."""
    global _AGENT_LOOP_HANDLE
    with _HANDLE_LOCK:
        if _AGENT_LOOP_HANDLE is None:
            _AGENT_LOOP_HANDLE = AgentLoopHandle(
                host=host if host is not None else AgentLoopHost()
            )
        return _AGENT_LOOP_HANDLE


def clear_agent_loop_handle_for_tests() -> None:
    """Drop the process handle so a check can bind a fresh host. Not product speak."""
    global _AGENT_LOOP_HANDLE
    with _HANDLE_LOCK:
        _AGENT_LOOP_HANDLE = None


def attach_agent_loop_worker(worker: object) -> AgentLoopHandle:
    """Bind a new worker to the current generation (after reset or first spawn)."""
    handle = ensure_agent_loop_handle()
    with _HANDLE_LOCK:
        handle.worker = worker
    return handle


def _stop_agent_loop_worker(worker: object, wait_ms: int) -> None:
    quit_fn = getattr(worker, "quit", None)
    if callable(quit_fn):
        try:
            quit_fn()
        except Exception:  # noqa: BLE001 — dispose best-effort
            log.debug("agent loop worker quit failed", exc_info=True)
    wait_fn = getattr(worker, "wait", None)
    if callable(wait_fn):
        try:
            wait_fn(max(0, int(wait_ms)))
        except Exception:  # noqa: BLE001
            log.debug("agent loop worker wait failed", exc_info=True)


def reset_agent_loop(*, wait_ms: int = 5_000) -> AgentLoopResetResult:
    """Hot-restart substitute: cancel/clear worker, bump generation, keep host.

    Idempotent when already idle (no worker). Does not restart the OS process.
    pin/code swap still needs a full process restart (see AGENT_LOOP_RESET_COVERAGE).
    """
    handle = ensure_agent_loop_handle()
    host_before = handle.host
    host_id = id(host_before)
    with _HANDLE_LOCK:
        old = handle.worker
        handle.worker = None
        handle.ephemeral.clear()
        handle.generation += 1
        generation = handle.generation
    if old is not None:
        _stop_agent_loop_worker(old, wait_ms)
    pin = load_pinned_sha()
    matches = pin_matches_vendor_pin()
    host_same = handle.host is host_before and id(handle.host) == host_id
    return AgentLoopResetResult(
        ok=matches and host_same,
        generation=generation,
        host_id=host_id,
        host_same=host_same,
        pin=pin,
        pin_matches_vendor=matches,
        messages=(
            f"generation={generation}",
            f"host_same={host_same}",
            f"pin_matches_vendor={matches}",
            "reset=ok" if matches and host_same else "reset=degraded",
        ),
    )


def replace_agent_loop_worker(
    worker: object,
    *,
    wait_ms: int = 5_000,
) -> AgentLoopResetResult:
    """Reset then attach ``worker``. Host identity unchanged."""
    result = reset_agent_loop(wait_ms=wait_ms)
    attach_agent_loop_worker(worker)
    return result


def ensure_iris_agent_runtime(
    base_url: str = "http://127.0.0.1:8642/v1",
    *,
    api_key: str = "",
    command: str = "hermes",
    wait_sec: float = 45.0,
    should_abort: Callable[[], bool] | None = None,
    on_progress: Callable[[str], None] | None = None,
    provider: bool = True,
    start_gateway: bool = True,
) -> IrisAgentRuntimeEnsureResult:
    """Iris Agent 수명 supervisor — home → provider → gateway (멱등).

    setup / HermesHealthWorker / login warm 이 이 심볼만 통해 ensure 한다.
    Lifetime: keep-background (Iris 종료 후에도 gateway 유지 가능).
    """
    home = ensure_iris_agent_home()
    messages: list[str] = [f"home={home}"]
    # circular: hermes_gateway imports ensure_iris_agent_home from this module.
    from iris.system.hermes_gateway import (
        ensure_hermes_gateway_running,
        ensure_hermes_provider_config,
    )

    if provider:
        try:
            ensure_hermes_provider_config()
            messages.append("provider ok")
        except Exception as exc:  # noqa: BLE001
            messages.append(f"provider skip: {exc}")
            log.warning("iris agent runtime provider: %s", exc)

    if not start_gateway:
        gateway_ok = False
        messages.append("gateway skipped")
    else:
        gateway_ok = bool(
            ensure_hermes_gateway_running(
                base_url,
                api_key=api_key,
                command=command,
                wait_sec=wait_sec,
                should_abort=should_abort,
                on_progress=on_progress,
            )
        )
        messages.append("gateway ok" if gateway_ok else "gateway fail")

    # Hermes install/gateway가 업스트림 SOUL.md를 심은 뒤 Iris 페르소나로 되돌린다.
    try:
        from iris.system.hermes_soul_sync import ensure_soul

        messages.append(ensure_soul())
    except Exception as exc:  # noqa: BLE001
        messages.append(f"soul sync skip: {exc}")
        log.warning("iris agent runtime soul: %s", exc)

    return IrisAgentRuntimeEnsureResult(
        ok=gateway_ok if start_gateway else True,
        home=home,
        gateway_ok=gateway_ok,
        messages=messages,
    )


def apply_iris_agent_baseline_overlays(agent_root: Path) -> list[str]:
    """install/update 직후 1회. ollama options 가드를 기준선에 흡수한다.

    gateway ensure 는 가드 부재 시 ``apply_ollama_options_guard`` 만 직접 호출한다.
    dead-check 는 업스트림 pin 이 이미 고친 경우 verify 메시지만 남긴다.
    """
    root = Path(agent_root)
    messages: list[str] = []
    from iris.system.hermes_ollama_guard import (
        apply_ollama_options_guard,
        ollama_options_guard_present,
    )

    if ollama_options_guard_present(root):
        messages.append("ollama options guard: present in baseline")
    elif apply_ollama_options_guard(root):
        messages.append("ollama options guard: absorbed into baseline")
    else:
        messages.append("ollama options guard: pattern missing — warn")
        log.warning("iris agent baseline: ollama options guard not applied at %s", root)

    # circular: sync imports credentials → agent_runtime; mutate only at install.
    from iris.system.hermes_iris_control_sync import ensure_hermes_stdio_dead_check_patch

    messages.append(
        ensure_hermes_stdio_dead_check_patch(agent_root=root, mutate=True)
    )
    stamp = root / ".iris-agent-baseline"
    try:
        stamp.write_text(f"{load_pinned_sha()}\n", encoding="utf-8")
    except OSError as exc:
        messages.append(f"baseline stamp write fail: {exc}")
    return messages


if __name__ == "__main__":
    assert len(load_pinned_sha()) >= 7
    assert load_upstream_url().startswith("https://")
    home = iris_agent_home()
    assert isinstance(home, Path)
    assert iris_agent_repo_dir(home) == home / "hermes-agent"
    assert iris_agent_home() == product_agent_home()
    print("agent_runtime self-check ok", load_pinned_sha()[:7], home)
