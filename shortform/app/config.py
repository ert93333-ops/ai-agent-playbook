"""설정 로딩: .env + tracks.yaml + templates.yaml + persona.

모든 경로는 리포지토리의 shortform/ 디렉터리(ROOT) 기준.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "work"
OUT_DIR = ROOT / "out"
ASSETS_DIR = ROOT / "assets"
DB_PATH = ROOT / "shortform.db"

ALLOWED_LICENSES = {"own", "licensed", "cc_by", "public", "commentary"}

# 0-1-1 commentary 변형 규칙 (기계 검증 값)
COMMENTARY_RULES = {
    "min_narration_coverage": 0.70,   # TTS 해설이 러닝타임의 70% 이상
    "max_clip_sec": 8.0,              # 제3자 클립 개별 컷 상한
    "max_footage_ratio": 0.50,        # 원본 푸티지 합계 / 러닝타임 상한
}

MAX_DURATION_SEC = 60.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    anthropic_api_key: str = ""
    # heavy: 대본·리스크 심사처럼 품질이 채널 생사를 가르는 판단
    # light: 소재 점수·댓글 마이닝처럼 기계적 분류 (토큰 비용 ~1/5)
    shortform_model: str = "claude-opus-4-8"
    shortform_model_light: str = "claude-haiku-4-5"

    youtube_api_key: str = ""
    youtube_client_secret_file: str = "client_secret.json"
    youtube_token_file: str = "token.youtube.json"
    ig_access_token: str = ""
    ig_user_id: str = ""

    auto_publish: bool = False
    daily_upload_limit_yt: int = 3
    daily_upload_limit_ig: int = 3
    alert_webhook_url: str = ""

    # 시기별 최적화 목표: subs(YPP 진입 전 — 구독 전환) | retention(이후 — 완주율)
    optimize_goal: str = "subs"
    monthly_llm_budget_usd: float = 50.0

    # 공급사 메일 아웃리치 (SMTP 미설정이면 초안 파일만 생성)
    seller_name: str = ""            # 예: 홍길동 (OO스토어 대표)
    seller_store: str = ""           # 예: 쿠팡 OO스토어
    smtp_host: str = ""              # 예: smtp.gmail.com (앱 비밀번호 사용)
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""         # Resend 사용 시 (SMTP보다 설정 간단)
    outreach_from: str = ""          # Resend 발신 주소 (도메인 인증 필요)
    outreach_auto_send: bool = False # true면 초안 없이 자동 발송


class Track(BaseModel):
    id: str
    enabled: bool
    target_lang: str
    source_langs: list[str]
    trend_regions: list[str]
    persona_file: str
    tts_voice: str
    tts_rate: str
    publish_slots: list[str]
    timezone: str
    categories: list[str]
    daily_upload_limit: int
    # 멀티 채널 리스크 분산: 트랙별 업로드 계정 (비우면 전역 설정 사용)
    youtube_token_file: str | None = None
    youtube_client_secret_file: str | None = None
    subreddits: list[str] = []      # Reddit 소싱 (r/all 외 니치 서브레딧)
    sourcing: str = "trend"         # trend(M1 자동 소싱) | catalog(products.yaml)


def products() -> list[dict[str, Any]]:
    """상품 카탈로그 (products.yaml, 없으면 빈 리스트) — product 트랙용."""
    path = ROOT / "products.yaml"
    if not path.exists():
        return []
    return _load_yaml(path).get("products", [])


def affiliates() -> dict[str, list[str]]:
    """카테고리 → 제휴 링크 문단 (affiliates.yaml, 없으면 빈 dict)."""
    path = ROOT / "affiliates.yaml"
    if not path.exists():
        return {}
    return _load_yaml(path)


@functools.lru_cache
def settings() -> Settings:
    return Settings()


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@functools.lru_cache
def tracks() -> dict[str, Track]:
    raw = _load_yaml(ROOT / "tracks.yaml")["tracks"]
    return {tid: Track(id=tid, **cfg) for tid, cfg in raw.items()}


def enabled_tracks() -> list[Track]:
    return [t for t in tracks().values() if t.enabled]


@functools.lru_cache
def templates() -> dict[str, dict[str, Any]]:
    return _load_yaml(ROOT / "templates.yaml")


def persona(track: Track) -> dict[str, Any]:
    return _load_yaml(ROOT / track.persona_file)


def sources() -> list[dict[str, Any]]:
    path = ROOT / "sources.yaml"
    if not path.exists():
        return []
    return _load_yaml(path).get("sources", [])


def job_dir(job_id: int) -> Path:
    d = WORK_DIR / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    return d
