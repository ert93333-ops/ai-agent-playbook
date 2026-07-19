#!/bin/bash
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python3가 필요합니다"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip show python-multipart >/dev/null 2>&1 || pip install -e ".[media,serve,dev]"
[ -f .env ] || { cp .env.example .env; echo ".env에 ANTHROPIC_API_KEY를 입력하세요"; ${EDITOR:-nano} .env; }
command -v ffmpeg >/dev/null || echo "[주의] ffmpeg 미설치: brew install ffmpeg"
( sleep 2; open http://localhost:8008 ) &
python -m uvicorn app.dashboard.server:app --port 8008
