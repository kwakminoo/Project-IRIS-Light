# Iris Agent — 자동화와 Gateway

> 정리일: 2026-11-24

## 제품 기본

말 턴은 **InternalSidecar만**이다. HTTP `:8642` ExternalGateway는 제품 런타임이 아니다.

## ExternalGateway (retired / non-product)

`iris_agent_gateway.py`는 orphan stop·진단·`start_gateway=True` opt-in용으로만 남는다.  
제품 setup / health / sync는 `shared_engine().ensure_ready`를 쓴다.

## supervisor

`ensure_iris_agent_runtime`이 설치·핀·기동·warm을 한곳에서 본다. 기본 `start_gateway=False`.

관련: [[01 - 설치와 설정]] · [[05 - API와 Iris Light 연동]]
