# TODO: 테스트 후 삭제할 것
# 실행: venv\Scripts\python test_receipt.py

import asyncio
import traceback
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── 테스트 값 (실행 전 교체) ──────────────────────────────
SN        = "000001"       # 차트번호
DATE_FROM = "2025-01-01"  # 조회 시작일 (YYYY-MM-DD)
DATE_TO   = "2025-12-31"  # 조회 종료일 (YYYY-MM-DD)
# ─────────────────────────────────────────────────────────


async def main():
    from agent.pdf_receipt import generate

    print(f"[test] PDF 생성 시작")
    print(f"       sn        = {SN}")
    print(f"       date_from = {DATE_FROM}")
    print(f"       date_to   = {DATE_TO}")
    print()

    try:
        out_path: Path = await generate(sn=SN, date_from=DATE_FROM, date_to=DATE_TO)
        print(f"[test] 성공 — PDF 저장 경로:")
        print(f"       {out_path}")
    except Exception:
        print("[test] 실패 — traceback:")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
