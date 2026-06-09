"""
agent/handler.py

AgentHub로부터 수신한 메시지를 action별로 라우팅한다.
"""

import json
import logging
from typing import Any

import websockets

from agent.discord import send_error
from agent.kakao_chat import rename_chat
from agent.okchart import validate_patient

log = logging.getLogger(__name__)


async def dispatch(msg: dict[str, Any], ws: websockets.WebSocketClientProtocol) -> None:
    """메시지를 action 필드에 따라 라우팅한다.

    Args:
        msg: AgentHub에서 수신한 JSON 딕셔너리
        ws:  AgentHub WebSocket 연결 (응답 전송용)

    수신 메시지 예시:
        rename_chat:
            {"action": "rename_chat", "sn": "000001", "phone": "010-XXXX-XXXX",
             "patient_name": "홍길동", "sender": "홍길동", "code": "123456"}

        validate_patient:
            {"action": "validate_patient", "request_id": "uuid",
             "name": "홍길동", "birth": "19900101", "phone": "010-1234-5678"}
    """
    action = msg.get('action')

    if action == 'rename_chat':
        sender       = msg.get('sender', '')
        code         = msg.get('code', '')
        sn           = msg.get('sn', '')
        patient_name = msg.get('patient_name', '')
        log.info(f'[rename_chat] sender={sender}, code={code}, sn={sn}, patient_name={patient_name}')
        try:
            await rename_chat(sender=sender, code=code, sn=sn, patient_name=patient_name)
        except Exception as e:
            log.error(f'[dispatch] rename_chat 처리 중 오류: {e}')

    elif action == 'validate_patient':
        request_id = msg.get('request_id', '')
        name       = msg.get('name', '')
        birth      = msg.get('birth', '')   # 이 함수 scope에서만 사용
        phone      = msg.get('phone', '')
        log.info(f'[validate_patient] request_id={request_id}, name={name}, phone={phone}')

        try:
            result = await validate_patient(name=name, birth=birth, phone=phone)
            # birth는 result에 포함되지 않음 (okchart.py에서 제외)

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
            # birth 변수 명시적 삭제
            birth = None  # noqa: F841

        await ws.send(json.dumps(payload))
        log.info(f'[validate_patient] 응답 전송 완료 | request_id={request_id}')

    else:
        log.warning(f'Unknown action: {action!r}')
