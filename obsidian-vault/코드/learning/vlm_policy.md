# vlm_policy

`iris/learning/vlm_policy.py`

Ollama/API VLM이 업무 학습에 적합한지 판별.

## 주요 정의

- `class VlmVerdict`
- `def supports_vision_capability`
- `def model_name_suggests_vision`
- `def model_supports_vision`
- `def is_learning_capable_vision`
- `def evaluate_ollama_model`
- `def list_learning_vlm_models`
- `def evaluate_api_fallback`

## 내부 의존성

- [[ollama_client]]
