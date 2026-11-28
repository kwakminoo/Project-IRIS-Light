"""FFC-05: store-bound extraction/OCR memo (process LRU + TEMP spill)."""

from __future__ import annotations

import atexit
import gzip
import hashlib
import json
import shutil
import tempfile
import time
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MAX_ENTRIES = 32
_MAX_SPILL_BYTES = 64 * 1024 * 1024
_TTL_SEC = 2 * 60 * 60
_SPILL_THRESHOLD = 256 * 1024
_DPI = 130

_store_memos: weakref.WeakKeyDictionary[Any, "ExtractionMemo"] = weakref.WeakKeyDictionary()
_namespaces: set[str] = set()
_engine_once: dict[str, object] | None = None


@dataclass(frozen=True)
class ExtractionFingerprint:
    size: int
    mtime_ns: int
    page_from: int | None
    page_to: int | None
    page_limit: int | None
    kind: str
    ocr_language: str
    dpi: int
    vision_all: bool
    char_limit: int | None
    tess_ver: str
    pymupdf: bool

    def canonical(self) -> dict[str, object]:
        return {
            "content": {"size": self.size, "mtime_ns": self.mtime_ns},
            "window": {
                "page_from": self.page_from,
                "page_to": self.page_to,
                "page_limit": self.page_limit,
            },
            "method": {
                "kind": self.kind,
                "ocr_language": self.ocr_language,
                "dpi": self.dpi,
                "vision_all": self.vision_all,
                "char_limit": self.char_limit,
            },
            "engine": {"tess_ver": self.tess_ver, "pymupdf": self.pymupdf},
        }


@dataclass(frozen=True)
class ExtractionCacheKey:
    namespace: str
    attachment_id: str
    fingerprint: ExtractionFingerprint
    key_hash: str

    @classmethod
    def build(
        cls,
        namespace: str,
        attachment_id: str,
        fingerprint: ExtractionFingerprint,
    ) -> "ExtractionCacheKey":
        payload = {
            "namespace": namespace,
            "attachment_id": attachment_id or "",
            "fingerprint": fingerprint.canonical(),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return cls(
            namespace=namespace,
            attachment_id=attachment_id or "",
            fingerprint=fingerprint,
            key_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )


@dataclass
class ExtractionCacheEntry:
    key_hash: str
    produced_at: float
    hits: int = 0
    result: dict[str, object] = field(default_factory=dict)
    spill_path: Path | None = None
    bytes_on_disk: int = 0
    attachment_id: str = ""


class ExtractionMemo:
    """Per-AttachmentStore extract memo; spill lives under TEMP."""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._entries: dict[str, ExtractionCacheEntry] = {}
        self._order: list[str] = []
        self._spill_bytes = 0
        self._spill_root = Path(tempfile.gettempdir()) / "iris-extract-cache" / namespace
        _namespaces.add(namespace)

    def __del__(self) -> None:  # pragma: no cover - best-effort TEMP wipe
        try:
            self._wipe_spill_dir(forget_namespace=True)
        except Exception:
            pass

    def _wipe_spill_dir(self, *, forget_namespace: bool = False) -> None:
        root = self._spill_root
        if root.is_dir():
            shutil.rmtree(root, ignore_errors=True)
        if forget_namespace:
            _namespaces.discard(self.namespace)

    def _touch(self, key_hash: str) -> None:
        if key_hash in self._order:
            self._order.remove(key_hash)
        self._order.append(key_hash)

    def _drop_entry(self, key_hash: str) -> None:
        entry = self._entries.pop(key_hash, None)
        if key_hash in self._order:
            self._order.remove(key_hash)
        if entry is None:
            return
        if entry.spill_path is not None:
            try:
                entry.spill_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._spill_bytes = max(0, self._spill_bytes - int(entry.bytes_on_disk or 0))

    def _evict_lru(self) -> None:
        while len(self._entries) > _MAX_ENTRIES and self._order:
            self._drop_entry(self._order[0])
        while self._spill_bytes > _MAX_SPILL_BYTES and self._order:
            self._drop_entry(self._order[0])

    def _load_result(self, entry: ExtractionCacheEntry) -> dict[str, object] | None:
        if entry.spill_path is not None:
            try:
                with gzip.open(entry.spill_path, "rt", encoding="utf-8") as fh:
                    spilled = json.load(fh)
                out = dict(entry.result)
                out["text"] = spilled.get("text", "")
                if "page_status" in spilled:
                    out["page_status"] = spilled["page_status"]
                return out
            except (OSError, json.JSONDecodeError, gzip.BadGzipFile):
                self._drop_entry(entry.key_hash)
                return None
        return dict(entry.result)

    def _spill_payload(
        self, result: dict[str, object]
    ) -> tuple[dict[str, object], Path | None, int]:
        text = str(result.get("text") or "")
        page_status = result.get("page_status")
        rough = len(text.encode("utf-8", errors="replace"))
        if isinstance(page_status, list):
            rough += len(json.dumps(page_status, ensure_ascii=False).encode("utf-8"))
        if rough <= _SPILL_THRESHOLD:
            return dict(result), None, 0
        self._spill_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(
            (text + json.dumps(page_status, ensure_ascii=False, default=str)).encode("utf-8")
        ).hexdigest()
        path = self._spill_root / f"{digest}.json.gz"
        payload = {"text": text, "page_status": page_status}
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        size = path.stat().st_size
        slim = {k: v for k, v in result.items() if k not in {"text", "page_status"}}
        slim["text"] = ""
        slim["page_status"] = []
        return slim, path, size


def fingerprint_for(
    path: Path,
    *,
    page_from: int | None,
    page_to: int | None,
    page_limit: int | None,
    ocr_language: str,
    vision_all: bool,
    char_limit: int | None,
    engine_probe: dict[str, object],
    kind: str | None = None,
) -> ExtractionFingerprint:
    st = path.stat()
    suffix = path.suffix.lower()
    resolved_kind = kind or ("pdf" if suffix == ".pdf" else "image")
    mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
    return ExtractionFingerprint(
        size=int(st.st_size),
        mtime_ns=mtime_ns,
        page_from=page_from,
        page_to=page_to,
        page_limit=page_limit,
        kind=resolved_kind,
        ocr_language=str(ocr_language or "kor+eng"),
        dpi=_DPI,
        vision_all=bool(vision_all),
        char_limit=char_limit,
        tess_ver=str(engine_probe.get("tess_ver") or ""),
        pymupdf=bool(engine_probe.get("pymupdf")),
    )


def make_key(
    memo: ExtractionMemo,
    fingerprint: ExtractionFingerprint,
    *,
    attachment_id: str = "",
) -> ExtractionCacheKey:
    return ExtractionCacheKey.build(memo.namespace, attachment_id or "", fingerprint)


def get(memo: ExtractionMemo, key: ExtractionCacheKey) -> dict[str, object] | None:
    entry = memo._entries.get(key.key_hash)
    if entry is None:
        return None
    if time.time() - entry.produced_at > _TTL_SEC:
        memo._drop_entry(key.key_hash)
        return None
    loaded = memo._load_result(entry)
    if loaded is None:
        return None
    entry.hits += 1
    memo._touch(key.key_hash)
    return _sanitize_source(loaded)


def put(memo: ExtractionMemo, key: ExtractionCacheKey, result: dict[str, object]) -> None:
    if _looks_like_error(result):
        return
    clean = _sanitize_source(dict(result))
    slim, spill_path, disk_bytes = memo._spill_payload(clean)
    if key.key_hash in memo._entries:
        memo._drop_entry(key.key_hash)
    entry = ExtractionCacheEntry(
        key_hash=key.key_hash,
        produced_at=time.time(),
        hits=0,
        result=slim,
        spill_path=spill_path,
        bytes_on_disk=disk_bytes,
        attachment_id=key.attachment_id or "",
    )
    memo._entries[key.key_hash] = entry
    memo._touch(key.key_hash)
    memo._spill_bytes += disk_bytes
    memo._evict_lru()


def invalidate(
    memo: ExtractionMemo,
    *,
    attachment_id: str | None = None,
    all: bool = False,
) -> int:
    if all:
        n = len(memo._entries)
        for key_hash in list(memo._entries):
            memo._drop_entry(key_hash)
        memo._wipe_spill_dir()
        return n
    if attachment_id is None:
        n = len(memo._entries)
        for key_hash in list(memo._entries):
            memo._drop_entry(key_hash)
        return n
    target = attachment_id or ""
    dropped = 0
    for key_hash, entry in list(memo._entries.items()):
        if entry.attachment_id == target:
            memo._drop_entry(key_hash)
            dropped += 1
    return dropped


def memo_for_store(store: Any) -> ExtractionMemo:
    existing = _store_memos.get(store)
    if existing is not None:
        return existing
    token = getattr(store, "session_token", None)
    if not token:
        token = f"store-{id(store):x}"
        try:
            store.session_token = token
        except Exception:
            pass
    memo = ExtractionMemo(str(token))
    _store_memos[store] = memo
    return memo


def default_engine_probe() -> dict[str, object]:
    global _engine_once
    if _engine_once is not None:
        return dict(_engine_once)
    tess_ver = ""
    try:
        from iris.knowledge.content_extract import _resolve_tesseract_cmd

        cmd = _resolve_tesseract_cmd()
        tess_ver = Path(cmd).name
        try:
            from subprocess import run

            from iris.system.win_subprocess import no_window_kwargs

            proc = run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=3,
                **no_window_kwargs(),
            )
            line = (proc.stdout or proc.stderr or "").splitlines()
            if line:
                tess_ver = line[0].strip()[:80]
        except Exception:
            pass
    except Exception:
        tess_ver = "missing"
    pymupdf_ok = False
    try:
        import pymupdf  # noqa: F401

        pymupdf_ok = True
    except ImportError:
        pymupdf_ok = False
    _engine_once = {"tess_ver": tess_ver, "pymupdf": pymupdf_ok}
    return dict(_engine_once)


def _sanitize_source(result: dict[str, object]) -> dict[str, object]:
    out = dict(result)
    raw = str(out.get("source") or "")
    if raw:
        try:
            p = Path(raw)
            if p.is_absolute() or len(p.parts) > 1:
                out["source"] = p.name
        except (OSError, ValueError, TypeError):
            out["source"] = Path(raw).name if raw else raw
    return out


def _looks_like_error(result: dict[str, object]) -> bool:
    code = str(result.get("error_code") or result.get("code") or "")
    if code.startswith(("PDF_", "OCR_", "VISION_")) or code == "EXTRACTION_CANCELLED":
        return True
    return False


def _atexit_sweep() -> None:
    base = Path(tempfile.gettempdir()) / "iris-extract-cache"
    for ns in list(_namespaces):
        shutil.rmtree(base / ns, ignore_errors=True)
    _namespaces.clear()
    if base.is_dir():
        try:
            next(base.iterdir())
        except StopIteration:
            shutil.rmtree(base, ignore_errors=True)
        except OSError:
            pass


atexit.register(_atexit_sweep)
