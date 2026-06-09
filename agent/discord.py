"""
agent/discord.py

Discord 웹훅으로 에러 알림을 전송한다.
"""

import logging
import os
import traceback

import httpx

log = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')


async def send_error(location: str, exc: Exception) -> None:
    """에러 정보를 Discord 웹훅으로 전송한다.

    Args:
        location: 에러 발생 위치 (예: 'kakao_chat.rename_chat')
        exc:      발생한 예외 객체
    """
    if not WEBHOOK_URL:
        log.warning('DISCORD_WEBHOOK_URL 이 설정되지 않아 알림을 건너뜁니다.')
        return

    tb = traceback.format_exc()
    content = (
        f'🚨 **[{location}]** 오류 발생\n'
        f'```\n'
        f'{type(exc).__name__}: {exc}\n\n'
        f'{tb}'
        f'```'
    )
    # Discord 메시지 최대 2000자 제한
    if len(content) > 2000:
        content = content[:1990] + '\n…```'

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(WEBHOOK_URL, json={'content': content})
            resp.raise_for_status()
    except Exception as e:
        log.error(f'Discord 알림 전송 실패: {e}')
