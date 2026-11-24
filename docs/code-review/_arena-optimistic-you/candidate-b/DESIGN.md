# Candidate B — Optimistic You via `UserTurn.user_bubble_shown`

| 항목 | 내용 |
|---|---|
| 후보 | B |
| 작성일 | 2026-11-03 |
| 관련 | `docs/code-review/_arena-optimistic-you/grounding/phase-a.md` |
| 형태 제약 | **별도 registry 모듈 금지.** 플래그는 `UserTurn` 필드, 표시는 `MainWindow._present_user_turn_early` 한 곳 |
| 구현 | 하지 않음 (서명·스케치만) |

## Synthesis decision

_(비움 — 아레나 합성 단계에서 채움)_

---

## 1. Problem

보내기 직후 입력창만 비고 You 버블은 `AttachmentWorker`·로컬 의도 게이트·`_continue_user_turn_bound` 이후에야 붙는다. 첨부가 있거나 게이트가 길면 “전송이 안 된 것”처럼 보인다.

목표: **같은 턴에 대해 You를 한 번만**, 가능한 한 이르게 보여 주고, continue / 로컬 echo가 두 번째 append를 하지 않게 한다.

---

## 2. Usage (호출자 관점 — 먼저)

호출자는 “버블 레지스트리”를 모른다. **턴 객체**와 **한 메서드**만 안다.

```text
ChatPanel._emit_send
  → clear input → send_clicked
MainWindow._on_user_text
  → UserTurnDispatcher.submit → UserTurn 생성
     ├─ session free → turn_ready → _dispatch → _execute_user_turn_body
     │                    └─ 초입: _present_user_turn_early(turn)   ★ You 즉시
     │                    └─ … gates / AttachmentWorker …
     │                    └─ _continue_user_turn_bound
     │                         └─ if turn.user_bubble_shown: skip You append
     └─ session busy → turn_queued
                          └─ _on_turn_queued → _present_user_turn_early(turn)  ★ 권장
                          └─ (later promote) body 초입 present → no-op (이미 shown)
```

**호출 예 (의도 코드, 미구현):**

```python
# iris/ui/window/main_window.py — _execute_user_turn_body 초입
def _execute_user_turn_body(self, turn: UserTurn) -> None:
    text = (turn.text or "").strip()
    if not text and not turn.attachments:
        self._turn_dispatcher.finish_active_turn(turn.id)
        return
    # … followthrough / gate begin / mark working … 기존과 동일 …
    self._present_user_turn_early(turn)  # ← 첨부 준비·의도 게이트보다 앞
    # … try_wiki_command / AttachmentWorker / _continue_user_turn …
    raise NotImplementedError  # design sketch only


# 큐에 쌓일 때 (권장: 보내기 = 즉시 You)
def _on_turn_queued(self, turn: object, reason: str) -> None:
    # … 기존 live_activity 로그 …
    if isinstance(turn, UserTurn):
        self._present_user_turn_early(turn)
    raise NotImplementedError


# continue — 두 번째 You 금지
def _continue_user_turn_bound(self, turn, model, owns, prepared=None) -> None:
    shown = self._format_user_turn_content(turn)
    showing = self._showing_bound()
    # …
    if turn.source == UserTurnSource.VOICE:
        # voice: STT pending 완료 경로 유지 (early present가 voice를 스킵하므로 여기가 본표시)
        ...
    elif showing and not self._turn_is_followthrough and not turn.user_bubble_shown:
        self._chat.append_message_instant("You", shown)
        turn.mark_user_bubble_shown()  # 또는 present가 이미 켠 경우 이 분기는 안 탐
    raise NotImplementedError
```

**로컬 의도 echo** (`wiki_turn._echo_user`, `_show_extension_turn`, PDF/스킬 등 You를 직접 붙이는 곳)는 가능하면:

```python
# 선호: 공유 진입점
window._present_user_turn_early(turn)  # already shown → no-op, then record_history만

# 또는 최소: if not turn.user_bubble_shown: append…; mark…
```

idempotent 계약: **같은 `turn`에 `_present_user_turn_early`를 몇 번 불러도 UI append는 최대 1회.**

---

## 3. Types / signatures

### 3.1 `UserTurn` — 데이터에 래치

현재 `iris/runtime/user_turn.py`는 `@dataclass(frozen=True)`. UI 래치는 **턴 수명과 같이 움직여야** 하므로 필드가 맞다. frozen과의 충돌은 “신원 필드는 불변, 래치만 전이”로 푼다.

```python
# iris/runtime/user_turn.py — sketch (not implemented)

@dataclass(frozen=True)
class UserTurn:
    text: str
    source: UserTurnSource
    session_id: int | None = None
    attachments: tuple[str, ...] = ()
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.perf_counter)
    # UI latch: continue / local echo가 두 번 You를 붙이지 않게 한다.
    user_bubble_shown: bool = False

    def mark_user_bubble_shown(self) -> bool:
        """False→True 한 번만. 이미 True면 False(no-op)."""
        if self.user_bubble_shown:
            return False
        object.__setattr__(self, "user_bubble_shown", True)
        return True
        # not implemented in this document
```

대안(동일 후보 계열): `frozen` 제거 후 일반 대입. 더 단순하지만 `UserTurn`을 키/캐시로 쓰는 코드가 있으면 깨질 수 있음 → 기본안은 `__setattr__` 전이.

**금지(이 후보):** `dict[turn_id, bool]` 별도 registry 모듈, `MainWindow`의 전역 set.

### 3.2 `MainWindow._present_user_turn_early`

```python
# iris/ui/window/main_window.py — sketch

def _present_user_turn_early(self, turn: UserTurn) -> bool:
    """You 버블을 지금 붙인다. 이미 붙였거나 이 경로에서 붙이면 안 되면 False.

    Returns:
        True  — 이번에 append 했다
        False — no-op (이미 shown / followthrough / voice / 비표시 세션 / 빈 본문)
    """
    # not implemented
    if turn.user_bubble_shown:
        return False
    if self._turn_is_followthrough or self._sending_followthrough:
        return False
    if turn.source == UserTurnSource.VOICE:
        # STT pending 완료가 You를 담당. 여기서 붙이면 complete_stt_pending과 이중/경합.
        return False
    if not (turn.text or "").strip() and not turn.attachments:
        return False
    # 큐/비활성 대화: 현재 화면 세션과 turn.session_id가 다를 때 skip
    sid = int(turn.session_id) if turn.session_id is not None else int(self._conversation_id)
    if sid != int(self._conversation_id):
        return False
    # _showing_bound는 bound_slot 의존 — body 밖(queued)에서는 세션 id 비교로 충분
    display = self._format_user_turn_content(turn)
    panel = self._active_workspace_iris_panel()
    if panel is not None:
        panel.append_user(display)
    else:
        self._chat.append_message_instant("You", display)
    turn.mark_user_bubble_shown()
    return True
```

표시 문자열은 grounding과 같이 `_format_user_turn_content` / `format_user_attachment_block` — **AttachmentWorker 전에도 가능.**

### 3.3 Continue / 로컬 경로 계약

| 지점 | 동작 |
|---|---|
| `_present_user_turn_early` | append + `mark_user_bubble_shown` (idempotent) |
| `_continue_user_turn_bound` You 분기 | `if turn.user_bubble_shown: skip` (voice STT 분기는 기존 유지; early가 voice를 안 건드림) |
| `wiki_turn._echo_user` / `_show_extension_turn` 등 | early 이후면 skip append; history record는 기존대로 |
| `_commit_recorded_user_turn_bound` | You append 안 함 (현행 유지). 플래그와 무관 |

새 파일 없음. 터치 예상: `user_turn.py`, `main_window.py`, (선택) `wiki_turn.py` / 로컬 You echo 몇 곳의 skip 가드.

---

## 4. Shape (깊은 모듈)

```text
┌─────────────────────────────────────────┐
│ UserTurn                                 │
│  text, attachments, id, source, …        │
│  user_bubble_shown + mark_…()  ← 전이   │
└──────────────────▲──────────────────────┘
                   │ reads / marks
┌──────────────────┴──────────────────────┐
│ MainWindow._present_user_turn_early      │
│  정책: followthrough / voice / session   │
│  표면: workspace panel vs _chat          │
│  본문: _format_user_turn_content         │
└──────────────────▲──────────────────────┘
                   │ one call site family
     body 초입 · turn_queued · (로컬 echo 공유)
```

- **데이터 우선:** “이 턴의 You를 이미 그렸는가”는 턴의 상태. 창/디스패처에 부수 map을 두지 않음.
- **멱등 전이:** `mark_user_bubble_shown` False→True 한 번; present는 그 전에 읽고 그 후에 씀.
- **얕은 API 금지:** ChatPanel에 optimistic API를 추가하지 않음. `_emit_send`는 지금처럼 clear + signal만.
- **Dispatcher는 모름:** `UserTurnDispatcher`는 여전히 큐만. UI 래치는 UI가 턴 필드에 쓴다.

---

## 5. Rationale

### Problem → 이 형태

지연의 핵심은 `_execute_user_turn_body`가 AttachmentWorker에서 **return** 하고 You는 `_continue_user_turn_bound`에만 있는 구조다. body 초입에 present를 넣으면 게이트·워커와 무관하게 You가 뜬다. 플래그를 턴에 두면 continue가 “이미 그렸는지”를 turn_id 조회 없이 본다.

### Queued turns — submit 시 present 권장

| 선택 | 결과 |
|---|---|
| body만 | 세션 busy면 입력만 비고 You는 dequeue 때까지 없음 → 목표 미달 |
| **queued에서도 present** | 보내기 = 즉시 You. body/continue는 플래그로 no-op |

`turn_dropped`(overflow) 시 버블만 남는 비용이 있다. overflow는 드물고, Experience First는 “보낸 글이 로그에 남는 것”을 선호. drop 시 버블 제거는 이번 범위 밖(Open questions).

Voice queued는 early가 voice를 스킵하므로 현행 STT UX 유지.

### Followthrough

`_turn_is_followthrough` / `_sending_followthrough`면 early no-op, continue도 기존처럼 You skip. 플래그를 켜지 않음.

---

## 6. Tradeoffs

| 이득 | 비용 |
|---|---|
| 새 모듈·레지스트리 없음; diff 작음 | `UserTurn` frozen + 가변 래치 (`__setattr__`) 설명 필요 |
| 멱등이 턴에 붙어 큐→실행 자연스럽게 이어짐 | 로컬 You echo 전부가 플래그를 모르면 이중 append 가능 → 가드 몇 곳 |
| ChatPanel / Dispatcher 계약 무변경 | queued You는 아직 “커밋되지 않은” 턴(히스토리/모델 전). 실패 시 버블 orphan |
| 표면 선택(panel vs `_chat`)을 present 한곳에 모음 | `_active_workspace_iris_panel()` 현재 `None` 고정이어도 경로를 맞춰 둬야 함 |

히스토리(`_record_history`)는 early에서 **쓰지 않음**. 기록 시점 불변 → 낙관 UI와 영속 분리.

---

## 7. Alternatives considered (이 후보 안에서 기각)

| 대안 | 기각 이유 |
|---|---|
| 별도 `YouBubbleRegistry` / `turn_id → bool` | **후보 A 계열.** 이 후보는 턴 필드 제약 |
| ChatPanel에서 send 직후 You append | 턴 id·followthrough·voice·세션 바인딩을 패널이 모름 → 얕고 깨지기 쉬움 |
| Dispatcher.submit이 UI 콜백 | runtime이 UI에 결합; 깊은 모듈 위반 |
| continue만 앞으로 당김 (워커 후 유지) | 첨부 지연을 없애지 못함 |
| early에서 history까지 기록 | 게이트가 조기 return·실패할 때 유령 user row |

---

## 8. Open questions

1. 로컬 You echo (`_echo_user`, extension/PDF/skill)를 전부 `_present_user_turn_early`로 수렴할지, continue만 고치고 로컬은 `if not turn.user_bubble_shown` 한 줄만 넣을지.
2. `turn_dropped` 후 orphan You를 지울지(로그에서 마지막 You 제거는 위험) — 무시 vs 세션 리셋만.
3. frozen 유지+`__setattr__` vs `frozen=False` — 테스트/해시 사용처 점검 후 결정.
4. 타 세션 큐 턴: 지금 설계는 `session_id != _conversation_id`면 skip. 사용자가 그 세션으로 전환한 뒤 body에서 present — OK인지.
5. early 직후 `set_generating(True)`를 같이 켤지(첨부 경로만 켜는 현행과 시각 일관성).

---

## 9. Next implementation step

1. `UserTurn.user_bubble_shown` + `mark_user_bubble_shown()` 추가; 생성자/테스트가 새 필드 기본값으로 통과하는지 확인.
2. `MainWindow._present_user_turn_early` 구현 (voice/followthrough/세션 가드).
3. `_execute_user_turn_body`에서 followthrough 플래그 설정 **직후** present 호출; `_continue_user_turn_bound` You 분기에 `not turn.user_bubble_shown` 가드.
4. `_on_turn_queued`에서 keyboard 턴 present (권장).
5. `_echo_user` / `_show_extension_turn` 등 이중 위험 지점에 skip 또는 present 공유.
6. 재현: 첨부 있는 전송 → You가 워커 완료 **전**에 보이는지; continue 후 이중 You 없는지; followthrough·voice 회귀.

검증 스케치 (미구현):

```python
def test_present_user_turn_early_idempotent():
    # turn = UserTurn(...); present twice → one append; turn.user_bubble_shown is True
    raise NotImplementedError
```

---

## 10. Grounding cross-check

| Grounding 항목 | Candidate B |
|---|---|
| You before AttachmentWorker | body 초입 present |
| No double-append | `user_bubble_shown` + continue skip |
| Followthrough skip | present no-op |
| Voice / STT | present skips voice; continue 유지 |
| Queued | present on `turn_queued` (권장) |
| Workspace vs main chat | present 내부 panel/`_chat` |
| Qt UI thread | MainWindow 슬롯 경로만 |
| Smallest diff | 필드 1 + 메서드 1 + 가드 수곳; 새 파일 없음 |
