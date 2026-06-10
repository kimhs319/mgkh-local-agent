"""
agent/renderer.py

renderer.ts (mgkh-hwp-test) Python 포팅.
pdf2_schema.json을 읽어 HTML 문자열을 동적으로 생성한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ── 타입 별칭 ────────────────────────────────────────────
Schema   = dict[str, Any]
TableDef = dict[str, Any]
CellDef  = dict[str, Any]


def load_schema(schema_path: str | Path) -> Schema:
    """schema JSON 파일을 읽어 dict로 반환."""
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


# ── CSS ──────────────────────────────────────────────────
def _build_css() -> str:
    return """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Noto Sans KR', sans-serif; font-size: 9pt; color: #000; background: #fff; }
    .page { width: 210mm; min-height: 297mm; padding: 15mm 15mm 10mm 15mm; margin: 0 auto; background: #fff; }
    .regulation { font-size: 7.5pt; margin-bottom: 10mm; line-height: 1.5; }
    .title { text-align: center; font-size: 16pt; font-weight: 700; margin-bottom: 6mm; letter-spacing: -0.5px; }
    table { width: 100%; border-collapse: collapse; font-size: 8.5pt; margin-top: -1px; }
    table:first-of-type { margin-top: 0; }
    td { border: 1px solid #000; padding: 2px 4px; vertical-align: middle; line-height: 1.4; }
    .c-header { background-color: #f5f5f5; text-align: center; font-size: 7.5pt; font-weight: 500; white-space: pre-line; }
    .c-label  { background-color: #f5f5f5; font-weight: 500; text-align: center; white-space: nowrap; }
    .c-value  { background-color: #fff; }
    .c-sum    { background-color: #f5f5f5; font-weight: 700; }
    .c-note   { font-size: 7.5pt; line-height: 1.7; padding: 3px 6px; }
    .c-date   { text-align: center; padding: 6px 4px; font-size: 9pt; }
    .r-data td   { height: 18px; border-top: none; border-bottom: none; }
    .r-data-first td { border-top: 1px solid #000; }
    .r-data-last td  { border-bottom: 1px solid #000; }
    .r-sum td    { height: 22px; }
    .r-info td   { height: 26px; }
    """


# ── 정렬 스타일 ───────────────────────────────────────────
def _align_style(align: str | None) -> str:
    if align == "right":  return "text-align:right;padding-right:6px"
    if align == "center": return "text-align:center"
    return "text-align:left;padding-left:4px"


# ── 단일 테이블 렌더 ─────────────────────────────────────
def _build_table(
    table_def: TableDef,
    data: dict[str, Any],
    records: list[dict[str, Any]],
) -> str:
    total_cols      = table_def["totalCols"]
    col_widths      = table_def["colWidths"]
    cells: list[CellDef] = table_def["cells"]
    data_row_tmpl   = table_def.get("dataRowTemplate")

    # ── 전체 행 수 계산 ──
    fixed_max_row = max(c["row"] + c["rowspan"] - 1 for c in cells)
    if data_row_tmpl:
        data_last_row = data_row_tmpl["startRow"] + data_row_tmpl["count"] - 1
    else:
        data_last_row = -1
    total_rows = max(fixed_max_row, data_last_row) + 1

    # ── 가상 그리드 구성 ──
    # grid[r][c] = CellDef(시작셀) | None(점유됨) | missing(빈칸)
    grid: list[list[CellDef | None]] = [
        [None] * total_cols for _ in range(total_rows)
    ]
    _EMPTY = object()  # sentinel: 아직 아무것도 배치 안 된 셀
    grid = [[_EMPTY] * total_cols for _ in range(total_rows)]  # type: ignore

    # 고정 셀 배치
    for cell in cells:
        for dr in range(cell["rowspan"]):
            for dc in range(cell["colspan"]):
                if dr == 0 and dc == 0:
                    grid[cell["row"]][cell["col"]] = cell
                else:
                    grid[cell["row"] + dr][cell["col"] + dc] = None  # 점유

    # 데이터 행 배치
    if data_row_tmpl:
        start_row = data_row_tmpl["startRow"]
        count     = data_row_tmpl["count"]
        cols      = data_row_tmpl["cols"]
        for i in range(count):
            r   = start_row + i
            rec = records[i] if i < len(records) else None
            for col_def in cols:
                synthetic: CellDef = {
                    "type":    "data",
                    "row":     r,
                    "col":     col_def["col"],
                    "rowspan": 1,
                    "colspan": 1,
                    "dataKey": col_def["dataKey"],
                    "align":   col_def["align"],
                    "_rec":    rec,
                }
                grid[r][col_def["col"]] = synthetic

    # ── 행 class 판별 ──
    def row_class(r: int) -> str:
        if data_row_tmpl:
            s, cnt = data_row_tmpl["startRow"], data_row_tmpl["count"]
            if s <= r < s + cnt:
                classes = "r-data"
                if r == s:         classes += " r-data-first"
                if r == s + cnt - 1: classes += " r-data-last"
                return classes
        row_cells = [c for c in cells if c["row"] == r]
        types = {c["type"] for c in row_cells}
        if "sum" in types:                    return "r-sum"
        if "header" in types:                 return ""
        if "label" in types or "value" in types: return "r-info"
        return ""

    # ── HTML 생성 ──
    colgroup = "\n".join(f'    <col style="width:{w}">' for w in col_widths)
    rows_html: list[str] = []

    for r in range(total_rows):
        tds: list[str] = []
        for c in range(total_cols):
            cell = grid[r][c]
            if cell is _EMPTY or cell is None:
                continue

            rs = f' rowspan="{cell["rowspan"]}"' if cell["rowspan"] > 1 else ""
            cs = f' colspan="{cell["colspan"]}"' if cell["colspan"] > 1 else ""

            cls     = ""
            style   = ""
            content = ""

            t = cell["type"]

            if t == "header":
                cls     = "c-header"
                content = (cell.get("text") or "").replace("\n", "<br>")

            elif t == "label":
                cls     = "c-label"
                style   = _align_style(cell.get("align", "center"))
                content = cell.get("text") or ""

            elif t == "value":
                cls     = "c-value"
                style   = _align_style(cell.get("align"))
                raw     = str(data.get(cell["dataKey"], ""))
                suffix  = cell.get("suffix", "")
                content = f"{raw} {suffix}" if suffix else raw

            elif t == "data":
                cls  = "c-value"
                style = _align_style(cell.get("align"))
                rec  = cell.get("_rec")
                content = str(rec.get(cell["dataKey"], "")) if rec else ""

            elif t == "sum":
                cls     = "c-sum"
                style   = _align_style(cell.get("align"))
                content = str(data.get(cell["dataKey"], ""))

            elif t == "facility":
                cls          = "c-value"
                facility_val = str(data.get(cell["dataKey"], ""))
                options      = cell.get("options", [])
                layout       = cell.get("layout", [])
                lines = []
                for row_vals in layout:
                    parts = []
                    for val in row_vals:
                        opt   = next((o for o in options if o["value"] == val), None)
                        label = opt["label"] if opt else val
                        check = "[&#9632;]" if facility_val == val else "[&nbsp;]"
                        parts.append(f"{check} {label}")
                    lines.append(" &nbsp;&nbsp; ".join(parts))
                content = "<br>".join(lines)

            elif t == "date":
                cls   = "c-date"
                style = _align_style("center")
                y = str(data.get(cell.get("yearKey",  "year"),  ""))
                m = str(data.get(cell.get("monthKey", "month"), ""))
                d = str(data.get(cell.get("dayKey",   "day"),   ""))
                content = f"{y} 년 &nbsp; {m} 월 &nbsp; {d} 일"

            elif t == "note":
                cls     = "c-note"
                content = (cell.get("text") or "").replace("\n", "<br>")

            style_attr = f' style="{style}"' if style else ""
            tds.append(f'      <td class="{cls}"{rs}{cs}{style_attr}>{content}</td>')

        rc = row_class(r)
        tr_class = f' class="{rc}"' if rc else ""
        rows_html.append(f"    <tr{tr_class}>\n" + "\n".join(tds) + "\n    </tr>")

    return "\n".join([
        "  <table>",
        "    <colgroup>",
        colgroup,
        "    </colgroup>",
        *rows_html,
        "  </table>",
    ])


# ── 메인 렌더 함수 ────────────────────────────────────────
def render(schema: Schema, data: dict[str, Any]) -> str:
    """schema + data로 A4 HTML 문자열을 생성하여 반환."""
    records: list[dict[str, Any]] = data.get(schema["dataKey"], [])

    tables_html = "\n".join(
        _build_table(t, data, records) for t in schema["tables"]
    )

    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="ko">',
        "<head>",
        '  <meta charset="UTF-8">',
        f'  <title>{schema["title"]}</title>',
        '  <link rel="preconnect" href="https://fonts.googleapis.com">',
        '  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">',
        f'  <style>{_build_css()}</style>',
        "</head>",
        "<body>",
        '<div class="page">',
        f'  <div class="regulation">{schema["regulation"]}</div>',
        f'  <div class="title">{schema["title"]}</div>',
        tables_html,
        "</div>",
        "</body>",
        "</html>",
    ])
