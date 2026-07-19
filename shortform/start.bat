@echo off
chcp 65001 >nul
title shortform
cd /d %~dp0

where python >nul 2>nul
if errorlevel 1 (
  echo [오류] Python이 설치되어 있지 않습니다. https://www.python.org/downloads/ 에서
  echo 설치할 때 "Add python.exe to PATH"를 반드시 체크하세요.
  pause & exit /b 1
)

if not exist .venv (
  echo [1/4] 가상환경 생성 중...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

rem 마지막으로 추가된 의존성(python-multipart) 기준으로 설치 여부 판단 —
rem 코드 업데이트로 의존성이 늘어나도 자동으로 재설치되게 한다.
pip show python-multipart >nul 2>nul
if errorlevel 1 (
  echo [2/4] 의존성 설치 중... ^(최초 1회, 몇 분 걸립니다^)
  pip install -e ".[media,serve,dev]"
)

if not exist .env (
  echo [3/4] 환경 파일 생성 — 메모장이 열리면 ANTHROPIC_API_KEY를 입력하고 저장하세요.
  copy .env.example .env >nul
  notepad .env
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [주의] ffmpeg가 없습니다. 렌더링이 실패합니다. 설치: winget install ffmpeg
  echo        설치 후 이 창을 닫고 start.bat을 다시 실행하세요.
)

echo [4/4] 대시보드 시작 — 브라우저가 열립니다. 이 창은 닫지 마세요.
start "" http://localhost:8008
python -m uvicorn app.dashboard.server:app --port 8008
pause
