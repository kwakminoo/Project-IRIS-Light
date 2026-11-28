# FFC-05 Extraction Cache — Candidate B

**Shape:** store-bound extract memo (process-local LRU + disk spill), not a free-floating disk-blob cache.

## 1. Data shapes & organizing structure

```
ExtractionFingerprint
  content: { size: int, mtime_ns: int }          # from Path.stat / store index
  window:  { page_from, page_to, page_limit }    # None → sentinel
  method:  { kind: "pdf"|"image", ocr_language, dpi: 130,
             vision_all: bool, char_limit: int|None }
  engine:  { tess_ver: str, pymupdf: bool }      # once per process

ExtractionCacheKey
  namespace: str          # session_token (= AttachmentStore id / chat session)
  attachment_id: str     # "" if bare path (still revalidated by caller)
  fingerprint: ExtractionFingerprint
  key_hash: str          # sha256 of canonical JSON; never basename alone

ExtractionCacheEntry
  key_hash, produced_at, hits
  result: dict             # same fields extract_from_source returns (no abs path)
  spill_path: Path|None    # large text/page_status off-heap
  bytes_on_disk: int
```

Organizing: one `ExtractionMemo` per live `AttachmentStore` (session). Process holds weak map `id(store) → memo`. Spill dir: `%TEMP%/iris-extract-cache/<namespace>/`.

## 2. Module boundary & public API

| Module | Owns |
|---|---|
| `iris/knowledge/extraction_cache.py` | key build, LRU, spill I/O, get/put |
| `iris/runtime/attachment_store.py` | namespace token, invalidate on detach/clear/reindex drift |
| `iris/knowledge/content_extract.py` | single wrap site (does not own retention) |

```python
# extraction_cache.py
def get(memo, key) -> dict | None
def put(memo, key, result: dict) -> None
def invalidate(memo, *, attachment_id: str | None = None, all: bool = False) -> int
def memo_for_store(store) -> ExtractionMemo
def fingerprint_for(path, *, page_from, page_to, page_limit, ocr_language,
                    vision_all, char_limit, engine_probe) -> ExtractionFingerprint
```

Hit requires: key match **and** live access revalidation (caller already passed `_checked_content_source` / `resolve_file`). Memo never bypasses that.

## 3. Wire points

```
content.extract / attachment_context PDF enrich / page_vision local doc
  → access check + canonicalize (unchanged)
  → extract_from_source(...)
       ├─ URL / office / text: no cache
       ├─ pdf | image:
       │    key = fingerprint(path.stat + window + method + engine)
       │    hit → return copy (strip any abs path; keep basename-only source when attachment_id)
       │    miss → existing read_pdf_pages / OCR → put → return
       └─ errors (PDF_*, OCR_*, EXTRACTION_CANCELLED): do not put
```

`read_pdf_pages` stays a pure leaf (no cache) so existing page-range/OCR self-checks unchanged. Secondary callers that call `read_pdf_pages` directly skip memo (acceptable: wiki/`extract_from_source` is the hot path).

Invalidate hooks:
- `AttachmentStore.clear` / root remove → `invalidate(all)` / by `attachment_id`
- `_index_root` when `size`/`modified_time` changes vs prior meta → invalidate that id
- `resolve_file` access failure → invalidate that id

## 4. Namespace, fingerprint, invalidation, size/TTL

| Rule | Value |
|---|---|
| Namespace | chat/`AttachmentStore` session token; never shared across sessions |
| Fingerprint | size+mtime_ns + page window + ocr_language + dpi + vision_all + char_limit + tess version + pymupdf present — **not** filename |
| Invalidation | detach/clear; mtime/size drift; access revoked; process exit (spill wiped) |
| LRU | max **32** entries / memo; max **64 MiB** spill / namespace |
| TTL | **2 h** wall clock; expired on get → drop |
| Spill | entry text+page_status > **256 KiB** → JSON.gz under TEMP; unlink on invalidate/TTL/LRU |
| Temp cleanup | memo `__del__` / `invalidate(all)` / atexit sweep of namespace dir |
| Provider payload | cached `source` rewritten to basename / relative_path; no absolute paths |

## 5. Self-check plan

`iris/knowledge/_check_extraction_cache.py` (run: `python -m iris.knowledge._check_extraction_cache`)

1. Same PDF twice via `extract_from_source` with memo → 2nd call skips OCR (patch `_ocr_for_document` counter == 1).
2. Touch mtime → miss (counter increments).
3. Different `page_from`/`ocr_language` → miss (separate keys).
4. `invalidate(attachment_id=…)` → next get None.
5. Key JSON contains no basename-only identity; two files same name different size → different `key_hash`.
6. Existing: `python -m iris.ui._check_pdf_page_range`, `_check_ocr_fast_path`, `_check_chip_pdf_enrich` still green.

## 6. Alternatives rejected

| Rejected | Why |
|---|---|
| Pure disk-blob under `~/.iris-light/extract-cache` | Orphans across sessions; access revalidation awkward; contradicts store-as-SoT |
| Cache inside `read_pdf_pages` | Couples leaf to session; breaks path-only unit checks |
| Content-hash whole file every hit | Expensive on large PDFs; size+mtime from store index enough with invalidate-on-drift |
| Cache error results | Would sticky `OCR_*` across transient tess install |
| Filename / attachment display-name keys | Grounding forbid; FRC-05 already fixed basename ambiguity elsewhere |
