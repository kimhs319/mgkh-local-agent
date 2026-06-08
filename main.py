"""
mgkh-local-agent — 진입점

Cloudflare AgentHub DO에 WebSocket으로 상시 연결하여
명령을 수신하고 handler로 위임한다.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

import websockets
from dotenv import load_dotenv

from agent.handler import dispatch

# .env 로드 (LOCAL 개발 환경)
load_dotenv(Path(__file__).parent / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger(__name__)

AGENT_HUB_URL   = os.environ['AGENT_HUB_URL']    # wss://mgkh-otp-worker.<account>.workers.dev/agent-ws
AGENT_SECRET    = os.environ['AGENT_SECRET']      # wrangler secret put AGENT_SECRET 와 동일

RECONNECT_DELAY = 5   # 재접속 대기 시간(초)
PING_INTERVAL   = 30  # keep-alive ping 주기(초)


async def run() -> None:
    """AgentHub에 연결하고 메시지를 처리하는 메인 루프."""
    while True:
        try:
            log.info(f'Connecting to {AGENT_HUB_URL} ...')
            async with websockets.connect(
                AGENT_HUB_URL,
                additional_headers={'X-Agent-Secret': AGENT_SECRET},
                ping_interval=PING_INTERVAL,
                ping_timeout=10,
            ) as ws:
                log.info('Connected to AgentHub.')
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        log.info(f'Received: {msg}')
                        await dispatch(msg)
                    except json.JSONDecodeError:
                        log.warning(f'Non-JSON message: {raw!r}')
                    except Exception as e:
                        log.error(f'dispatch error: {e}', exc_info=True)

        except (websockets.ConnectionClosed, OSError) as e:
            log.warning(f'Connection lost: {e}. Reconnecting in {RECONNECT_DELAY}s...')
            await asyncio.sleep(RECONNECT_DELAY)
        except Exception as e:
            log.error(f'Unexpected error: {e}. Reconnecting in {RECONNECT_DELAY}s...')
            await asyncio.sleep(RECONNECT_DELAY)


def main() -> None:
    loop = asyncio.new_event_loop()

    # Windows 환경에서 Ctrl-C 처리
    if sys.platform == 'win32':
        signal.signal(signal.SIGINT, lambda *_: loop.stop())

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        log.info('Stopped by user.')
    finally:
        loop.close()


if __name__ == '__main__':
    main()
