"""Iris UI 테마 토큰 — PyQt·Theia 공통 사이버스페이스 색상."""

from __future__ import annotations

from dataclasses import dataclass


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


TOKENS = ThemeTokens()
