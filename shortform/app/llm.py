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


# $/1M 토큰 (input, output) — 예산 가드용 추정치
_PRICES = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class BudgetExceeded(RuntimeError):
    pass


def _model(tier: str) -> str:
    s = settings()
    return s.shortform_model_light if tier == "light" else s.shortform_model


def _budget_guard() -> None:
    """월 예산 초과 시 호출 차단 — 무인 루프의 비용 폭주 방지."""
    from . import db
    budget = settings().monthly_llm_budget_usd
    if budget > 0 and db.month_llm_cost() >= budget:
        raise BudgetExceeded(
            f"월 LLM 예산 ${budget} 초과 — .env MONTHLY_LLM_BUDGET_USD 조정 필요")


def _record(model: str, usage) -> None:
    from . import db
    inp, outp = _PRICES.get(model, (5.0, 25.0))
    total_in = (usage.input_tokens + (usage.cache_read_input_tokens or 0) // 10
                + (usage.cache_creation_input_tokens or 0))
    cost = total_in / 1e6 * inp + usage.output_tokens / 1e6 * outp
    db.record_llm_usage(model, total_in, usage.output_tokens, round(cost, 6))


def complete_json(prompt: str, schema: dict[str, Any], *,
                  system: str | None = None, max_tokens: int = 16000,
                  tier: str = "heavy") -> dict[str, Any]:
    _budget_guard()
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
    _record(kwargs["model"], resp.usage)
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM refused the request (safety)")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def complete_text(prompt: str, *, system: str | None = None,
                  max_tokens: int = 8000, tier: str = "heavy") -> str:
    _budget_guard()
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
    _record(kwargs["model"], resp.usage)
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM refused the request (safety)")
    return next(b.text for b in resp.content if b.type == "text")
