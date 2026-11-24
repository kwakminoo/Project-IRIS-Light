# Candidate 2 — Destination-first name plan

Iris Light Cursor-like file naming. One authority decides *where* a create-turn writes; vibe stream and VerifyTurn both read that authority. No ask-for-name branch. No `iris_generated.py`.

---

## Problem

Nameless 「만들어줘」 today splits into three writers with three naming policies:

1. Live vibe (`_live_vibe_open_target` / `_write_fenced_once` / `_try_reveal_local_vibe_code`) → `default_generated_rel_path` → always `iris_generated.<ext>`.
2. VerifyTurn / `plan_local_file_writes` → named paths or **ask** (「파일 이름을 알려 주세요…」).
3. Hermes MEMORY nudge rule 12 → ask before inventing a path; still bans `iris_generated.py`.

The prior report (`docs/code-review/completed/파일이름-동일답변-원인.md`) shows the product failure: user intent never reaches a path, the fixed name wins, and the completion gate collapses distinct model answers into the same reveal line.

Locked product decisions force one plan, English invented names, immediate write, delete of `default_generated_rel_path`, and deletion of the ask-when-unclear rule. Shape is non-obvious because vibe needs a destination *before* the fence body is complete, while VerifyTurn pairs full fences with content — same destination rule, different moment.

## Usage (caller's view)

Callers never invent a relative path and never choose between "vibe name" and "verify name". They ask one module for destinations (or a full write batch), then write.

### README-style

```text
Turn wants a code file?
  → destinations_for_create_turn(goal, assistant_so_far="", lang_hint="")
  → RelPath[]  (empty = not a create turn / cannot pair safely)
  → open/stream/write those paths only

Turn finished with fences?
  → write_batch_for_create_turn(goal, assistant)
  → WriteBatch  (empty = skip; never ask)
  → for each slot: project.write_file(rel, content)

Hermes (tool path):
  MEMORY says: invent an English rel_path from the goal/code and call write_file.
  Do not ask for a name. Do not use iris_generated.py.
```

### Call site 1 — live vibe open (stream start)

```python
# iris/ui/window/main_window.py  (_live_vibe_open_target)

from iris.ui.chat.name_plan import destinations_for_create_turn

def _live_vibe_open_target(self, state: dict, lang: str) -> bool:
    goal = self._pending_local_vibe_prompt or ""
    dests = destinations_for_create_turn(
        goal,
        assistant_so_far=state.get("raw") or "",
        lang_hint=lang,
    )
    if not dests:
        return False
    rel = dests[0].as_posix()  # first fence destination; stream writes here
    # ... resolve_under_root, mkdir, open_file_in_workspace ...
    state["rel"] = rel
    raise NotImplementedError("wire open only; naming comes from name_plan")
```

### Call site 2 — VerifyTurn local write (turn end)

```python
# iris/runtime/turn_verify.py  + main_window._maybe_local_file_create_write

from iris.ui.chat.name_plan import write_batch_for_create_turn

def verify_file_create_turn(evidence: TurnEvidence, ...) -> VerifyResult:
    batch = write_batch_for_create_turn(evidence.goal, evidence.assistant)
    # no LocalWritePlan.kind == "ask"
    if not evidence_already_wrote and batch.slots:
        # action local_write; execute batch.slots
        ...
    raise NotImplementedError("ask action for missing names is gone")
```

### Call site 3 — post-stream reveal fallback

```python
# _try_reveal_local_vibe_code / _write_fenced_once

batch = write_batch_for_create_turn(prompt, assistant_text)
# or destinations_for_create_turn when only lang is known mid-fence
# default_generated_rel_path is deleted; callers must not import it
```

Usage invariant: if vibe opened `rel=X`, VerifyTurn's batch for the same goal+assistant must use `X` for the matching fence (same function, same inputs shape).

---

## Shape

### Core idea — destinations before content

Do not grow `LocalWritePlan` with another `kind`. Replace the kind-tagged plan with two related values owned by one module:

| Type | Meaning |
|---|---|
| `RelPath` | Validated project-relative path; construction rejects `iris_generated.*` and non-ASCII stems |
| `WriteSlot` | One destined fence: path + full code |
| `WriteBatch` | Zero or more slots; empty means skip (never ask) |

Naming policy lives in **one** pure function chain. Streaming and verify are shells that call it at different times.

```text
goal (+ optional assistant / lang)
        │
        ▼
┌───────────────────────────┐
│  name_plan (deep module)  │  invent English path, ban iris_generated,
│  destinations / batch     │  pair fences, no ask
└─────────────┬─────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
 vibe stream      VerifyTurn / local write
 (dest early)     (batch at end)
```

Interface depth: public surface is two functions (`destinations_for_create_turn`, `write_batch_for_create_turn`) plus frozen types. Complexity hidden: English stem invention, suffix from lang, ban list, multi-fence pairing rules, assistant-name fallback. Callers do not see invent heuristics or former ask strings.

### Types and signatures

```python
# iris/ui/chat/name_plan.py
"""Single destination authority for create-turn file writes.

Invariants:
- RelPath never equals iris_generated.<ext> (any case).
- Stem is ASCII (English preferred); Korean user goal may still yield English path.
- Empty WriteBatch means skip — there is no ask variant.
- destinations_for_create_turn and write_batch_for_create_turn share resolve_destinations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

# Opaque validated relative path ("tetris_king.py", "vision/gamma_lab.py").
# Construction is the validation boundary (per boundary-discipline).
RelPath = NewType("RelPath", str)


@dataclass(frozen=True)
class FenceBody:
    lang: str
    code: str  # may be "" when only the opening fence is known


@dataclass(frozen=True)
class WriteSlot:
    rel: RelPath
    code: str


@dataclass(frozen=True)
class WriteBatch:
    """Ready-to-write or empty. Never carries an ask_message."""

    slots: tuple[WriteSlot, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.slots


class BannedGeneratedName(ValueError):
    """Raised if something tries to build RelPath('iris_generated.py')."""


def make_rel_path(raw: str) -> RelPath:
    """Parse/normalize; reject empty, iris_generated.*, and non-ASCII stems.

    // TODO: strip ./, unify slashes, casefold-ban iris_generated + suffix
    """
    raise NotImplementedError


def invent_english_rel(goal: str, fence: FenceBody) -> RelPath:
    """Cursor-like: name fits the code and/or goal intent, in English.

    Priority sketch (single source — do not reimplement at call sites):
    1. Explicit English/ASCII filename in goal (named_rel_paths).
    2. Else single explicit name in assistant prose (when caller passes it).
    3. Else invent snake_case English stem from goal keywords + code hints
       (def/class names, dominant noun), then lang suffix.
    4. Never return iris_generated.*.
    5. If invention still empty, use a generic English stem from lang only
       (e.g. script.py / app.js) — still not iris_generated.

    // TODO: keep deterministic for same (goal, lang, code head)
    """
    raise NotImplementedError


def resolve_destinations(
    goal: str,
    fences: list[FenceBody],
    *,
    assistant_names: list[str] | None = None,
) -> tuple[RelPath, ...]:
    """Map N fences → N RelPaths, or () if create-goal missing / unsafe pair.

    Rules (encoded here, not in UI):
    - Not a file-create goal → ().
    - 0 fences → ().
    - goal names length == fences → zip.
    - 0 goal names, 1 fence, 1 assistant name → that name.
    - 0 goal names, 1 fence → invent_english_rel(goal, fence).
    - name/fence count mismatch (and not the single-assistant case) → ()
      (skip; do not ask; do not invent mismatched pairs).

    // TODO: reuse named_rel_paths from file_write_claim or move both here
    """
    raise NotImplementedError


def destinations_for_create_turn(
    goal: str,
    *,
    assistant_so_far: str = "",
    lang_hint: str = "",
) -> tuple[RelPath, ...]:
    """Early destinations for vibe. Partial assistant text OK.

    Builds FenceBody list from opened fences in assistant_so_far; if a fence
    opened with lang but empty body, still invent/resolve a path so the IDE
    tab can open. lang_hint seeds a synthetic fence when the opener is known
    only from the stream state.

    Must agree with write_batch_for_create_turn once the same fences complete.
    """
    raise NotImplementedError


def write_batch_for_create_turn(goal: str, assistant: str) -> WriteBatch:
    """End-of-turn pairs. Replaces plan_local_file_writes (no ask kind)."""
    raise NotImplementedError
```

### VerifyTurn / claim surface (thin adapters)

```python
# iris/runtime/turn_verify.py — sketch delta

VerifyAction = Literal["display", "local_write", "failover", "stop"]
# "ask" removed from name-missing path. (Other ask UX, if any, stays elsewhere.)

@dataclass(frozen=True)
class VerifyResult:
    display: str
    actions: tuple[VerifyAction, ...]
    suppress_voice_followup: bool
    local_batch: WriteBatch | None = None  # was local_plan: LocalWritePlan
    suppress_followthrough: bool = False


def verify_file_create_turn(evidence: TurnEvidence, ...) -> VerifyResult:
    # wrote? → no local batch
    # else batch = write_batch_for_create_turn(...); slots → local_write
    # needs_recovery no longer treats "ask" as recovery satisfaction
    raise NotImplementedError
```

```python
# iris/ui/chat/file_write_claim.py — keep gates; retire plan kinds

# DELETE: LocalWritePlan, plan_local_file_writes ask branch
# KEEP: named_rel_paths (or re-export from name_plan), settle_completion_claim,
#       turn_write_evidence, file_create_goal, image pipe

# Compatibility shim during migration (delete after callers move):
def plan_local_file_writes(goal: str, assistant: str) -> WriteBatch:
    """Deprecated alias → write_batch_for_create_turn."""
    raise NotImplementedError
```

### Hermes nudge (phase A text contract)

```text
# iris/system/hermes_memory_nudge.py rule 12 (replace ask wording)

After creating/writing code: project.write_file with open=true.
rel_path = filename the user asked for when present.
If they did not name a file, invent a short English rel_path that fits the
code/goal and write immediately. Do not ask for a filename.
Do not invent iris_generated.py.
```

Bump `_NUDGE_VERSION` so stale MEMORY markers refresh.

### Delete after migration

```python
# iris/system/project_ops.py
# DELETE default_generated_rel_path and its self-check assert that expects iris_generated.py
```

### Module map

```text
iris/ui/chat/name_plan.py          NEW — RelPath, invent, destinations, WriteBatch
iris/ui/chat/file_write_claim.py   KEEP gates; remove LocalWritePlan ask; thin re-export
iris/runtime/turn_verify.py        Consume WriteBatch; drop name-ask action
iris/ui/window/main_window.py      Vibe + reveal + local write → name_plan only
iris/system/hermes_memory_nudge.py Rule 12 invent+write (English)
iris/system/project_ops.py         Delete default_generated_rel_path
iris/ui/_check_file_write_claim.py Expect invent+write; forbid ask / iris_generated
iris/ui/_check_* vibe checks       Assert same dest as write_batch for same goal
```

Call chain length (create turn): `MainWindow` → `name_plan` → `project.write_file`. Verify: `MainWindow` → `turn_verify` → `name_plan`. Max three files on the happy path (per minimize-reader-load).

### Implementation phases (locked order)

| Phase | Work | Done when |
|---|---|---|
| **C** | Point vibe (`_live_vibe_open_target`, `_write_fenced_once`, `_try_reveal_local_vibe_code`) at `destinations_for_create_turn` / `write_batch_for_create_turn`. Delete `default_generated_rel_path` and all imports. | No caller references `default_generated_rel_path`; vibe path == verify path for same goal |
| **A** | Hermes nudge: invent English `rel_path` and `write_file`; remove ask-before-write. Bump nudge version. | MEMORY block text matches contract; version marker advanced |
| **B** | Local plan: invent+write for nameless create; remove `LocalWritePlan` ask / VerifyAction ask for missing names; update checks. | 「스크립트 만들어줘」+ one fence writes an English file without ask string |

Phase C first so the dual-writer bug dies before invent quality is tuned. A and B both invent English names; A is model-side, B is local fallback when tools did not write.

### What the system deliberately does not do

- Does not ask the user for a filename on nameless create.
- Does not keep a second default path helper in `project_ops`.
- Does not invent the literal `iris_generated.py`.
- Does not invent N unrelated names when name/fence counts disagree — skip instead of ask or mis-pair.
- Does not put Hermes wire/MCP types on the public name_plan API.

---

## Synthesis decision

*(Arena fills this. Candidate-2 base claim: destination-first `name_plan` with `WriteBatch` and no ask variant; vibe and VerifyTurn share `resolve_destinations`.)*

## Tradeoffs accepted

- We accept skip-on-count-mismatch (no write, no ask) in exchange for never pairing the wrong name to the wrong fence.
- We accept heuristic English invention (occasionally bland `script.py`) in exchange for deleting the ask UX and the `iris_generated` trap.
- We accept a short migration shim `plan_local_file_writes → WriteBatch` in exchange for not big-banging every import in one commit.
- We accept inventing a destination before the fence body is complete (vibe) in exchange for live typing into the *final* path, provided end-of-turn batch uses the same resolver inputs.
- We accept ASCII-only stems (reject Hangul filenames) in exchange for the locked English-filename preference.

## Alternatives considered

1. **Thin evolve `LocalWritePlan`** (`kind: skip|write`, invent inside `plan_local_file_writes`, vibe calls the same function). Hides less: callers still think in "plan kinds", ask-shaped fields linger, and early vibe (lang-only) stays an awkward overload of a pairs-based type. Lost on interface depth — same surface area, weaker destination concept.
2. **Keep `default_generated_rel_path` but make it invent English.** Leaves two writers; an agent that opens only `main_window` vibe code will keep a parallel invent path that drifts from VerifyTurn (split ownership / two ways to do one task). Rejected by the unify lock.
3. **Hermes-only naming (no local invent).** Deep for the agent path, shallow for tool-less turns: vibe would still need a local destination. Product requires local write-immediately for nameless create when tools did not run.

## Open questions and risks

- Should invent prefer code symbols (`class GammaLab` → `gamma_lab.py`) over goal nouns when both exist?
- For multi-fence nameless creates, invent per fence (`script_1.py`…) or always skip until the user names them?
- Does `make_rel_path` allow subfolders (`vision/gamma.py`) from goal text, or only basename?
- When vibe already opened dest A and a later tool `write_file` uses dest B, do we leave A as an empty stub or delete it?
- Is Hangul in the *path* ever allowed if the user typed `이미지테스트2.py` explicitly (ASCII digits + Hangul), or do we transliterate even explicit names?

## Next implementation step

Add `iris/ui/chat/name_plan.py` with `make_rel_path` / `resolve_destinations` / `destinations_for_create_turn` / `write_batch_for_create_turn` (`NotImplementedError` bodies first only if scaffolding; prefer implementing resolve next), then migrate `_live_vibe_open_target` off `default_generated_rel_path` (phase C).
