# SerpApi - Yahoo! Images API

> Source: https://serpapi.com/yahoo-images-api  
> 정리일: 2026-07-21

## 개요

SerpApi의 **Yahoo! Images API**는 Yahoo! Images의 검색 결과(SERP)를 스크래핑한다.

- **엔드포인트:** `https://serpapi.com/search?engine=yahoo_images`
- **API uptime:** 97.920%
- 라이브 데모는 SerpApi Playground에서 제공.

## API 파라미터

### 검색 쿼리

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `p` | 필수 | 검색어. 일반 Yahoo! Images 검색에서 쓰는 모든 형식 사용 가능. |

### 지역화 (Localization)

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `yahoo_domain` | 선택 | 사용할 Yahoo! 도메인. 기본값 `search.yahoo.com`. 허용된 도메인이면 앞에 붙는다 (예: `fr.search.yahoo.com`). |

### 고급 이미지 필터 파라미터

| 파라미터 | 용도 | 사용 가능한 값 |
|----------|------|----------------|
| `imgsz` | 크기 필터 | `small`(작음), `medium`(중간), `large`(큼), `wallpaper`(초대형) |
| `imgc` | 색상 필터 | `color`, `bw`(흑백), `red`, `orange`, `yellow`, `green`, `teal`, `blue`, `purple`, `pink`, `brown`, `black`, `gray`, `white` |
| `imgty` | 이미지 유형 필터 | `photo`, `clipart`, `linedrawing`, `gif`(움직이는 GIF), `transparent`(투명) |
| `imga` | 레이아웃 필터 | `square`(정사각), `wide`(가로), `tall`(세로) |
| `imgf` | 인물 필터 | `face`(얼굴만), `portrait`(머리·어깨), `nonportrait`(인물 없음) |
| `imgt` | 시간 필터 | `day`(24시간), `week`(1주), `month`(1달), `year`(1년) |
| `imgl` | 사용 권한 필터 | `cc`(모든 CC), `pd`(퍼블릭 도메인), `fsu`(공유·사용 가능), `fsuc`(상업적 공유·사용), `fmsu`(수정·공유·사용), `fmsuc`(상업적 수정·공유·사용) |

### 페이지네이션

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `b` | 선택 | 결과 오프셋. 지정한 수만큼 건너뛴다. `1`(기본)=첫 결과, `61`=61번째, `121`=121번째 ... |

### SerpApi 파라미터

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `engine` | 필수 | `yahoo_images`로 설정해야 이 엔진 사용. |
| `device` | 선택 | `desktop`(기본), `tablet`(iPad), `mobile`. |
| `no_cache` | 선택 | `false`(기본)=캐시 허용, `true`=캐시 무시하고 새로 가져옴. 캐시는 1시간 만료, 캐시 검색은 무료·검색 횟수 미차감. `async`와 함께 쓰지 말 것. |
| `async` | 선택 | `false`(기본)=결과를 받을 때까지 HTTP 연결 유지, `true`=제출만 하고 나중에 Searches Archive API로 조회. `no_cache`와 함께 쓰지 말 것. Ludicrous Speed 계정에서는 사용 불가. |
| `zero_trace` | 선택 | Enterprise 전용. `true`면 검색 파라미터·파일·메타데이터를 서버에 저장하지 않음(디버깅 어려워질 수 있음). 기본 `false`. |
| `api_key` | 필수 | SerpApi 비공개 키. |
| `output` | 선택 | `json`(기본)=구조화된 결과, `html`=원본 HTML. |

## API 결과

### JSON 결과

- 이미지 결과의 구조화된 데이터 포함.
- 검색 상태는 `search_metadata.status`로 확인: `Processing` → `Success` \|\| `Error`.
- 실패 시 `error`에 오류 메시지 포함.
- `search_metadata.id`는 SerpApi 내부 검색 ID.

### HTML 결과

- JSON 결과 디버깅이나 아직 지원되지 않는 기능용.
- Yahoo! Images의 원본 HTML 반환.

## 응답 JSON 구조

### `images_results[]`

| 필드 | 타입 | 설명 |
|------|------|------|
| `thumbnail` | String | 썸네일 이미지 URL |
| `link` | String | 이미지 페이지 URL |
| `title` | String | 이미지 결과 제목 |
| `original` | String | 원본 업로드 이미지 URL |
| `source` | String | 이미지가 있는 웹사이트 소스 URL |
| `size` | String | 이미지 용량 (예: `200KB`) |
| `dimensions` | String | 이미지 크기 (예: `200x300`) |
| `position` | Integer | 이미지 결과 순위 |

### `related_searches[]` / `suggested_searches[]`

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | String | 연관/추천 검색어 (예: `coffee beans`) |
| `link` | String | 해당 검색 URL |
| `thumbnail` | String | 썸네일 URL |
| `serpapi_link` | String | SerpApi Yahoo! Images Scraper API URL |

### `shopping_results[]`

| 필드 | 타입 | 설명 |
|------|------|------|
| `title` | String | 상품 제목 |
| `link` | String | 상품 URL |
| `thumbnail` | String | 상품 썸네일 URL |
| `seller` | String | 판매자 이름 |
| `price.value` | String | 가격 표시값 (예: `$26.72`) |
| `price.extracted_value` | Numeric | 추출된 숫자 가격 (예: `26.72`) |

### `serpapi_pagination`

| 필드 | 설명 |
|------|------|
| `next` | 다음 페이지 결과 JSON URL |
| `current` | 현재 페이지 결과 JSON URL |

## 요청 예제

```bash
curl "https://serpapi.com/search?engine=yahoo_images&p=coffee&api_key=YOUR_API_KEY"
```

관련: [[00 - SerpApi 개요]]
