"""
agent/handler.py

AgentHub로부터 수신한 메시지를 action별로 라우팅한다.
"""

import logging
from typing import Any

from agent.kakao_chat import rename_chat

log = logging.getLogger(__name__)


async def dispatch(msg: dict[str, Any]) -> None:
    """메시지를 action 필드에 따라 라우팅한다.

    Args:
        msg: AgentHub에서 수신한 JSON 딕셔너리
             예: {
                   "action": "rename_chat",
                   "sn": "000001",
                   "phone": "010-XXXX-XXXX",
                   "patient_name": "홍길동",
                   "sender": "홍길동",
                   "code": "123456"
                 }
    """
    action = msg.get('action')

    if action == 'rename_chat':
        sender       = msg.get('sender', '')
        code         = msg.get('code', '')
        sn           = msg.get('sn', '')
        patient_name = msg.get('patient_name', '')
        log.info(f'[rename_chat] sender={sender}, code={code}, sn={sn}, patient_name={patient_name}')
        await rename_chat(sender=sender, code=code, sn=sn, patient_name=patient_name)

    else:
        log.warning(f'Unknown action: {action!r}')
