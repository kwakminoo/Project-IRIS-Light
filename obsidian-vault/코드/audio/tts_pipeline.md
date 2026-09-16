# tts_pipeline

`iris/audio/tts_pipeline.py`

실시간 TTS용 semantic chunker + GPU를 쉬지 않고 돌리는 합성 결정.

## 주요 정의

- `def should_start_tts_synth`
- `def _fenced_ranges`
- `def _split_positions`
- `def _trimmed_length`
- `def _semantic_cut`
- `def _first_sentence_cut`
- `def _forced_cut`
- `class TtsSentencePump`

## 내부 의존성

- [[text_normalizer]]
