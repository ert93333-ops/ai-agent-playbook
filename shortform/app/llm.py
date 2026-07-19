"""Claude API 래퍼.

- 프롬프트는 app/prompts/*.md 파일로 관리 (git 버전 관리 = 판단 기준의 기준점).
- JSON 응답은 output_config.format(json_schema)으로 강제해 파싱 실패를 없앤다.
- 캐시를 위해 큰 고정 입력(전사문 등)은 system 프리픽스에, 가변 질문은 뒤에.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic

from .config import settings

PROMPT_DIR = Path(__file__).parent / "prompts"

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings().anthropic_api_key or None)
    return _client


def load_prompt(name: str, **vars: Any) -> str:
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    for k, v in vars.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _model(tier: str) -> str:
    s = settings()
    return s.shortform_model_light if tier == "light" else s.shortform_model


def complete_json(prompt: str, schema: dict[str, Any], *,
                  system: str | None = None, max_tokens: int = 16000,
                  tier: str = "heavy") -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        model=_model(tier),
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = [{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral"}}]
    resp = client().messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM refused the request (safety)")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def complete_text(prompt: str, *, system: str | None = None,
                  max_tokens: int = 8000, tier: str = "heavy") -> str:
    kwargs: dict[str, Any] = dict(
        model=_model(tier),
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = [{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral"}}]
    resp = client().messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM refused the request (safety)")
    return next(b.text for b in resp.content if b.type == "text")
