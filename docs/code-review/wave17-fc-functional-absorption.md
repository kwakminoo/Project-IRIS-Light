# Wave 1.7 기능 흡수 매트릭스

| Hermes 기능 | IRIS 실행 정본과 권한 | 관찰과 잔여 |
|---|---|---|
| `vision_analyze` | `vision.analyze_attachment`, Desktop 첨부 ID 및 로컬 Vision | PDF 쪽 또는 이미지 바이트 입력, 결과 출처와 세션 확인. 실제 Vision 모델 품질 검증 잔여. |
| `image_generate` | Vendor 제공자 구현이 존재 | IRIS Native 연결과 실제 생성 제공자 검증 잔여. |
| `skills_list` | `skill.list`, Desktop 등록 프로필 | 설치 디렉터리 및 비활성 옵션 반영하는 로컬 계약 통과. |
| `skill_view` | `skill.view`, 등록 이름과 스킬 내부 상대 경로 | 본문과 연관 자료, 상위 디렉터리 탈출 차단 계약 통과. |
| `skill_manage` | `skill.manage`, Control 사람 확인 | 등록·수정·활성·비활성·보관 계약. Custom 변경과 보관 유지. 외부 설치 공급자 검증 잔여. |
| `text_to_speech` | 기존 Desktop Voice/TTS 큐 | 모델 호출과 실제 재생의 기능 동등성 잔여. |
| `todo_list` | 기존 턴 활동·추적 | 의존성·완료 증거를 저장하는 Native 태스크 API 잔여. |
| `memory` | IRIS Wiki, 사용자 프로필 | Wiki 읽기·저장 경로 및 대화 검색 사용 가능. 기억 갱신·삭제 모델 계약 잔여. |
| `session_search` | Desktop `chat.search_past`, Gateway `GET /v1/agent/sessions/search` | Desktop 의미 검색과 Gateway 주체별 리터럴 검색. Gateway 토큰 격리·재시작 계약 통과. Gateway 모델 도구 노출은 잔여. |
| `clarify` | ChatPanel 후속 질의 흐름 | 지속되는 질의 대기와 사용자 입력으로 재개하는 모델 계약 잔여. |
| `execute_code` | Native Shell, IDE, `process.manage`와 실행 승인 | Process Skip·Run·출력 및 승인 소비 실측. 범용 인라인 코드 모델 계약 잔여. |
| `delegate_task` | Core 격리 `Engine.fork()` | 부모·자식 요청, 권한 상속·재귀 한도·예산·취소 전파 잔여. |
| `cronjob_manage` | IRIS Routine과 Scheduler | 제품 예약 실행 경로 존재. 모델 관리 계약과 재시작 후 중복 방지 실측 잔여. |
| `computer_use` | Browser, IDE, 에뮬레이터, 학습된 작업 | 제품 도구별 승인 경계. 통합 관찰→실행→취소 검증 잔여. |
| `manage_connections` | Native MCP 설정과 Gateway의 토큰 API | MCP 승인·실행과 Gateway 접속을 실측. 제공자·Connector 재연결 관리 잔여. |

Owned Core 대화 루프, 컨텍스트 압축, Plugin Hook과 오류 처리는 현재 설치본을 사용한다. 보수적으로 별도 검증이 필요한 영역은 외부 부작용과 연결되는 Background Tasks, Hook, 알림 및 모델 제공자 fallback이다. [기능 마감 추적표](wave17-fc-tracker-2026-11-27.md)
