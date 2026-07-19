"""LLM 구조화 출력 JSON 스키마 모음."""

_S = {"type": "string"}
_N = {"type": "number"}
_B = {"type": "boolean"}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props,
            "required": required or list(props), "additionalProperties": False}


def _arr(items: dict) -> dict:
    return {"type": "array", "items": items}


AUDIENCE_FIT = _obj({
    "gate_pass": _B,
    "gate_reason": _S,
    "score": _N,
    "category": {"type": "string",
                 "enum": ["global_meme", "tech_science", "sports", "incident"]},
    "angle_hint": _S,
})

COMMENT_INSIGHTS = _obj({
    "peak_moments": _arr(_obj({"second": _N, "why": _S})),
    "memes": _arr(_obj({"original": _S, "korean_idea": _S})),
    "open_questions": _arr(_S),
    "local_context": _arr(_S),
    "sensitive": _arr(_S),
})

SCRIPT = _obj({
    "clips": _arr(_obj({"start": _N, "end": _N, "role": _S})),
    "script": _arr(_obj({
        "text": _S,
        "clip_ref": {"type": ["integer", "null"]},
        "emphasis_words": _arr(_S),
    })),
    "hook_text": _S,
    "keywords": _arr(_S),
})

TITLES = _obj({
    "candidates": _arr(_S),
    "chosen": _obj({"title": _S, "reason": _S}),
})

RISK = _obj({
    "pass": _B,
    "risk_score": _N,
    "escalate": _B,
    "violations": _arr(_obj({"check": _S, "detail": _S})),
})

PRODUCT_RESEARCH = _obj({
    "opportunities": _arr(_obj({
        "product": _S, "demand_signal": _S, "angle": _S,
        "sourcing_hint": _S, "caution": _S,
    })),
})

LONGFORM = _obj({
    "title": _S,
    "description": _S,
})

TONE_REVIEW = _obj({
    "persona_diffs": _arr(_obj({"target": _S, "change": _S, "evidence": _S})),
    "title_prompt_diffs": _arr(_obj({"target": _S, "change": _S, "evidence": _S})),
})
