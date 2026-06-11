"""
agent/kakao_chat.py

카카오비즈니스 채팅방 이름 변경.
세션 파일(SESSION_PATH)을 로드해 Playwright headless 브라우저로 동작한다.
최초 1회 로그인 후 세션을 저장해두면 이후 자동 재사용된다.
"""

import logging
import os
from pathlib import Path

from playwright.async_api import async_playwright

from agent.discord import send_error

log = logging.getLogger(__name__)

SESSION_PATH = Path(os.environ.get('SESSION_PATH', 'output/session/kakao_state.json'))
TARGET_URL   = 'https://business.kakao.com/_gxjkUT/chats'
USER_AGENT   = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/131.0.0.0 Safari/537.36'
)


async def rename_chat(sender: str, code: str, sn: str, patient_name: str) -> None:
    """카카오비즈니스 채팅방 이름 변경.

    Args:
        sender:       카카오 채팅방 별명 (탐색 keyword)
        code:         OTP 인증번호 6자리 (탐색 number)
        sn:           차트번호
        patient_name: 환자 이름
    """
    new_name = f'{sn} {patient_name}'

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                storage_state=str(SESSION_PATH),
                user_agent=USER_AGENT,
            )
            page = await context.new_page()

            # ── 1. 채팅 목록 페이지 이동 ──────────────────
            log.info('채팅 목록 페이지로 이동 중...')
            await page.goto(TARGET_URL)
            await page.wait_for_load_state('domcontentloaded')

            # ── 2. 계정 선택 버튼 (뜨는 경우만) ──────────
            btn = page.get_by_role('button', name='mgkhclinic1@gmail.com 직원용')
            if await btn.count() > 0:
                log.info('계정 선택 버튼 감지, 클릭')
                try:
                    await btn.click()
                    await page.wait_for_url('**/chats**')
                except Exception as e:
                    log.error(f'계정 선택 버튼 클릭 실패: {e}')
                    await send_error('kakao_chat.account_select', e)
                    raise
            else:
                await page.wait_for_timeout(3000)

            # ── 3. 대화창 탐색 ────────────────────────────
            log.info(f'대화창 탐색 중... (sender: {sender}, code: {code})')
            locator = (
                page.locator('li')
                .filter(has_text=sender)
                .filter(has_text=code)
            )

            count = await locator.count()
            if count == 0:
                msg = f'대화창을 찾을 수 없습니다. (sender: {sender}, code: {code})'
                log.error(msg)
                await send_error('kakao_chat.find_chat', RuntimeError(msg))
                return
            if count > 1:
                log.warning(f'대화창이 {count}개 탐색됩니다. 첫 번째 항목을 사용합니다.')

            # ── 4. 팝업 오픈 ──────────────────────────────
            try:
                async with page.expect_popup() as popup_info:
                    await locator.first.click()
                chat_page = await popup_info.value
            except Exception as e:
                log.error(f'대화창 팝업 오픈 실패: {e}')
                await send_error('kakao_chat.open_popup', e)
                raise

            await chat_page.wait_for_load_state('domcontentloaded')
            await chat_page.wait_for_timeout(2000)
            log.info('대화창 팝업 오픈 완료')

            # ── 5. 채팅방 이름 변경 ───────────────────────
            try:
                await chat_page.get_by_role('button', name='사이드 메뉴 열기').click()

                name_input = chat_page.get_by_role('textbox', name='채팅방 이름 입력 메모 입력')
                await name_input.click()
                await name_input.fill(new_name)
                log.info(f'채팅방 이름 입력: {new_name}')

                await chat_page.get_by_role('button', name='저장').first.click()
                await chat_page.get_by_role('button', name='확인').click()
            except Exception as e:
                log.error(f'채팅방 이름 변경 실패: {e}')
                await send_error('kakao_chat.rename', e)
                raise

            log.info(f'채팅방 이름 변경 완료: {new_name}')

        except Exception as e:
            log.error(f'[rename_chat] 실패: {e}', exc_info=True)
            # 단계별 send_error 에서 이미 처리된 경우 중복 전송 방지
            if not hasattr(e, '_discord_sent'):
                await send_error('kakao_chat.rename_chat', e)
            raise

        finally:
            await browser.close()
