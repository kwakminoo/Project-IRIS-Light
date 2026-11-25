# Wave 1.2 W12-01 Hygiene & Secret Audit

| 항목 | 내용 |
|---|---|
| 문서 번호 | W12-01 |
| 작성일 | 2026-11-25 |
| 목적 | 추적 잡음 제거·시크릿 패턴 검사 (값 미출력) |

## 1. 결론

`.gitignore`에 Wave 1.2 잡음 패턴을 추가하고 `git rm --cached`로 추적에서 제거했다. 로컬 파일은 보존했다. History rewrite는 하지 않았다.

## 2. 추적 제외 (검증)

| 경로 | `git ls-files` 개수 |
|---|---|
| `.tmp/` | 0 |
| `.iris/` | 0 |
| `graphify-out/` | 0 |
| `.github/context-mode/` | 0 |
| `.worktrees/` | 0 |
| `ide-folder-native.log` | 0 |
| `_tmp_*` | 0 |

`unittest tests.test_avd_paths.GitHygieneTests` — OK (ignore 문구 + tracked empty).

## 3. 시크릿 패턴 스캔

- 스캔 범위: 추적 중인 `.py/.md/.json/...` 텍스트
- 패턴: api_key / token / password / Bearer / sk- / AKIA 등 (값 미출력)
- 히트 파일 수: 145 (대부분 문서·예제·필드명 언급)

### 고위험 후보 (경로만)

| 경로 | 분류 |
|---|---|
| `integrations/showui-aloha/Aloha_Learn/config/api_keys.json` | 추적됨. 값은 empty (실키 없음, measured) |
| `integrations/showui-aloha/Aloha_Act/config/api_keys_example.json` | example — short/placeholder 분류 |
| 기타 docs/code-review·프롬프트 | 필드명/설명 위주 (추정) |

### 조치

- 이번 Wave: 값 출력·History rewrite·force push **하지 않음**.
- `api_keys.json`이 실키를 담으면 사용자에게 키 교체 + (별도 승인 시) history 정리를 권고한다.
- `.env`는 이미 ignore.

## 4. 조치

1. ignore + cached 제거 완료.
2. 실키 여부는 U13 보고서에서 재확인(값 없이).
