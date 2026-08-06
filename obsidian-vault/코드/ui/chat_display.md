# chat_display

`iris/ui/chat/chat_display.py`

채팅창 표시용 본문 정규화 (화자 접두사 제거·마크다운 렌더링).

## 주요 정의

- `def strip_speaker_prefix`
- `def normalize_chat_body`
- `def chat_body_to_html`
- `def visible_typing_text`
- `def typing_body_to_html`
- `def effective_typing_duration_ms`
- `def typing_target_index`
- `def scale_typing_duration_ms`
- `def extend_typing_timeline_ms`

## 내부 의존성

- [[activity_privacy]]
- [[markdown_text]]
