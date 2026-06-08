"""
agent/kakao_chat.py

Playwright를 사용해 카카오톡 PC 브라우저에서
칄카오연락치료실 쳄팅방 이름을 변경한다.

시작 전 접속 URL 확인:
    python -m playwright install chromium
"""

import logging
import os

from playwright.async_api import async_playwright

log = logging.getLogger(__name__)

KAKAO_URL = os.environ.get(
    'KAKAO_URL',
    'https://pc.kakao.com',  # 카카오톡 PC 브라우저 버전 URL
)


async def rename_chat(phone: str, new_name: str) -> None:
    """쳄팅방 이름 변경.

    phone으로 쳄팅방을 검색한 후 다음 순서로 동작:
    1. 검색 마늘에 phone 입력
    2. 첫 번째 결과 우클릭 → ‘대화 이름 변경’ 메뉴
    3. new_name 입력 후 확인
    """
    async with async_playwright() as p:
        # 현재 실행 중인 Chromium에 연결 (persistent context)
        # 실제 환경에서는 connect_over_cdp 또는 launch_persistent_context 사용 권장
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page    = await context.new_page()

        try:
            log.info(f'Navigating to {KAKAO_URL}')
            await page.goto(KAKAO_URL)

            # 채팅방 검색 입력
            search_input = page.locator('input[placeholder*="검색"]').first
            await search_input.fill(phone)
            await page.wait_for_timeout(1000)

            # 첫 번째 결과 우클릭
            first_result = page.locator('[class*="chatItem"], [class*="chat-item"]').first
            await first_result.click(button='right')
            await page.wait_for_timeout(300)

            # 콘텐츠 메뉴에서 '대화 이름 변경' 선택
            rename_menu = page.get_by_text('대화 이름 변경')
            await rename_menu.click()
            await page.wait_for_timeout(300)

            # 새 이름 입력
            name_input = page.locator('input[type="text"]').last
            await name_input.triple_click()  # 기존 텍스트 전체 선택
            await name_input.fill(new_name)

            # 확인 버튼 클릭
            confirm_btn = page.get_by_role('button', name='확인')
            await confirm_btn.click()
            await page.wait_for_timeout(500)

            log.info(f'[rename_chat] Done: "{new_name}"')

        except Exception as e:
            log.error(f'[rename_chat] Failed: {e}', exc_info=True)
            # 스크린샷 저장 (Playwright 디버깅 용)
            await page.screenshot(path='rename_chat_error.png')
            raise

        finally:
            await browser.close()
