"""
agent/okchart.py

mgkh-okchart-api (localhost:8000) 호출 모듈.

- POST /validate/patient  : 환자 본인 확인
- 토큰 만료(401) 시 APP_PASSWORD로 자동 재발급 후 1회 재시도
- 토큰은 session/okchart_token.json 에 저장 (재시작 후에도 유지)
- 생년월일(birth)은 이 모듈 내에서만 사용하고 반환값에 포함하지 않음
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

OKCHART_API_URL    = os.environ.get('OKCHART_API_URL', 'http://localhost:8000')
OKCHART_PASSWORD   = os.environ['OKCHART_APP_PASSWORD']
TOKEN_FILE         = Path(__file__).parent.parent / 'session' / 'okchart_token.json'


def _load_token() -> str:
    """저장된 토큰을 읽어 반환. 없으면 빈 문자열."""
    try:
        if TOKEN_FILE.exists():
            return json.loads(TOKEN_FILE.read_text(encoding='utf-8')).get('token', '')
    except Exception:
        pass
    return ''


def _save_token(token: str) -> None:
    """토큰을 파일에 저장."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps({'token': token}), encoding='utf-8')


async def _issue_token(client: httpx.AsyncClient) -> str:
    """APP_PASSWORD로 okchart-api에 로그인하여 신규 토큰 발급."""
    resp = await client.post(
        f'{OKCHART_API_URL}/login',
        json={'password': OKCHART_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()['token']
    _save_token(token)
    log.info('[okchart] 토큰 재발급 완료')
    return token


async def validate_patient(
    name: str,
    birth: str,
    phone: str,
) -> dict[str, Any]:
    """환자 본인 확인 요청.

    Args:
        name:  이름
        birth: 생년월일 (YYYYMMDD 또는 YYYY-MM-DD) — 반환값에 포함하지 않음
        phone: 전화번호

    Returns:
        matched=True  → {'matched': True,  'sn': str, 'patient_name': str, 'phone': str}
        matched=False → {'matched': False}

    Raises:
        httpx.HTTPError: 네트워크 오류 또는 서버 오류
    """
    token = _load_token()

    async with httpx.AsyncClient() as client:
        # 1회 시도
        result = await _call_validate(client, token, name, birth, phone)

        # 401 → 토큰 재발급 후 재시도
        if result is None:
            log.info('[okchart] 토큰 만료, 재발급 시도')
            token = await _issue_token(client)
            result = await _call_validate(client, token, name, birth, phone)

        if result is None:
            raise RuntimeError('okchart-api 인증 실패 (재발급 후에도 401)')

    # 생년월일은 반환값에 포함하지 않음
    return result


async def _call_validate(
    client: httpx.AsyncClient,
    token: str,
    name: str,
    birth: str,
    phone: str,
) -> dict[str, Any] | None:
    """실제 API 호출. 401이면 None 반환, 그 외 오류는 raise."""
    resp = await client.post(
        f'{OKCHART_API_URL}/validate/patient',
        json={'name': name, 'birth': birth, 'phone': phone},
        headers={'Authorization': f'Bearer {token}'},
        timeout=10,
    )

    if resp.status_code == 401:
        return None

    resp.raise_for_status()
    data = resp.json()

    if data.get('matched'):
        return {
            'matched': True,
            'sn':           data['sn'],
            'patient_name': data['patient_name'],
            'phone':        data['phone'],
        }
    return {'matched': False}
