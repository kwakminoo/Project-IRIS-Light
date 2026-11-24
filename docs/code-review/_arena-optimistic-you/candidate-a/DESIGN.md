# Candidate A — Optimistic You via turn.id paint registry

| 항목 | 내용 |
|---|---|
| 후보 | A |
| 작성일 | 2026-11-03 |
| 형태 | 순수 coordinator / registry (`turn.id` 키) |
| 구현 | 없음 (서명·스케치만) |
| Synthesis | _(비움 — 병렬 탐색 후 결정)_ |

## Problem

보내기 직후 입력창만 비고, You 말풍선은 `AttachmentWorker`·의도 게이트·`_continue_user_turn_bound` 이후에야 뜬다.  
목표는 **보내기 직후(첨부 prep / gate 지연 전)** 채팅 로그에 You가 보이게 하는 것이다.  
같은 턴이 continue 경로에서 다시 append하면 안 되고, followthrough·음성 STT·큐잉 계약을 깨면 안 된다.

## Usage (caller's usage first)

현재 측정 경로:

```
ChatPanel._emit_send
  → clear input; send_clicked
MainWindow._on_user_text
  → UserTurnDispatcher.submit  → turn_ready (동기)
MainWindow._dispatch_user_turn
  → _execute_user_turn_body
       … local intent gates (일부는 자체 You 후 return) …
       if attachments: AttachmentWorker.start(); return   ← You 없음 (오늘)
       else: _continue_user_turn
_continue_user_turn_bound
  → append_message_instant('You', shown)   ← 첫 You (오늘)
_commit_recorded_user_turn_bound
  → history + ChatWorker
```

후보 A가 끼우는 호출 (의도):

```
_execute_user_turn_body
  … early-return 게이트(위키/스킬/확장 등 자체 You) 통과 후 …
  … model / cloud 동기 검사 통과 후 …
  surface = resolve_you_surface(window)          # ChatPanel 또는 workspace panel
  ensure_user_bubble(surface, turn)              # ← 신규: AttachmentWorker 직전
  if attachments: AttachmentWorker.start(); return
  _continue_user_turn(...)

_continue_user_turn_bound
  # 기존 append_message_instant('You', …) 전부
  ensure_user_bubble(surface, turn)              # ← 동일 API, 이미 칠했으면 False / no-op

음성 분기
  complete_stt_pending(text) 성공 시
    mark_user_bubble_painted(turn.id)            # append 없이 레지스트리만
  실패 시
    ensure_user_bubble(surface, turn)

_finish_current_turn / finish_active_turn
  forget_user_bubble(turn.id)                    # 집합 누수 방지
```

호출자 규칙:

1. **한 번 칠하기** — 누가 먼저 칠하든 `ensure_user_bubble`만 쓴다. continue는 플래그를 읽지 않는다.
2. **AttachmentWorker는 paint 뒤** — `worker.start()` 앞에 ensure. worker 콜백은 ensure만 (idempotent).
3. **Followthrough** — `skip=True` 또는 surface 정책으로 ensure가 즉시 False (기존 `_turn_is_followthrough` 스킵 유지).
4. **자체 You early-return 경로** — 위키/확장 등 오늘 이미 You를 그리는 분기는 이번 후보에서 강제 리팩터하지 않는다. ensure 삽입점은 그 return들 **이후**다.
5. **큐잉** — `submit`/`turn_queued`에서는 그리지 않는다. `turn_ready` → body가 실제로 돌 때 ensure (프로모션 직후·첨부 전).

## Shape

### 한 줄

`turn.id → 이미 You를 그렸는가`만 아는 **작은 순수 레지스트리** + surface에 위임하는 `ensure_user_bubble`.  
턴 객체에 플래그를 심지 않는다 (`UserTurn`은 frozen 유지).

### 부품

| 부품 | 역할 |
|---|---|
| `YouBubbleSurface` | You를 어디에 그릴지 (메인 `_chat` / workspace `append_user`) |
| `UserBubblePaintRegistry` | `turn.id` → painted; ensure / mark / forget |
| MainWindow 호출 지점 | body(첨부 전) + continue(기존 append 교체) + finish(forget) |

Deep module: 호출자는 “이미 그렸나?”를 묻지 않고 `ensure`만 부른다. 레지스트리가 멱등성을 소유한다.

### Types / signatures (sketch only)

```python
# iris/ui/chat/you_bubble.py  (proposed; not implemented)

from __future__ import annotations

from typing import Protocol

from iris.runtime.user_turn import UserTurn


class YouBubbleSurface(Protocol):
    """활성 채팅 표면에 You 한 줄을 그린다. Qt 슬롯/스레드 가정은 호출자 몫."""

    def paint_you(self, text: str) -> None:
        """append_message_instant('You', …) 또는 WorkspaceIrisPanel.append_user."""
        raise NotImplementedError


class UserBubblePaintRegistry:
    """turn.id 키 멱등 You 페인트. 순수 상태 — Qt/IO 없음."""

    def __init__(self) -> None:
        self._painted: set[str] = set()

    def was_painted(self, turn_id: str) -> bool:
        return turn_id in self._painted

    def mark_painted(self, turn_id: str) -> None:
        """STT pending 완료처럼 이미 화면에 You가 있을 때 레지스트리만 맞춤."""
        self._painted.add(turn_id)

    def forget(self, turn_id: str) -> None:
        self._painted.discard(turn_id)

    def clear(self) -> None:
        self._painted.clear()

    def ensure_user_bubble(
        self,
        surface: YouBubbleSurface,
        turn: UserTurn,
        *,
        display: str,
        skip: bool = False,
    ) -> bool:
        """
        이 turn.id로 You가 아직 없으면 surface.paint_you(display) 후 True.
        이미 칠했거나 skip이면 False (no-op).
        """
        # not implemented — design only
        raise NotImplementedError


# 편의 함수 (모듈 레벨; 레지스트리 인스턴스는 MainWindow가 소유)
def ensure_user_bubble(
    registry: UserBubblePaintRegistry,
    surface: YouBubbleSurface,
    turn: UserTurn,
    *,
    display: str,
    skip: bool = False,
) -> bool:
    return registry.ensure_user_bubble(
        surface, turn, display=display, skip=skip
    )
```

Surface 어댑터 스케치 (MainWindow 근처, production 아님):

```python
class MainChatYouSurface:
    def __init__(self, chat_panel) -> None:
        self._chat = chat_panel

    def paint_you(self, text: str) -> None:
        # self._chat.append_message_instant("You", text)
        raise NotImplementedError


class WorkspaceYouSurface:
    def __init__(self, panel) -> None:
        self._panel = panel

    def paint_you(self, text: str) -> None:
        # self._panel.append_user(text)
        raise NotImplementedError


def resolve_you_surface(window) -> YouBubbleSurface:
    # panel = window._active_workspace_iris_panel()
    # return WorkspaceYouSurface(panel) if panel else MainChatYouSurface(window._chat)
    raise NotImplementedError
```

Body 삽입 의사코드:

```python
def _execute_user_turn_body(self, turn: UserTurn) -> None:
    # ... existing resets, gates that return early with their own You ...
    # ... choose_turn_model / cloud auth (sync) ...
    shown = self._format_user_turn_content(turn)
    if self._showing_bound():
        ensure_user_bubble(
            self._user_bubbles,
            resolve_you_surface(self),
            turn,
            display=shown,
            skip=bool(self._turn_is_followthrough),
        )
    attached_store = self._chat_session.attachments
    if turn.attachments or attached_store.roots:
        # AttachmentWorker.start() — after paint
        ...
        return
    self._continue_user_turn(turn, model, owns)
```

Continue 교체 의사코드:

```python
# was: self._chat.append_message_instant('You', shown)
ensure_user_bubble(
    self._user_bubbles,
    resolve_you_surface(self),
    turn,
    display=shown,
    skip=bool(self._turn_is_followthrough),
)
```

### 데이터 구조

| 키 | 값 | 수명 |
|---|---|---|
| `turn.id: str` | membership in `_painted: set[str]` | ensure/mark 시 추가, `_finish_current_turn` / drop 시 `forget` |

- `UserTurn` 불변 유지 — `painted` 필드를 turn에 두지 않음 (이 후보의 구조 제약).
- Display 텍스트: 기존 `_format_user_turn_content(turn)` — turn 생성 직후·AttachmentWorker 전에 가능 (grounding).

### Idempotent transitions

| 사건 | 전이 |
|---|---|
| 첫 `ensure` (skip=False, 미페인트) | paint → add id → `True` |
| 두 번째 `ensure` (continue) | no-op → `False` |
| `mark_painted` (STT 완료) | add id, paint 없음 |
| `ensure` after mark | no-op → `False` |
| `skip=True` (followthrough) | no-op → `False`, id 추가 안 함 (또는 정책: mark만 — Open questions) |
| `forget` | remove id |

## Rationale

### Why registry, not flag-on-turn

- `UserTurn`은 frozen dataclass; 페인트 여부는 UI 세션 관심사다.
- 여러 호출 지점(body / continue / voice)이 **같은 멱등 입구**를 공유해야 한다. 턴 필드면 dispatcher·큐·재제출과 수명이 얽힌다.
- 집합 한 개가 deep module: “이 id로 You를 이미 보여 줬는가”.

### Why ensure before AttachmentWorker

- 체감 지연의 본체는 첨부 prep이다. 동기 게이트는 짧다.
- Early-return 자체-You 경로보다 **뒤**에 두면 이중 You를 피하면서도 첨부 경로를 고친다.
- Continue가 같은 ensure를 쓰므로 “optimistic + 기존 append” 이중 경로가 사라진다.

### Tradeoffs

| 이득 | 비용 |
|---|---|
| 첨부 지연 전에 You 표시 | MainWindow에 registry 소유 + forget 의무 |
| continue와 공유 멱등 API | surface resolve / `_showing_bound`를 ensure 호출마다 맞춤 |
| turn 스키마 무변경 | early-return 경로들은 여전히 직접 append (일관성 느슨) |
| 큐에서는 안 그림 | 대기 중 턴은 프로모션 전까지 You 없음 (오늘과 동일에 가깝) |

### Alternatives considered

| 대안 | 이번 후보에서 안 고른 이유 |
|---|---|
| `UserTurn.user_bubble_shown: bool` (flag-on-turn) | 구조 제약 위반; frozen turn·큐 직렬화와 충돌 |
| `_emit_send`에서 즉시 You | turn.id 없음; dispatcher drop/queue와 불일치; session surface 모호 |
| ChatPanel이 자체 “pending You” 큐 | 런타임 턴 id와 단절; continue 멱등이 패널 내부로 새어 deep module 깨짐 |
| AttachmentWorker 콜백만 앞당김 | You는 여전히 worker 완료 후; 목표 미달 |

### Open questions

1. **Followthrough + skip** — skip 시 id를 mark할지, 아예 안 넣을지. (안 넣는 편이 forget 단순.)
2. **모델 미선택 / cloud block** — ensure를 model 검사 **전**에 두면 실패 턴에도 You가 남는다. UX상 나을 수 있으나 history와 UI 불일치. 후보 A 기본안은 model 통과 후·첨부 전.
3. **자체 You early-return** — 이후 패스에서 ensure로 통일할지, 이번 최소 diff에 둘지.
4. **`_showing_bound() == False`** — 다른 대화 슬롯 실행 중 ensure 생략(오늘 continue와 동일). 전환 후 로그에 You가 없는 턴 허용?
5. **큐 overflow drop** — 페인트 전이면 forget 불필요; 페인트 후 drop은 사실상 active finish 경로만.

### Next implementation step

1. `iris/ui/chat/you_bubble.py`에 registry + Protocol 추가 (단위: ensure 두 번 → 두 번째 False, mark 후 ensure False).
2. `MainWindow.__init__`에 `self._user_bubbles = UserBubblePaintRegistry()`; `_finish_current_turn`에서 `forget(turn_id)`.
3. `_execute_user_turn_body`에서 AttachmentWorker / `_continue_user_turn` 분기 직전에 `ensure_user_bubble` 한 줄.
4. `_continue_user_turn_bound`의 You `append_message_instant` / 음성 fallback을 ensure·mark로 교체.
5. 재현: 첨부 있는 전송 → worker 완료 전 You 1개; 첨부 없음 → You 1개; followthrough → You 0.

## Synthesis decision

_(비움)_
