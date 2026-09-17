"""Iris UI 테마 토큰 — PyQt·Theia 공통 사이버스페이스 색상."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ThemeTokens:
    # 우주 배경 — 푸른색 계열
    void_black: str = "#020408"
    space_deep: str = "#050a14"
    space_navy: str = "#0a1224"
    nebula_purple: str = "#0a1a3a"
    nebula_magenta: str = "#0d2847"

    # 레이어
    background_primary: str = "#030508"
    background_secondary: str = "#060d18"
    panel_background: str = "rgba(8, 16, 32, 0.42)"
    panel_overlay: str = "rgba(6, 14, 28, 0.55)"
    panel_border: str = "rgba(56, 189, 248, 0.16)"
    panel_hover: str = "rgba(37, 99, 235, 0.14)"
    border_color: str = "rgba(56, 189, 248, 0.18)"
    border_subtle: str = "rgba(148, 163, 184, 0.12)"
    divider: str = "transparent"

    # 텍스트
    text_primary: str = "#e8f0fe"
    text_secondary: str = "#94a3b8"
    text_muted: str = "#64748b"
    text_hud_label: str = "rgba(147, 197, 253, 0.82)"
    text_accent: str = "#93c5fd"

    # 네온 포인트 — 청색·시안 중심
    neon_purple: str = "#3b82f6"
    neon_magenta: str = "#22d3ee"
    neon_blue: str = "#38bdf8"
    neon_cyan: str = "#22d3ee"
    glow_purple: str = "rgba(59, 130, 246, 0.45)"
    glow_magenta: str = "rgba(34, 211, 238, 0.35)"

    # 액센트·상태
    accent_primary: str = "rgba(30, 64, 175, 0.55)"
    accent_secondary: str = "rgba(34, 211, 238, 0.35)"
    accent_hover: str = "rgba(37, 99, 235, 0.65)"
    accent_border: str = "rgba(96, 165, 250, 0.55)"
    success: str = "#34d399"
    warning: str = "#fbbf24"
    error: str = "#f87171"
    disabled: str = "#475569"

    # HUD 메트릭
    metric_track: str = "rgba(10, 20, 40, 0.72)"
    metric_fill_cpu: str = "#3b82f6"
    metric_fill_gpu: str = "#22d3ee"
    metric_fill_mem: str = "#38bdf8"
    metric_fill_api: str = "rgba(186, 198, 214, 0.72)"

    # 간격 (4px grid)
    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 12
    spacing_lg: int = 16
    spacing_xl: int = 24

    # 모서리
    radius_sm: int = 4
    radius_md: int = 6
    radius_lg: int = 8

    # 테두리
    border_width: int = 1

    # 애니메이션 (ms)
    animation_fast: int = 120
    animation_normal: int = 220

    # 폰트
    font_family: str = '"Segoe UI Variable", "Segoe UI", "Noto Sans KR", "Malgun Gothic"'
    font_mono: str = '"Consolas", "Cascadia Mono", "Courier New"'
    font_size_title: str = "17px"
    font_size_heading: str = "12px"
    font_size_body: str = "13px"
    font_size_caption: str = "11px"
    font_size_base: str = "13px"
    font_size_hud: str = "11px"
    font_size_micro: str = "10px"
    font_size_input: str = "14px"

    # 채팅 블록 (Cursor식 prose / code / tool) — 채팅창 배경과의 명도 차이를 크게
    # 벌리지 않는 차분한 다크 네이비, 테두리도 은은하게.
    chat_block_bg: str = "#141b2e"
    chat_block_border: str = "rgba(148, 163, 184, 0.14)"
    # 실측 확인: Qt Rich Text의 border-color 파서는 rgba() 알파를 무시하고 완전
    # 불투명으로 렌더링한다(반면 background-color의 rgba는 정상적으로 반투명이
    # 유지된다). 그래서 실제로 그려지는 구분선·테두리에는 처음부터 옅은 톤으로
    # 만든 불투명 hex 값을 쓴다.
    chat_block_border_solid: str = "#293251"
    chat_block_radius: int = 8
    # 주의: 이 값은 항상 큰따옴표(") style="..." 속성 안에 삽입된다. 폰트명을
    # 큰따옴표로 감싸면 속성이 중간에서 끊겨 뒤따르는 CSS 선언이 모두 유실되므로
    # 반드시 작은따옴표만 사용한다.
    chat_block_mono_font: str = "'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace"
    chat_block_code_weight: int = 500
    chat_block_line_height: str = "1.6"
    # 코드 블록 헤더(언어명·복사)용 일반 UI 폰트 — font_family와 동일한 스택이지만
    # 위와 같은 이유로 작은따옴표를 사용한다.
    chat_ui_font: str = "'Segoe UI Variable', 'Segoe UI', 'Noto Sans KR', 'Malgun Gothic'"

    # 채팅 인라인 코드 — 배경 대비를 약하게 해 문장 흐름을 방해하지 않도록.
    chat_inline_code_bg: str = "rgba(148, 163, 184, 0.08)"
    chat_inline_code_color: str = "#9fb3d9"

    # 채팅 표(table) — border-bottom은 위와 같은 이유로 불투명 hex를 사용한다.
    chat_table_header_bg: str = "rgba(148, 163, 184, 0.10)"
    chat_table_row_border: str = "#26314a"

    # 채팅 로그 텍스트 선택(드래그 선택) 색상 — 시스템 강조색 대신 테마에 맞는 은은한 톤
    chat_selection_bg: str = "#2c5a8c"
    chat_selection_fg: str = "#f8fafc"

    # 답변 전체보기(Reading Mode) — 반투명 모달이 아니라 "문서를 읽는 화면".
    # 스크림은 뒤쪽 채팅 글씨가 읽히지 않을 만큼 거의 불옵명하게(≈96%) 덮고,
    # 리딩 패널은 스크림보다 한 단계 밝은 다크 네이비로 명도 차이를 만든다.
    chat_reading_scrim: str = "#01030a"
    chat_reading_scrim_alpha: int = 246  # 0–255 → ≈96.5% 불투명
    chat_reading_panel_bg: str = "#0b1120"
    chat_reading_panel_border: str = "rgba(148, 163, 184, 0.10)"
    chat_reading_panel_radius: int = 14
    chat_reading_title_fg: str = "rgba(147, 197, 253, 0.72)"
    chat_reading_scrollbar: str = "rgba(148, 163, 184, 0.26)"
    # 긴 답변 hover — 클릭 가능함을 아주 미세하게만 알린다 (테두리·버튼 없음).
    # QColor로 직접 쓰이므로 CSS 문자열이 아니라 (r, g, b, a) 성분으로 둔다
    # (QColor는 소수 알파를 가진 rgba() 문자열을 파싱하지 못한다).
    chat_reading_hover_rgba: tuple[int, int, int, int] = (148, 163, 184, 14)

    # 채팅 코드 블록 Syntax Highlighting — Pygments Style에 주입되는 의미별 색상.
    # 하드코딩 대신 이 dict만 바꾸면 코드 블록 전체 색상 테마가 바뀐다.
    chat_syntax_colors: dict[str, str] = field(
        default_factory=lambda: {
            "keyword": "#c792ea",      # def/return/if/const 등 예약어 — 부드러운 보라/핑크
            "builtin": "#7ec8e3",      # 내장 함수·타입 (len, print, int, px 단위 등) — 하늘색
            "string": "#a8cc8c",       # 문자열 — 연한 녹색
            "number": "#e3a262",       # 숫자 — 연한 주황
            "constant": "#e3a262",     # true/false/null 등 리터럴 상수
            "comment": "#6b7280",      # 주석 — 명도를 낮춘 회색 (italic)
            "function": "#7fb4e0",     # 함수·메서드 이름 — 부드러운 파랑
            "class_name": "#6ec9c2",   # 클래스 이름 — 청록
            "decorator": "#6ec9c2",    # @decorator
            "tag": "#d99aa8",          # HTML 태그 / JSON 키 — 차분한 로즈(과채도 빨강 지양)
            "attribute": "#7fb4e0",    # HTML·CSS 속성명
            "variable": "#d8e1f0",     # 변수 — 기본 텍스트와 크게 차이나지 않게
            "operator": "#9aa8c0",     # 연산자 — 기본 텍스트보다 약간 어두운 회백색
            "punctuation": "#9aa8c0",  # 구두점 — 기본 텍스트보다 약간 어두운 회백색
        }
    )


TOKENS = ThemeTokens()
