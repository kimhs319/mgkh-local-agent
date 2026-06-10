"""
agent/pdf_receipt.py
진료비 납입확인서 PDF 생성 모듈

주요 흐름:
  1. okchart-api에서 demography + receipt 조회
  2. 주민등록번호 조합 (birth + sex)
  3. pdf2_schema.json 기관 정보 + receipt 데이터로 Jinja2 HTML 렌더링
  4. Playwright로 PDF 출력 → PDF_OUTPUT_DIR 저장

주민등록번호 뒷자리 첫 번호:
  1900년대 남: 1, 여: 2
  2000년대 남: 3, 여: 4
"""

import logging
import os
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

from agent.okchart import get_demography, get_receipt

log = logging.getLogger(__name__)

# ── 기관 정보 (하드코딩) ─────────────────────────────────────
_FACILITY = {
    "facility_type": "clinic",
    "biz_number":    "000-00-00000",
    "company_name":  "명곡한의원",
    "phone":         "000-000-0000",
    "address":       "주소를 입력하세요",
    "representative": "대표자명",
}

# ── 경로 설정 ────────────────────────────────────────────────
_TEMPLATE_DIR  = Path(__file__).parent.parent / "templates"
_TEMPLATE_FILE = "pdf2.html"
_OUTPUT_DIR    = Path(os.environ.get("PDF_OUTPUT_DIR", "."))


def _make_resident_number(birth: str, sex: int) -> str:
    """생년월일 + 성별로 주민등록번호 마스킹 형식 생성.

    Args:
        birth: YYYY-MM-DD
        sex:   1=남자, 0=여자

    Returns:
        예) '800101-1******'
    """
    yy = birth[2:4]
    mm = birth[5:7]
    dd = birth[8:10]
    year = int(birth[:4])

    if year >= 2000:
        first = 3 if sex == 1 else 4
    else:
        first = 1 if sex == 1 else 2

    return f"{yy}{mm}{dd}-{first}******"


def _fmt_number(n) -> str:
    """숫자를 천 단위 콤마 형식으로 변환. 0이면 빈 문자열."""
    v = int(n or 0)
    return f"{v:,}" if v else ""


def _build_records(receipt_data: list[dict]) -> tuple[list[dict], dict]:
    """receipt API 응답 데이터를 html 템플릿 변수로 변환.

    Returns:
        (records, sums)
        records: 각 진료일 행 데이터 (최대 25건)
        sums:    합계 dict
    """
    records = []
    sums = {
        "sum_total":                 0,
        "sum_copay_public":          0,
        "sum_copay_patient_insured": 0,
        "sum_copay_patient_uninsured": 0,
        "sum_copay_patient_uninsured_b": 0,
        "sum_copay_cash":            0,
        "sum_patient_total":         0,
        "sum_card":                  0,
        "sum_cash_receipt":          0,
        "income_deduction_total":    0,
    }

    for r in receipt_data:
        total          = int(r.get("진료비총액", 0) or 0)
        copay_public   = int(r.get("공단부담총액", 0) or 0)
        # ② 본인부담(급여) = 환자부담총액 - 비급여총액
        copay_insured  = int(r.get("환자부담총액", 0) or 0) - int(r.get("비급여총액", 0) or 0)
        copay_uninsured = int(r.get("전액본인부담", 0) or 0)
        copay_uninsured_b = int(r.get("비급여총액", 0) or 0)
        patient_total  = int(r.get("환자부담총액", 0) or 0)
        card           = int(r.get("납부카드", 0) or 0)
        cash_receipt   = int(r.get("납부현금영수증", 0) or 0)
        cash           = int(r.get("납부현금", 0) or 0)

        records.append({
            "date":                    r.get("진료일", ""),
            "type":                    r.get("환자구분", "외래"),
            "total":                   _fmt_number(total),
            "copay_public":            _fmt_number(copay_public),
            "copay_patient_insured":   _fmt_number(copay_insured),
            "copay_patient_uninsured": _fmt_number(copay_uninsured),
            "copay_patient_uninsured_b": _fmt_number(copay_uninsured_b),
            "copay_cash":              "",
            "patient_total":           _fmt_number(patient_total),
            "card":                    _fmt_number(card),
            "cash_receipt":            _fmt_number(cash_receipt),
            "cash":                    _fmt_number(cash),
        })

        sums["sum_total"]                 += total
        sums["sum_copay_public"]          += copay_public
        sums["sum_copay_patient_insured"] += copay_insured
        sums["sum_copay_patient_uninsured"] += copay_uninsured
        sums["sum_copay_patient_uninsured_b"] += copay_uninsured_b
        sums["sum_patient_total"]         += patient_total
        sums["sum_card"]                  += card
        sums["sum_cash_receipt"]          += cash_receipt
        sums["income_deduction_total"]    += patient_total

    return records, {k: _fmt_number(v) for k, v in sums.items()}


async def generate(sn: str, date_from: str, date_to: str) -> Path:
    """진료비 납입확인서 PDF를 생성하여 저장 경로를 반환합니다.

    Args:
        sn:        차트번호
        date_from: 조회 시작일 (YYYY-MM-DD)
        date_to:   조회 종료일 (YYYY-MM-DD)

    Returns:
        생성된 PDF 파일 경로 (Path)

    Raises:
        httpx.HTTPStatusError: API 오류 (404 등)
        RuntimeError: PDF 생성 실패
    """
    log.info("[pdf_receipt] 생성 시작 sn=%s %s~%s", sn, date_from, date_to)

    # ── 1. API 조회 ──────────────────────────────────────────
    demo    = await get_demography(sn)
    receipt = await get_receipt(sn, date_from, date_to)

    # ── 2. 주민등록번호 조합 ─────────────────────────────────
    resident_number = _make_resident_number(demo["birth"], demo["sex"])

    # ── 3. 템플릿 컨텍스트 구성 ──────────────────────────────
    records, sums = _build_records(receipt["data"])
    max_rows = 25
    empty_rows = max(0, max_rows - len(records))

    today = date.today()
    ctx = {
        "patient_name":    receipt["data"][0]["환자명"] if receipt["data"] else "",
        "resident_number": resident_number,
        "records":         records,
        "empty_rows":      list(range(empty_rows)),
        "year":            str(today.year),
        "month":           f"{today.month:02d}",
        "day":             f"{today.day:02d}",
        **sums,
        **_FACILITY,
    }

    # ── 4. Jinja2 HTML 렌더링 ────────────────────────────────
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
    )
    # Handlebars 스타일 {{var}} → Jinja2 {{var}} 는 동일
    # {{#each records}} 블록을 Jinja2 for 루프로 처리하기 위해
    # 템플릿은 Jinja2 문법으로 작성되어 있어야 합니다.
    template = env.get_template(_TEMPLATE_FILE)
    html = template.render(**ctx)

    # ── 5. Playwright PDF 출력 ───────────────────────────────
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"receipt_{sn}_{date_from}_{date_to}.pdf"
    out_path = _OUTPUT_DIR / filename

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page    = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.pdf(
            path=str(out_path),
            format="A4",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        await browser.close()

    log.info("[pdf_receipt] PDF 저장 완료: %s", out_path)
    return out_path
