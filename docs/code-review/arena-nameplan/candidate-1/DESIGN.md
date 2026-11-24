# Candidate 1 — Single NamePlan SSOT (Cursor-like invent-and-write)

Design package for Iris Light file naming. Usage first; types derived from usage.
Bodies are contracts (`raise NotImplementedError`), not shipping code.

---

## Problem

Nameless 「만들어줘」 today forks into two writers with two policies:

1. Mid-stream / post-stream vibe (`_feed_live_vibe_stream` → `_live_vibe_open_target` / `_write_fenced_once` / `_try_reveal_local_vibe_code`) calls `default_generated_rel_path` → always `iris_generated.<ext>` (prompt ignored).
2. End-of-turn Verify (`verify_file_create_turn` → `plan_local_file_writes` → `_maybe_local_file_create_write`) returns `kind="ask"` and the user sees 「파일 이름을 알려 주세요…」.

Hermes nudge still says “ask before writing” when unnamed. Product locked decisions delete that ask, prefer English paths from goal/code intent, ban inventing the literal `iris_generated.py`, and force vibe onto the same plan as Verify. Delivery order is locked: **C → A → B**.

Constraints from grounding: keep `LocalWritePlan` / `VerifyResult` interop; keep `iris_generated` filter in `named_rel_paths`; do not revive fence→file completion fallback; count-mismatch (N names ≠ N fences) may still ask.

---

## Usage (caller's view)

### README

One module owns “what relative path do we write for this create?”. Callers never invent stems and never call a deleted `default_generated_rel_path`.

```text
goal + (optional assistant) + fence lang
        │
        ▼
   resolve_create_rel_path   ← only public naming API
        │
        ├─ explicit name in goal / assistant  → that RelPath
        └─ else                               → English stem from goal and/or code + lang suffix
        │
        ▼
   plan_local_file_writes / live vibe open / write_file tool
        → same path string for the same goal+lang(+assistant names)
```

- Nameless create → **write immediately** with an English `RelPath`. No ask for missing name.
- Spoken Korean goal → English filename (`구구단 만들어줘` → `gugudan.py`, `이미지 명암 변환` → `image_contrast.py`-style stem).
- Forbidden stem `iris_generated` is rejected at `RelPath` construction; callers cannot pass it through.
- Hermes: invent an English `rel_path` and call `project.write_file`; do not ask solely because the user omitted a name.

### Call site 1 — mid-stream vibe open (phase C)

```python
# iris/ui/window/main_window.py  (_live_vibe_open_target)
from iris.ui.chat.name_plan import resolve_create_rel_path

def _live_vibe_open_target(self, state: dict, lang: str) -> bool:
    goal = self._pending_local_vibe_prompt or ""
    # assistant still partial — resolver must work from goal+lang alone
    rel = resolve_create_rel_path(goal, lang=lang, assistant="")
    if rel is None:
        return False  # not a file-create goal; do not open a tab
    # ... resolve_under_root(root, rel.value); open empty file; state["rel"] = norm_rel
    raise NotImplementedError
```

### Call site 2 — end-of-turn Verify / local write (phase B; contract visible in C)

```python
# iris/ui/chat/file_write_claim.py
from iris.ui.chat.name_plan import resolve_create_rel_path

def plan_local_file_writes(goal: str, assistant: str) -> LocalWritePlan:
    """skip | ask | write. ask only for name/fence count mismatch — never for missing name."""
    if not file_create_goal(goal).matched:
        return LocalWritePlan("skip")
    fences = extract_all_code_blocks(assistant)
    if not fences:
        return LocalWritePlan("skip")
    names = named_rel_paths(goal)
    if not names:
        # was: ask 「파일 이름을 알려 주세요…」
        # now: one inferred path when single fence; multi-fence without names stays ask
        if len(fences) == 1:
            rel = resolve_create_rel_path(
                goal,
                lang=str(fences[0].get("lang") or ""),
                assistant=assistant,
                code=str(fences[0].get("code") or ""),
            )
            if rel is None:
                return LocalWritePlan("skip")
            return LocalWritePlan("write", pairs=((rel.value, str(fences[0]["code"])),))
        return LocalWritePlan(
            "ask",
            ask_message="파일 이름과 코드 블록 개수가 맞지 않습니다. 이름과 코드를 맞춰 주세요.",
        )
    if len(names) != len(fences):
        return LocalWritePlan(
            "ask",
            ask_message="파일 이름과 코드 블록 개수가 맞지 않습니다. 이름과 코드를 맞춰 주세요.",
        )
    pairs = tuple((name, str(block["code"])) for name, block in zip(names, fences))
    return LocalWritePlan("write", pairs=pairs)
```

### Call site 3 — Hermes nudge (phase A)

```text
# hermes_memory_nudge §12 (and iris-vibe-code SKILL) — prose change only
After creating/writing code: project.write_file with open=true.
rel_path = user-named path when present; otherwise invent a short English
filename that fits the code / goal intent, then write immediately.
Do not ask solely because the user omitted a name.
Do not invent iris_generated.py.
Never claim 생성·작성·처리 완료 without tool ok and a disk path.
```

---

## Shape

### Module map

```text
iris/ui/chat/name_plan.py          NEW — RelPath + resolve_create_rel_path + infer stem (SSOT)
iris/ui/chat/file_write_claim.py   plan_local_file_writes / named_rel_paths call name_plan
iris/runtime/turn_verify.py        unchanged public API; ask only when plan.kind=="ask" (mismatch)
iris/system/project_ops.py         DELETE default_generated_rel_path (+ self-check asserts)
iris/ui/window/main_window.py      vibe trio + _write_fenced_once → resolve_create_rel_path
iris/system/hermes_memory_nudge.py §12 invent-and-write (bump _NUDGE_VERSION)
integrations/.../iris-vibe-code/SKILL.md  same sentence as nudge
tests / _check_*                   ask-for-nameless gone; vibe path == plan path
```

Call chain length stays ≤ 3 files: `MainWindow` → `name_plan` → `project.write_file` / disk; Verify → `file_write_claim` → `name_plan`.

### Types / signatures

```python
# iris/ui/chat/name_plan.py
from __future__ import annotations

from dataclasses import dataclass

_FORBIDDEN_STEMS = frozenset({"iris_generated"})


@dataclass(frozen=True)
class RelPath:
    """Project-relative POSIX path. Invariant: stem not in _FORBIDDEN_STEMS."""

    value: str

    @classmethod
    def parse(cls, raw: str) -> RelPath | None:
        """Normalize slashes; reject empty, iris_generated.*, absolute, `..` segments."""
        raise NotImplementedError


def resolve_create_rel_path(
    goal: str,
    *,
    lang: str,
    assistant: str = "",
    code: str = "",
) -> RelPath | None:
    """Single naming entry for vibe, Verify plan, and (by policy) Hermes.

    Priority (first hit wins):
      1. named_rel_paths(goal)[0] if any (multi-name handled by plan_local_file_writes)
      2. if assistant: named_rel_paths(assistant) when exactly one usable name
      3. infer_english_stem(goal, code=code) + lang suffix
      4. None if not a create-shaped goal (caller skips)

    Idempotent for fixed (goal, lang, assistant names, code identifiers).
    Never returns a RelPath whose stem is iris_generated.
    """
    raise NotImplementedError


def infer_english_stem(goal: str, *, code: str = "") -> str:
    """English snake_case stem from goal intent and/or code identifiers.

    Rules (encode in code, not comments):
      - Prefer Latin tokens already in goal (file-like or words).
      - Else map common Korean intent phrases → fixed English stems
        (e.g. 구구단→gugudan, 테트리스→tetris); romanize remaining hangul
        into ascii snake when no map hit (deterministic; no LLM call).
      - Else first def/class/name in `code` if present.
      - Else fallback stem `script` (still not iris_generated).
      - Output: [a-z][a-z0-9_]* , length capped (~40).
    """
    raise NotImplementedError


def lang_suffix(lang: str) -> str:
    """Same mapping as former project_ops._lang_suffix; owned here after delete."""
    raise NotImplementedError
```

```python
# iris/ui/chat/file_write_claim.py — LocalWritePlan stays; ask narrowed

@dataclass(frozen=True)
class LocalWritePlan:
    """skip | ask | write.

    ask = structural mismatch only (names vs fences).
    Missing name → write via resolve_create_rel_path (never ask_message about naming).
    write pairs never contain iris_generated.*.
    """

    kind: str
    pairs: tuple[tuple[str, str], ...] = ()
    ask_message: str = ""


def plan_local_file_writes(goal: str, assistant: str) -> LocalWritePlan:
    raise NotImplementedError  # body per Usage call site 2
```

```python
# iris/system/project_ops.py — deletion contract

# DELETE:
#   def default_generated_rel_path(prompt: str, lang: str) -> str: ...
# Migrate lang suffix helper into name_plan.lang_suffix (or keep private _lang_suffix
# only if another non-naming caller needs it — prefer one owner).
```

```python
# MainWindow — three former default_generated call sites

def _write_fenced_once(self, code: str, lang: str) -> dict | None:
    rel = resolve_create_rel_path(self._pending_local_vibe_prompt or "", lang=lang)
    if rel is None:
        return None
    # project.write_file(..., rel_path=rel.value, ...)
    raise NotImplementedError


def _live_vibe_open_target(self, state: dict, lang: str) -> bool:
    raise NotImplementedError  # Usage call site 1


def _try_reveal_local_vibe_code(self, assistant_text: str) -> None:
    # fallback write uses resolve_create_rel_path(prompt, lang=block.lang, assistant=assistant_text, code=...)
    # MUST equal plan_local_file_writes(prompt, assistant_text).pairs[0][0] when that plan is write.
    raise NotImplementedError
```

### Invariants encoded in types / one owner

| Invariant | Where |
|---|---|
| No `iris_generated` path | `RelPath.parse` / `resolve_create_rel_path` |
| One naming policy | only `name_plan.resolve_create_rel_path` |
| Ask ≠ missing name | `LocalWritePlan.ask` only for count mismatch |
| Vibe path == Verify path | both call same function with same goal/lang/(assistant) |
| English preference | `infer_english_stem` (no hangul in output stem) |

### Interface depth

Public surface is one function (`resolve_create_rel_path`) plus existing `plan_local_file_writes`. Complexity (romanize, phrase map, code-identifier scrape, forbidden stems, lang suffix) stays inside `name_plan`. Callers do not choose among “default generated / ask / assistant name / invent”.

Deliberately not done: LLM-based naming, mid-stream rename when assistant later utters a different name, resurrecting fence→file completion gate fallback.

### Shared state

Naming is a pure function of (goal, lang, assistant, code). No shared mutable name cache. Mid-stream opens empty file at resolved path; end-turn write to the same path is idempotent overwrite of content.

### Phase delivery (locked order)

| Phase | Work | Done when |
|---|---|---|
| **C** | Add `name_plan`; migrate vibe trio + `_write_fenced_once`; delete `default_generated_rel_path` and its asserts; wire plan helper so nameless single-fence already resolves (even if B still cleans tests/ask copy) | `rg default_generated_rel_path` empty; live open uses `resolve_create_rel_path` |
| **A** | Nudge + vibe-code SKILL: invent English path and `write_file`; bump nudge version | MEMORY marker vN+1; no “ask before writing” for unnamed |
| **B** | `plan_local_file_writes` remove nameless-ask; update `_check_file_write_claim` (nameless → write); Verify still honors mismatch ask | 「파일 이름을 알려 주세요」 string gone from create path |

C ships the SSOT and vibe migration first so mid-stream never lands on `iris_generated` again. B removes the user-visible ask branch and locks tests. A aligns the agent tool policy with local plan.

---

## Synthesis decision

*(Arena fills this. Candidate 1 base claim: single `name_plan.resolve_create_rel_path` SSOT; vibe and Verify share it; ask narrowed to mismatch only.)*

---

## Tradeoffs accepted

- We accept a small fixed Korean→English phrase table (+ deterministic romanize fallback) in exchange for no LLM naming round-trip on the hot vibe path.
- We accept mid-stream path frozen from goal+lang (assistant may later mention another name) in exchange for no mid-stream rename races; Hermes/tool rename remains the explicit rename path.
- We accept fallback stem `script` when goal and code yield nothing in exchange for never asking and never using `iris_generated`.
- We accept keeping `LocalWritePlan.kind == "ask"` for N≠M mismatch in exchange for not silently writing the wrong pairing.
- We accept C briefly overlapping B on nameless-write behavior (resolver live in C) in exchange for locked phase order without reintroducing `iris_generated` between C and B.

---

## Alternatives considered

1. **Keep `default_generated_rel_path` but teach it to slug the goal** — Rejected: two entry points (vibe vs plan) remain; agents will keep calling the project_ops helper from new sites (`two ways to do one task` / `split ownership`). Interface stays shallow: callers still pick which helper.
2. **Delete vibe auto-write; only Hermes `write_file` names files** — Rejected: product requires vibe stream to use the same plan, not disappear; Companion live-typing UX depends on early open. Exposes naming to the model-only path and leaves local Verify without a mid-stream twin.
3. **Ask UI removed but plan still `skip` when nameless** — Rejected: locked product says write immediately with a fitting English name; skip would recreate “말로만 완료” pressure on the completion gate.

---

## Open questions and risks

- Should multi-fence nameless create invent `script.py`, `script_2.py`, … or keep asking? (Design keeps ask.)
- How large is the Korean phrase→stem table before romanize-only is enough?
- If Hermes invents `foo.py` and local vibe already opened `bar.py` from the same goal, who wins that turn — tool_written suppress, or dual files?
- Is romanize-only acceptable for rare hangul goals when the phrase map misses (filename opaque but English-alphabet)?

---

## Next implementation step

Add `iris/ui/chat/name_plan.py` with `RelPath` + `resolve_create_rel_path` (+ `infer_english_stem` stub returning deterministic English), point `_live_vibe_open_target` at it, and delete `default_generated_rel_path` (phase C start).
