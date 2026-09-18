# archify (vendored)

`diagram.render` 컨트롤 액션이 쓰는 다이어그램 렌더러. 업스트림 서브트리를 그대로 복사한 것이며
IRIS에서 수정하지 않는다 (수정이 필요하면 업스트림에 올린 뒤 커밋 해시를 올려 재반입).

| 항목 | 값 |
|---|---|
| 출처 | https://github.com/tt-a1i/archify (`archify/` 서브트리) |
| pinned 커밋 | `72c750bb070d95171dbb2244e5b62b1b7da69c12` |
| 라이선스 | MIT (`LICENSE`, 루트 `THIRD_PARTY_NOTICES.md`에 고지) |
| 런타임 | Node >= 22 (`iris/system/node_runtime.py`의 `node_executable()` / `is_node_ready`) |
| npm 의존 | 없음 (`package.json`의 `dependencies`가 비어 있음) |

## 반입 범위

`test/`·`examples/`·`package-lock.json`은 제외했다. 나머지는 전량 런타임 경로다.
특히 **`scripts/`는 제외할 수 없다** — `bin/archify.mjs`가 `scripts/check-render-output.mjs`를
자식 node 프로세스로 띄워 산출물을 검사하며, 없으면 `artifact/check-failed`로 실패한다.

`examples/`를 빼면 `archify examples` / `archify demo` 서브커맨드는 동작하지 않는다 (IRIS는 쓰지 않음).

## 오프라인

- CLI 경로에 업데이트 확인이 없다 (업데이트 알림은 스킬 설치용 `scripts/check-update.mjs`이며 `bin`이 참조하지 않음).
- 런타임 네트워크 접근은 `renderers/shared/brand-marks.mjs` 1개소뿐이고 **IR 노드가 brand URL을 가질 때만** 발동한다.
  `iris/system/archify_render.py`가 brand URL을 거절하므로 네트워크 접근은 0이다.
- 산출 HTML은 자기완결적이다 (외부 CDN·폰트 참조 없음).
