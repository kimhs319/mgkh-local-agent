"""
configs/config.py

에이전트 전역 설정 값. 하드코딩으로 관리하며 .env 참조 없음.
"""

from pathlib import Path

# Cloudflare AgentHub WebSocket URL
AGENT_HUB_URL: str = "wss://mgkh-agent-hub-worker.mgkhclinic.workers.dev/agent-ws"

# Playwright 세션 파일 경로
SESSION_PATH: str = "session/kakao_state.json"

# mgkh-okchart-api URL
OKCHART_API_URL: str = "http://localhost:8000"

# PDF 출력 디렉토리 (진료비 납입확인서 저장 경로)
PDF_OUTPUT_DIR: str = "C:/receipts"
