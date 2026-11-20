"""QThread 기반 워커 (email_workers, iris_agent_workers, ollama_workers, boot_checks_worker).

Agent-readable:
- Owns: UI 스레드 밖에서 도는 메일·Iris Agent·Ollama·부팅 체크.
- Does not: 클라이언트 프로토콜 (`iris/infrastructure`).
- Talks to: 인프라 클라이언트, 설정 다이얼로그.
- Extend via: 스레드는 여기. HTTP 형식은 `*_client.py`.
"""
