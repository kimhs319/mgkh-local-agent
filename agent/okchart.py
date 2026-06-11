"""
agent/okchart.py

mgkh-okchart-api (localhost:8000) 호출 모듈.

- POST /validate/patient      : 환자 본인 확인
- GET  /patient/{sn}/demography : 환자 인구통계 정보 (birth, sex)
- GET  /receipt/{sn}          : 환자 날짜 범위 계산서
- 토큰 없음 또는 만료(401) 시 APP_PASSWORD로 자동 재발급 후 1회 재시도
- 토큰은 session/okchart_token.json 에 저장 (재시작 후에도 유지)
- 생년월일(birth)은 validate_patient 에서만 사용하고 반환값에 포함하지 않음
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


async def _get_with_retry(path: str) -> dict[str, Any]:
    """GET 요청. 토큰 없음 또는 401 시 토큰 재발급 후 1회 재시도."""
    token = _load_token()

    async with httpx.AsyncClient() as client:
        if not token:
            log.info('[okchart] 저장된 토큰 없음, 신규 발급')
            token = await _issue_token(client)

        resp = await client.get(
            f'{OKCHART_API_URL}{path}',
            headers={'Authorization': f'Bearer {token}'},
            timeout=15,
        )
        if resp.status_code == 401:
            log.info('[okchart] 토큰 만료, 재발급 시도')
            token = await _issue_token(client)
            resp = await client.get(
                f'{OKCHART_API_URL}{path}',
                headers={'Authorization': f'Bearer {token}'},
                timeout=15,
            )
        resp.raise_for_status()
        return resp.json()


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
        if not token:
            log.info('[okchart] 저장된 토큰 없음, 신규 발급')
            token = await _issue_token(client)

        result = await _call_validate(client, token, name, birth, phone)

        if result is None:
            log.info('[okchart] 토큰 만료, 재발급 시도')
            token = await _issue_token(client)
            result = await _call_validate(client, token, name, birth, phone)

        if result is None:
            raise RuntimeError('okchart-api 인증 실패 (재발급 후에도 401)')

    return result


async def _call_validate(
    client: httpx.AsyncClient,
    token: str,
    name: str,
    birth: str,
    phone: str,
) -> dict[str, Any] | None:
    """실제 validate API 호출. 401이면 None 반환, 그 외 오류는 raise."""
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


async def get_demography(sn: str) -> dict[str, Any]:
    """환자 인구통계 정보 조회.

    Args:
        sn: 차트번호

    Returns:
        {'sn': str, 'birth': 'YYYY-MM-DD', 'sex': 0|1}
        sex: 1 = 남자, 0 = 여자

    Raises:
        httpx.HTTPStatusError: 404(환자 없음) 또는 서버 오류
    """
    return await _get_with_retry(f'/patient/{sn}/demography')


async def get_receipt(sn: str, date_from: str, date_to: str) -> dict[str, Any]:
    """환자 날짜 범위 계산서 조회.

    Args:
        sn:        차트번호
        date_from: 조회 시작일 (YYYY-MM-DD)
        date_to:   조회 종료일 (YYYY-MM-DD)

    Returns:
        {'sn': str, 'date_from': str, 'date_to': str, 'count': int, 'data': [...]}

    Raises:
        httpx.HTTPStatusError: 404(계산서 없음) 또는 서버 오류
    """
    return await _get_with_retry(
        f'/receipt/{sn}?date_from={date_from}&date_to={date_to}'
    )
