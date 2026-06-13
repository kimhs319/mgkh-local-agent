"""
agent/pdf_receipt.py
진료비 납입확인서 PDF 생성 모듈

주요 흐름:
  1. okchart-api에서 demography + receipt 조회
  2. 주민등록번호 조합 (birth + sex)
  3. configs/pdf2_schema.json 읽어 renderer.render()로 HTML 동적 생성
  4. Playwright로 PDF 출력 → PDF_OUTPUT_DIR 저장

주민등록번호 뒷자리 첫 번호:
  1900년대 남: 1, 여: 2
  2000년대 남: 3, 여: 4
"""

import logging
import os
from datetime import date, datetime
from pathlib import Path

from playwright.async_api import async_playwright

from agent.okchart import get_demography, get_receipt
from agent.renderer import load_schema, render

log = logging.getLogger(__name__)

# ── 기관 정보 (하드코딩) ─────────────────────────────────────
_FACILITY = {
    "facility_type":  "clinic",
    "biz_number":     "233-16-02991",
    "company_name":   "마곡경희한의원",
    "phone":          "02-3664-8075",
    "address":        "서울시 강서구 강서로 385 우성에스비타워 307호",
    "representative": "김희수",
}

# ── 경로 설정 ────────────────────────────────────────────────
_SCHEMA_PATH = Path(__file__).parent.parent / "configs" / "pdf2_schema.json"
_OUTPUT_DIR  = Path(os.environ.get("PDF_OUTPUT_DIR", "."))


def _make_resident_number(birth: str, sex: int) -> str:
    """생년월일 + 성별로 주민등록번호 마스킹 형식 생성.

    Args:
        birth: YYYY-MM-DD
        sex:   1=남자, 0=여자

    Returns:
        예) '800101-1******'
    """
    yy   = birth[2:4]
    mm   = birth[5:7]
    dd   = birth[8:10]
    year = int(birth[:4])
    first = (3 if sex == 1 else 4) if year >= 2000 else (1 if sex == 1 else 2)
    return f"{yy}{mm}{dd}-{first}******"


def _fmt(n) -> str:
    """숫자를 천 단위 콤마 형식으로 변환. 0이면 빈 문자열."""
    v = int(n or 0)
    return f"{v:,}"


def _build_context(receipt_data: list[dict], demo: dict) -> dict:
    """API 응답 데이터를 renderer에 넘길 context dict로 변환."""
    records = []
    sums = dict(
        sum_total=0,
        sum_copay_public=0,
        sum_copay_patient_insured=0,
        sum_copay_patient_uninsured=0,
        sum_copay_patient_uninsured_b=0,
        sum_copay_cash=0,
        sum_patient_total=0,
        sum_card=0,
        sum_cash_receipt=0,
        income_deduction_total=0,
    )

    for r in receipt_data:
        total             = int(r.get("진료비총액",   0) or 0)
        copay_public      = int(r.get("공단부담총액", 0) or 0)
        copay_uninsured   = int(r.get("전액본인부담", 0) or 0)
        copay_uninsured_b = int(r.get("비급여총액",   0) or 0)
        patient_total     = int(r.get("환자부담총액", 0) or 0)
        # ②본인부담(급여) = 환자부담총액 - 전액본인부담 - 비급여총액
        copay_insured = int(r.get("본인부담금", 0) or 0)
        # col7 copay_cash = 환자부담총액(②+③+④)
        copay_cash        = patient_total
        card              = int(r.get("납부카드",       0) or 0)
        cash_receipt      = int(r.get("납부현금영수증", 0) or 0)
        cash              = int(r.get("납부현금",       0) or 0)

        records.append({
            "date":                     r.get("진료일", ""),
            "type":                     r.get("환자구분", "외래"),
            "total":                    _fmt(total),
            "copay_public":             _fmt(copay_public),
            "copay_patient_insured":    _fmt(copay_insured),
            "copay_patient_uninsured":  _fmt(copay_uninsured),
            "copay_patient_uninsured_b": _fmt(copay_uninsured_b),
            "copay_cash":               _fmt(copay_cash),
            "patient_total":            _fmt(card),          # col8 = 카드
            "card":                     _fmt(cash_receipt),  # col9 = 현금영수증
            "cash_receipt":             _fmt(cash),          # col10 = 현금
        })

        sums["sum_total"]                  += total
        sums["sum_copay_public"]           += copay_public
        sums["sum_copay_patient_insured"]  += copay_insured
        sums["sum_copay_patient_uninsured"] += copay_uninsured
        sums["sum_copay_patient_uninsured_b"] += copay_uninsured_b
        sums["sum_copay_cash"]             += copay_cash
        sums["sum_patient_total"]          += card
        sums["sum_card"]                   += cash_receipt
        sums["sum_cash_receipt"]           += cash
        sums["income_deduction_total"]     += patient_total

    today = date.today()
    patient_name = receipt_data[0].get("환자명", "") if receipt_data else ""

    return {
        "patient_name":    patient_name,
        "resident_number": _make_resident_number(demo["birth"], demo["sex"]),
        "records":         records,
        "year":            str(today.year),
        "month":           f"{today.month:02d}",
        "day":             f"{today.day:02d}",
        **{k: _fmt(v) for k, v in sums.items()},
        **_FACILITY,
    }


async def generate(sn: str, date_from: str, date_to: str) -> Path:
    """진료비 납입확인서 PDF를 생성하여 저장 경로를 반환합니다.

    Args:
        sn:        차트번호
        date_from: 조회 시작일 (YYYY-MM-DD)
        date_to:   조회 종료일 (YYYY-MM-DD)

    Returns:
        생성된 PDF 파일 경로 (Path)
    """
    log.info("[pdf_receipt] 생성 시작 sn=%s %s~%s", sn, date_from, date_to)

    # ── 1. API 조회 ──────────────────────────────────────────
    demo    = await get_demography(sn)
    receipt = await get_receipt(sn, date_from, date_to)

    # ── 2. context 구성 ──────────────────────────────────────
    ctx = _build_context(receipt["data"], demo)

    # ── 3. schema 기반 HTML 생성 ─────────────────────────────
    schema = load_schema(_SCHEMA_PATH)
    html   = render(schema, ctx)

    # ── 4. Playwright PDF 출력 ───────────────────────────────
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    filename = f"진료비납입확인서_{ctx['patient_name']}_{now:%Y%m%d_%H%M%S}.pdf"
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
