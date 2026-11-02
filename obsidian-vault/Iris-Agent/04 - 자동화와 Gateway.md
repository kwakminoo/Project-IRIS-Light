# Iris Agent — 자동화와 Gateway

> 정리일: 2026-10-28

## 제품 기본

말 턴은 **InternalSidecar**다. 별도 메시징 Gateway를 항상 띄울 필요는 없다.

## ExternalGateway (옵션)

환경 플래그로 HTTP `:8642`를 쓸 수 있다.  
헬스·모델 sync 등 레거시 경로가 여기로 갈 수 있다.

## supervisor

`ensure_iris_agent_runtime`이 설치·핀·기동·warm을 한곳에서 본다.

관련: [[01 - 설치와 설정]] · [[05 - API와 Iris Light 연동]]
