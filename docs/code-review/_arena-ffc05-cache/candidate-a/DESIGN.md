# FFC-05 Candidate A — Session-namespaced disk cache

Seat: arena A · Artifact: DESIGN only · No production code

## 1. Data shapes & structure

```text
ExtractionCache
  ns/<namespace>/entries/<key_hex>.json   # payload
  ns/<namespace>/index.json               # LRU + sizes + expiry
```

| Type | Fields |
|---|---|
| `CacheKey` | `namespace`, `content_fp` (blake2b-256 of file bytes), `size`, `mtime_ns`, `kind` (`pdf`\|`image`), `page_from`, `page_to`, `page_limit`, `ocr_language`, `render_dpi` (130), `ocr_engine` (`tesseract:<cmd_basename>+langs`), `method` (`text`\|`ocr`\|`hybrid` — filled on put from result), `char_limit` |
| `CacheEntry` | `key`, `created_at`, `expires_at`, `bytes`, `result` (subset of extract dict: `kind`, `text`, `title`, `truncated`, `incomplete`, `ocr_used`, `vision_used=false`, `note`, `total_pages`, `page_status`) |
| `CacheStats` | `hits`, `misses`, `bytes_used`, `entry_count` |

Organizing rule: one logical module, disk under `~/.iris-light/cache/extraction/`. Key material is **content fingerprint + range + OCR settings**, never basename/`attachment_id` alone. Absolute paths stay host-side only (not in `result.source` for attachment payloads).

## 2. Module boundary & public API

**Module:** `iris/knowledge/extraction_cache.py`  
**Does not:** run OCR, open PDFs, resolve attachments, talk to UI.  
**Owns:** key build, get/put/invalidate, size/TTL eviction, temp cleanup.

```python
def fingerprint_file(path: Path) -> tuple[str, int, int]: ...  # (blake2b_hex, size, mtime_ns)
def make_key(*, namespace, content_fp, size, mtime_ns, kind, page_from, page_to, page_limit, ocr_language, render_dpi=130, ocr_engine, char_limit) -> str: ...
def get(key: str, *, path: Path) -> dict | None: ...   # re-stat; miss if size/mtime/fp diverge
def put(key: str, result: dict, *, nbytes: int | None = None) -> None: ...
def invalidate(namespace: str | None = None, *, content_fp: str | None = None) -> int: ...
def purge_expired(*, now: float | None = None) -> int: ...
```

Defaults: `TTL=7d`, `MAX_BYTES_PER_NS=256MiB`, `MAX_ENTRIES_PER_NS=256`, global `MAX_BYTES=1GiB`. Evict LRU within namespace first.

## 3. Wire points (existing path)

```
content.extract → _checked_content_source → canonicalize → resolve_file
  → extract_from_source ──┬── PDF → read_pdf_pages   ← CACHE get/put (primary)
                          └── image → _ocr_for_document ← CACHE get/put
attachment_context (chip enrich) → read_pdf_pages      ← same primary
AttachmentStore.clear / detach / path-change error     ← invalidate(namespace)
```

- **Primary:** wrap body of `read_pdf_pages` — lookup after path open checks would succeed; put only on successful return (not on `DocumentExtractionError` / cancel).
- **Image:** same in `extract_from_source` image branch.
- **Skip cache when** `vision_reader is not None` or `vision_all` (model-dependent; never reuse).
- **Namespace:** `session:<ChatSession id>` or `store:<id(AttachmentStore)>` for chat; `anon` for bare path self-checks. Wiki `content.extract` uses the window’s session ns.
- Hit path still revalidates: `path.stat()` matches key `size`/`mtime_ns`; for attachments, caller already passed `resolve_file` (access still live). Mismatch → miss + invalidate that `content_fp`.

Preserve error codes unchanged (`PDF_*`, `OCR_*`, `EXTRACTION_CANCELLED`, …). Do not change `canonicalize_attachment_ref`.

## 4. Namespace / fingerprint / invalidation / limits

| Rule | Choice |
|---|---|
| Namespace | Session/store id; isolate principals; no cross-session hit |
| Fingerprint | Full-file blake2b-256 + size + mtime_ns (filename ignored) |
| OCR identity | language + render_dpi=130 + tesseract cmd basename + installed lang set |
| Invalidate | store `clear`/detach; file change (stat miss); `content_fp` delete; TTL expiry; size pressure |
| Temp | write `*.tmp` then replace; orphan `.tmp` deleted on purge |
| Provider payload | never put absolute path into cached `result` fields that leave the host |

## 5. Self-check plan

| File | Asserts |
|---|---|
| `iris/knowledge/_check_extraction_cache.py` | same bytes → hit; basename-only different path same bytes → hit; edit mtime/size → miss; different `ocr_language` → miss; different page window → miss; `invalidate(ns)` drops entries; oversize put triggers eviction; expired entry purged; vision_reader path not stored (call-site contract test via stub) |
| Keep green | `python -m iris.ui._check_pdf_page_range`, `_check_ocr_fast_path`, `_check_chip_pdf_enrich` |

## 6. Alternatives rejected

| Idea | Why not |
|---|---|
| Cache by `attachment_id` / filename | Grounding forbids; id is session-local and names collide |
| In-process dict only | No retention across turns; OCR re-cost on restart |
| Cache vision transcripts | Non-deterministic / model-bound |
| SQLite shared DB | Overkill; JSON+index matches `model_blurb_ko` / holiday cache style |
| Put inside wiki.py only | Misses `attachment_context` → `read_pdf_pages` hot path |
