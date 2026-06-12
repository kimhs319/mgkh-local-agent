"""
agent/kakao_chat.py

카카오비즈니스 채팅 자동화 모듈.
세션 파일(SESSION_PATH)을 로드해 Playwright headless 브라우저로 동작한다.

공개 함수:
    open_kakao_page(p)                                   → page
    find_chat_by_name(page, sn, patient_name)            → chat_page or None
    find_and_rename_chat(page, sender, code, sn, patient_name) → chat_page
    send_pdf_via_kakao(chat_page, pdf_path)              → None
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, async_playwright

from agent.discord import send_error

log = logging.getLogger(__name__)

SESSION_PATH = Path(os.environ.get('SESSION_PATH', 'output/session/kakao_state.json'))
TARGET_URL   = 'https://business.kakao.com/_gxjkUT/chats'
USER_AGENT   = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/131.0.0.0 Safari/537.36'
)


def _chat_name(sn: str, patient_name: str) -> str:
    """채팅방 이름 포맷. find_chat_by_name / find_and_rename_chat 공통 사용."""
    return f'{sn} {patient_name}'


# ── 공통 ─────────────────────────────────────────────────────────────────────

async def open_kakao_page(p) -> Page:
    """Chromium 실행 → 카카오비즈니스 채팅 목록 페이지 진입.

    Args:
        p: async_playwright() 컨텍스트 (호출부에서 관리)

    Returns:
        채팅 목록이 로드된 Page 객체
    """
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(
        storage_state=str(SESSION_PATH),
        user_agent=USER_AGENT,
    )
    page = await context.new_page()

    log.info('채팅 목록 페이지로 이동 중...')
    await page.goto(TARGET_URL)
    await page.wait_for_load_state('domcontentloaded')

    # 계정 선택 버튼 (뜨는 경우만)
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

    log.info('채팅 목록 페이지 진입 완료')
    return page


async def send_pdf_via_kakao(chat_page: Page, pdf_path: Path) -> None:
    """열려 있는 채팅 팝업에서 PDF 파일 전송 후 완료 메시지 입력.

    Args:
        chat_page: 이미 열린 채팅 팝업 Page
        pdf_path:  전송할 PDF 파일 경로
    """
    log.info(f'[send_pdf] PDF 전송 시작: {pdf_path}')
    try:
        # 파일 첨부 → 파일 선택창 동시 대기
        async with chat_page.expect_file_chooser() as fc_info:
            await (
                chat_page
                .get_by_role('button')
                .filter(has_text=re.compile(r'^$'))
                .nth(1)
                .click()
            )
        file_chooser = await fc_info.value
        await file_chooser.set_files(str(pdf_path))
        
        log.info('[send_pdf] 파일 선택 완료')

        # 완료 메시지 전송
        msg_box = chat_page.get_by_role('textbox', name='메시지 보내기')
        await msg_box.click()
        await msg_box.fill('요청하신 서류 전송하였습니다. 감사합니다.')
        await msg_box.press('Enter')

        log.info('[send_pdf] 메시지 전송 완료')
    except Exception as e:
        log.error(f'[send_pdf] 실패: {e}')
        await send_error('kakao_chat.send_pdf', e)
        raise


# ── 흐름 1 전용 ───────────────────────────────────────────────────────────────

async def find_chat_by_name(page: Page, sn: str, patient_name: str) -> Optional[Page]:
    """채팅 목록에서 '{sn} {patient_name}' 으로 대화창을 탐색해 팝업을 반환.

    Args:
        page:         open_kakao_page() 에서 반환된 채팅 목록 Page
        sn:           차트번호
        patient_name: 환자 이름

    Returns:
        채팅 팝업 Page — 탐색 실패 시 None
    """
    name = _chat_name(sn, patient_name)
    log.info(f'[find_chat_by_name] 탐색 중... name={name}')

    locator = page.locator('li').filter(has_text=name)
    count = await locator.count()

    if count == 0:
        log.info(f'[find_chat_by_name] 대화창 없음: {name}')
        return None
    if count > 1:
        log.warning(f'[find_chat_by_name] {count}개 탐색됨, 첫 번째 사용')

    try:
        async with page.expect_popup() as popup_info:
            await locator.first.click()
        chat_page = await popup_info.value
    except Exception as e:
        log.error(f'[find_chat_by_name] 팝업 오픈 실패: {e}')
        await send_error('kakao_chat.find_chat_by_name', e)
        raise

    await chat_page.wait_for_load_state('domcontentloaded')
    await chat_page.wait_for_timeout(2000)
    log.info(f'[find_chat_by_name] 팝업 오픈 완료: {name}')
    return chat_page


# ── 흐름 2 전용 ───────────────────────────────────────────────────────────────

async def find_and_rename_chat(
    page: Page,
    sender: str,
    code: str,
    sn: str,
    patient_name: str,
) -> Page:
    """sender + code 로 대화창 탐색 → 팝업 오픈 → 채팅방 이름을 '{sn} {patient_name}' 으로 변경.

    Args:
        page:         open_kakao_page() 에서 반환된 채팅 목록 Page
        sender:       카카오 채팅방 별명 (탐색 keyword)
        code:         OTP 인증번호 6자리 (탐색 keyword)
        sn:           차트번호
        patient_name: 환자 이름

    Returns:
        이름 변경이 완료된 채팅 팝업 Page

    Raises:
        RuntimeError: 대화창 탐색 실패
    """
    new_name = _chat_name(sn, patient_name)
    log.info(f'[find_and_rename_chat] 탐색 중... sender={sender}, code={code}')

    locator = (
        page.locator('li')
        .filter(has_text=sender)
        .filter(has_text=code)
    )
    count = await locator.count()

    if count == 0:
        msg = f'대화창을 찾을 수 없습니다. (sender={sender}, code={code})'
        log.error(msg)
        err = RuntimeError(msg)
        await send_error('kakao_chat.find_and_rename_chat', err)
        raise err
    if count > 1:
        log.warning(f'[find_and_rename_chat] {count}개 탐색됨, 첫 번째 사용')

    # 팝업 오픈
    try:
        async with page.expect_popup() as popup_info:
            await locator.first.click()
        chat_page = await popup_info.value
    except Exception as e:
        log.error(f'[find_and_rename_chat] 팝업 오픈 실패: {e}')
        await send_error('kakao_chat.find_and_rename_chat_popup', e)
        raise

    await chat_page.wait_for_load_state('domcontentloaded')
    await chat_page.wait_for_timeout(2000)
    log.info('[find_and_rename_chat] 팝업 오픈 완료')

    # 채팅방 이름 변경
    try:
        await chat_page.get_by_role('button', name='사이드 메뉴 열기').click()

        name_input = chat_page.get_by_role('textbox', name='채팅방 이름 입력 메모 입력')
        await name_input.click()
        await name_input.fill(new_name)
        log.info(f'[find_and_rename_chat] 이름 입력: {new_name}')

        await chat_page.get_by_role('button', name='저장').first.click()
        await chat_page.get_by_role('button', name='확인').click()
        log.info(f'[find_and_rename_chat] 이름 변경 완료: {new_name}')
    except Exception as e:
        log.error(f'[find_and_rename_chat] 이름 변경 실패: {e}')
        await send_error('kakao_chat.find_and_rename_chat_rename', e)
        raise

    return chat_page
