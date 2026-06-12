"""
agent/handler.py

AgentHub로부터 수신한 메시지를 action별로 라우팅한다.

액션 목록:
    validate_patient       : 환자 본인 확인 후 validate_result 응답
    check_and_send_receipt : [흐름 1] validate matched → 대화창 탐색
                              - 있으면 pdf 생성 + 전송
                              - 없으면 chat_check_result(chat_found=False) 응답
                                → AgentHub가 OTP 발송
                              - 오류 발생 시 Discord 에러 전송 후 종료 (OTP 미발송)
    rename_and_send_receipt: [흐름 2] verify 성공 → pdf 생성 → rename → dimmed → 전송
"""

import json
import logging
from pathlib import Path
from typing import Any

import websockets
from playwright.async_api import async_playwright

from agent.discord import send_error
from agent.kakao_chat import (
    find_and_rename_chat,
    find_chat_by_name,
    open_kakao_page,
    send_pdf_via_kakao,
)
from agent.okchart import validate_patient
from agent.pdf_receipt import generate as generate_receipt_pdf

log = logging.getLogger(__name__)


async def dispatch(msg: dict[str, Any], ws: websockets.WebSocketClientProtocol) -> None:
    """메시지를 action 필드에 따라 라우팅한다.

    Args:
        msg: AgentHub에서 수신한 JSON 딕셔너리
        ws:  AgentHub WebSocket 연결 (응답 전송용)
    """
    action = msg.get('action')

    # ── validate_patient ─────────────────────────────────────────────────────
    if action == 'validate_patient':
        request_id = msg.get('request_id', '')
        name       = msg.get('name', '')
        birth      = msg.get('birth', '')
        phone      = msg.get('phone', '')
        log.info(f'[validate_patient] request_id={request_id}, name={name}, phone={phone}')

        try:
            result = await validate_patient(name=name, birth=birth, phone=phone)

            if result['matched']:
                log.info(
                    f'[validate_patient] matched | request_id={request_id} '
                    f'sn={result["sn"]} name={result["patient_name"]}'
                )
                payload = {
                    'type':         'validate_result',
                    'request_id':   request_id,
                    'matched':      True,
                    'sn':           result['sn'],
                    'patient_name': result['patient_name'],
                    'phone':        result['phone'],
                }
            else:
                log.info(f'[validate_patient] not_matched | request_id={request_id}')
                payload = {
                    'type':       'validate_result',
                    'request_id': request_id,
                    'matched':    False,
                }

        except Exception as e:
            log.error(f'[validate_patient] 오류: {e}', exc_info=True)
            await send_error('handler.validate_patient', e)
            payload = {
                'type':       'validate_result',
                'request_id': request_id,
                'matched':    False,
                'error':      str(e),
            }

        finally:
            birth = None  # noqa: F841

        await ws.send(json.dumps(payload))
        log.info(f'[validate_patient] 응답 전송 완료 | request_id={request_id}')

    # ── check_and_send_receipt (흐름 1) ──────────────────────────────────────
    elif action == 'check_and_send_receipt':
        sn           = msg.get('sn', '')
        patient_name = msg.get('patient_name', '')
        phone        = msg.get('phone', '')
        date_from    = msg.get('date_from', '')
        date_to      = msg.get('date_to', '')
        log.info(f'[check_and_send_receipt] sn={sn}, name={patient_name}, {date_from}~{date_to}')

        try:
            async with async_playwright() as p:
                page = await open_kakao_page(p)
                chat_page = await find_chat_by_name(page, sn, patient_name)

                if chat_page is None:
                    log.info('[check_and_send_receipt] 대화창 없음 — chat_check_result 전송 (OTP 발송 요청)')
                    await ws.send(json.dumps({
                        'type':         'chat_check_result',
                        'chat_found':   False,
                        'sn':           sn,
                        'patient_name': patient_name,
                        'phone':        phone,
                        'date_from':    date_from,
                        'date_to':      date_to,
                    }))
                    return

                pdf_path: Path = await generate_receipt_pdf(
                    sn=sn, date_from=date_from, date_to=date_to
                )
                await send_pdf_via_kakao(chat_page, pdf_path)
                log.info('[check_and_send_receipt] 완료')

        except Exception as e:
            log.error(f'[check_and_send_receipt] 오류: {e}', exc_info=True)
            await send_error('handler.check_and_send_receipt', e)
            # 오류 시 OTP 발송하지 않고 종료 (예: 카카오 토큰 만료 등 — OTP를 보내도 처리 불가)

    # ── rename_and_send_receipt (흐름 2) ─────────────────────────────────────
    elif action == 'rename_and_send_receipt':
        sn           = msg.get('sn', '')
        patient_name = msg.get('patient_name', '')
        sender       = msg.get('sender', '')
        code         = msg.get('code', '')
        date_from    = msg.get('date_from', '')
        date_to      = msg.get('date_to', '')
        log.info(
            f'[rename_and_send_receipt] sn={sn}, name={patient_name}, '
            f'sender={sender}, {date_from}~{date_to}'
        )

        try:
            # pdf 생성 먼저
            pdf_path = await generate_receipt_pdf(
                sn=sn, date_from=date_from, date_to=date_to
            )

            # 카카오 접속 → rename → dimmed_layer 해제 → 전송
            async with async_playwright() as p:
                page = await open_kakao_page(p)
                chat_page = await find_and_rename_chat(
                    page, sender, code, sn, patient_name
                )
                await send_pdf_via_kakao(chat_page, pdf_path)
                log.info('[rename_and_send_receipt] 완료')

        except Exception as e:
            log.error(f'[rename_and_send_receipt] 오류: {e}', exc_info=True)
            await send_error('handler.rename_and_send_receipt', e)

    else:
        log.warning(f'Unknown action: {action!r}')
