"""교재형 0/1 격자 이미지를 구조화 JSON으로 읽는다 (OCR 대체)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

_MIN_SCORE = 0.55
_MAX_GRIDS = 3


@dataclass(frozen=True)
class GridExtractVerdict:
    ok: bool
    score: float
    data: dict[str, Any] | None
    reason: str


def write_morphology_fixture(path: Path | str) -> None:
    """자검용: 왼쪽 5×5 중앙 3×3 전경 + 오른쪽 3×3 십자 커널."""
    cell, gap, pad, between = 28, 3, 16, 48
    image = [
        [0, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 1, 1, 1, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 0, 0, 0],
    ]
    kernel = [
        [0, 1, 0],
        [1, 1, 1],
        [0, 1, 0],
    ]
    left_w = 5 * cell + 4 * gap
    right_w = 3 * cell + 2 * gap
    height = 5 * cell + 4 * gap
    width = pad + left_w + between + right_w + pad
    canvas = Image.new("RGB", (width, pad + height + pad), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    _paint_grid(draw, pad, pad, image, cell, gap)
    _paint_grid(draw, pad + left_w + between, pad + cell, kernel, cell, gap)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def write_noisy_multi_grid_fixture(path: Path | str) -> None:
    """자검용: 멀리 떨어진 여러 작은 격자 → 잡음 multi-grid 추출 유도."""
    cell, gap, pad = 18, 2, 12
    tiny = [
        [0, 1],
        [1, 0],
    ]
    # 가로·세로로 충분히 벌려 4개 이상 그룹이 생기게 한다.
    positions = [(pad, pad), (pad + 160, pad), (pad, pad + 140), (pad + 160, pad + 140), (pad + 80, pad + 70)]
    width = pad + 160 + 2 * cell + gap + pad
    height = pad + 140 + 2 * cell + gap + pad
    canvas = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    for ox, oy in positions:
        _paint_grid(draw, ox, oy, tiny, cell, gap)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def _paint_grid(
    draw: ImageDraw.ImageDraw,
    ox: int,
    oy: int,
    data: list[list[int]],
    cell: int,
    gap: int,
) -> None:
    for r, row in enumerate(data):
        for c, val in enumerate(row):
            x0 = ox + c * (cell + gap)
            y0 = oy + r * (cell + gap)
            fill = (30, 90, 180) if val == 1 else (255, 255, 255)
            draw.rectangle(
                [x0, y0, x0 + cell - 1, y0 + cell - 1],
                fill=fill,
                outline=(40, 40, 40),
                width=2,
            )


def extract_binary_grid(path: Path | str) -> dict[str, Any] | None:
    """셀 격자 이미지를 0/1 배열로. 신뢰도 낮거나 잡음이면 None."""
    return extract_binary_grid_verdict(path).data


def extract_binary_grid_verdict(path: Path | str) -> GridExtractVerdict:
    """격자 추출 + 신뢰도. score 낮거나 grids>3 이면 ok=False."""
    try:
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    except Exception:
        bgr = None
    if bgr is None:
        # Unicode 경로 등 imread 실패 시 PIL 폴백
        bgr = _imread_bgr(path)
    if bgr is None:
        return GridExtractVerdict(False, 0.0, None, "unreadable")
    cells = _detect_cells(bgr)
    if len(cells) < 4:
        return GridExtractVerdict(False, 0.0, None, "too_few_cells")
    matrices = _cells_to_grids(cells)
    if not matrices:
        return GridExtractVerdict(False, 0.0, None, "no_matrices")
    named = _name_grids(matrices)
    score, reason = _score_named_grids(named)
    if len(named) > _MAX_GRIDS:
        return GridExtractVerdict(False, score, None, "too_many_grids")
    if score < _MIN_SCORE:
        return GridExtractVerdict(False, score, None, reason or "low_score")
    cleaned = _keep_primary_grids(named)
    if not cleaned:
        return GridExtractVerdict(False, score, None, "no_primary_grids")
    data = {
        "kind": "binary_grids",
        "grids": cleaned,
        "op_hint": None,
        "score": round(score, 3),
    }
    return GridExtractVerdict(True, score, data, "ok")


def _imread_bgr(path: Path | str) -> np.ndarray | None:
    try:
        with Image.open(path) as im:
            rgb = np.array(im.convert("RGB"))
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _score_named_grids(named: list[dict[str, Any]]) -> tuple[float, str]:
    n = len(named)
    if n == 0:
        return 0.0, "empty"
    if n > _MAX_GRIDS:
        return 0.0, "too_many_grids"
    score = 0.35
    if n <= 2:
        score += 0.25
    has_cross = False
    has_solid = False
    for g in named:
        data = g.get("data") or []
        rows = len(data)
        cols = len(data[0]) if data else 0
        name = str(g.get("name") or "")
        if rows == 3 and cols == 3 and _looks_like_cross(data):
            has_cross = True
            score += 0.3
        elif 3 <= rows <= 9 and 3 <= cols <= 9 and abs(rows - cols) <= 2:
            has_solid = True
            score += 0.25
        else:
            score -= 0.2
        if name.startswith("grid"):
            score -= 0.25
    if has_cross and has_solid:
        score += 0.15
    score = max(0.0, min(1.0, score))
    if score < _MIN_SCORE:
        return score, "low_score"
    return score, "ok"


def _keep_primary_grids(named: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """image/kernel 만 남긴다. 잡음 gridN 은 모델에 넣지 않는다."""
    primary = [g for g in named if g.get("name") in ("image", "kernel")]
    if primary:
        return primary
    if named:
        first = dict(named[0])
        first["name"] = "image"
        return [first]
    return []


def format_grid_attachment_text(data: dict[str, Any]) -> str:
    lines = ["STRUCTURED BINARY GRID (machine-extracted; verify against the image):"]
    if data.get("op_hint"):
        lines.append(f"op_hint: {data['op_hint']}")
    for grid in data.get("grids") or []:
        name = str(grid.get("name") or "grid")
        rows = grid.get("data") or []
        lines.append(f"{name}:")
        lines.append("```matrix")
        for row in rows:
            lines.append(" ".join(str(int(v)) for v in row))
        lines.append("```")
    lines.append(
        "Attachment metadata: "
        + json.dumps({"kind": data.get("kind")}, ensure_ascii=False)
    )
    return "\n".join(lines)


def _detect_cells(bgr: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """(x, y, w, h, value) 목록. value는 1(채움) 또는 0(빈 칸)."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # 외곽선: 흰 칸·파란 칸 모두 테두리가 있다.
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    min_a = max(64, (h * w) // 12000)
    max_a = (h * w) // 6
    cells: list[tuple[int, int, int, int, int]] = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if area < min_a or area > max_a:
            continue
        ratio = cw / ch if ch else 0
        if ratio < 0.65 or ratio > 1.55:
            continue
        if cw < 10 or ch < 10:
            continue
        # 외곽 전체 이미지 테두리 스킵
        if x <= 1 and y <= 1 and cw >= w - 3 and ch >= h - 3:
            continue
        inset = max(2, min(cw, ch) // 6)
        patch = gray[y + inset : y + ch - inset, x + inset : x + cw - inset]
        if patch.size == 0:
            continue
        value = 1 if float(patch.mean()) < 160 else 0
        cells.append((x, y, cw, ch, value))
    return _dedupe_cells(cells)


def _dedupe_cells(
    cells: list[tuple[int, int, int, int, int]],
) -> list[tuple[int, int, int, int, int]]:
    cells = sorted(cells, key=lambda c: (c[1], c[0], -c[2] * c[3]))
    kept: list[tuple[int, int, int, int, int]] = []
    for c in cells:
        cx, cy = c[0] + c[2] / 2, c[1] + c[3] / 2
        overlap = False
        for k in kept:
            kx, ky = k[0] + k[2] / 2, k[1] + k[3] / 2
            if abs(cx - kx) < min(c[2], k[2]) * 0.45 and abs(cy - ky) < min(c[3], k[3]) * 0.45:
                overlap = True
                break
        if not overlap:
            kept.append(c)
    return kept


def _cells_to_grids(
    cells: list[tuple[int, int, int, int, int]],
) -> list[list[list[int]]]:
    # 가로로 큰 틈이 있으면 별도 격자로 나눈다 (원본 | 커널).
    groups = _split_by_horizontal_gap(cells)
    out: list[list[list[int]]] = []
    for group in groups:
        if len(group) < 4:
            continue
        matrix = _group_to_matrix(group)
        if matrix is not None:
            out.append(matrix)
    return out


def _split_by_horizontal_gap(
    cells: list[tuple[int, int, int, int, int]],
) -> list[list[tuple[int, int, int, int, int]]]:
    if not cells:
        return []
    # 열 중심 x 를 모은 뒤, 안쪽 피치보다 훨씬 큰 틈에서 격자를 자른다.
    centers = sorted({c[0] + c[2] // 2 for c in cells})
    if len(centers) < 3:
        return [cells]
    deltas = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    median_pitch = float(np.median(deltas))
    cut = median_pitch * 1.3
    split_after: set[int] = set()
    for i, d in enumerate(deltas):
        if d > cut:
            split_after.add(centers[i])
    if not split_after:
        return [cells]
    groups: list[list[tuple[int, int, int, int, int]]] = [[]]
    for c in sorted(cells, key=lambda t: t[0] + t[2] // 2):
        cx = c[0] + c[2] // 2
        groups[-1].append(c)
        if cx in split_after:
            groups.append([])
    return [g for g in groups if g]


def _group_to_matrix(
    cells: list[tuple[int, int, int, int, int]],
) -> list[list[int]] | None:
    ys = sorted(c[1] for c in cells)
    xs = sorted(c[0] for c in cells)
    tol_y = max(4, int(np.median([c[3] for c in cells]) * 0.4))
    tol_x = max(4, int(np.median([c[2] for c in cells]) * 0.4))
    row_ys = _bucket(ys, tol=tol_y)
    col_xs = _bucket(xs, tol=tol_x)
    if len(row_ys) < 2 or len(col_xs) < 2:
        return None
    matrix = [[0 for _ in col_xs] for _ in row_ys]
    for x, y, w, h, val in cells:
        ri = min(range(len(row_ys)), key=lambda i: abs(row_ys[i] - y))
        ci = min(range(len(col_xs)), key=lambda i: abs(col_xs[i] - x))
        if abs(row_ys[ri] - y) > h or abs(col_xs[ci] - x) > w:
            continue
        matrix[ri][ci] = max(matrix[ri][ci], val)
    return matrix


def _bucket(values: list[int], *, tol: int) -> list[int]:
    values = sorted(values)
    buckets: list[list[int]] = [[values[0]]]
    for v in values[1:]:
        if abs(v - buckets[-1][-1]) <= tol:
            buckets[-1].append(v)
        else:
            buckets.append([v])
    return [int(sum(b) / len(b)) for b in buckets]


def _name_grids(grids: list[list[list[int]]]) -> list[dict[str, Any]]:
    scored = sorted(grids, key=lambda g: (-(len(g) * len(g[0])), -sum(sum(r) for r in g)))
    out: list[dict[str, Any]] = []
    used_kernel = False
    for i, g in enumerate(scored):
        if len(g) == 3 and len(g[0]) == 3 and _looks_like_cross(g):
            name = "kernel"
            used_kernel = True
        elif i == 0:
            name = "image"
        elif not used_kernel and len(g) == 3 and len(g[0]) == 3:
            name = "kernel"
            used_kernel = True
        else:
            name = f"grid{i + 1}"
        out.append({"name": name, "data": g})
    if out and not any(g["name"] == "image" for g in out):
        out[0]["name"] = "image"
    return out


def _looks_like_cross(g: list[list[int]]) -> bool:
    if len(g) != 3 or any(len(r) != 3 for r in g):
        return False
    return g == [[0, 1, 0], [1, 1, 1], [0, 1, 0]]
