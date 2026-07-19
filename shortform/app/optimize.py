"""M9 — 변형 실험·최적화 엔진 (카테고리 조건부 Thompson sampling).

"어떤 소재에 어떤 톤앤매너가 어울리는가"를 데이터로 학습한다:
- 선택: 차원(voice/tempo/layout/title_formula/persona_tone)별 프리셋을
  카테고리 조건부 Beta 분포에서 샘플링. 카테고리 표본 < MIN_TRIALS면
  templates.yaml의 category_priors → 전역 통계 순으로 폴백.
- 보상: 시청완주율(주지표, 0~1) — M8 성과 수집이 record_result()로 적재.
"""
from __future__ import annotations

import random
from typing import Any

from . import db
from .config import templates

DIMENSIONS = ["layout", "tempo", "voice", "title_formula", "persona_tone"]
MIN_TRIALS = 10      # PLAYBOOK §7: 표본 10 미만이면 결론 내리지 않는다
EXPLORE_TRIALS = 5   # 초반 탐색기: 프리셋당 이 표본을 채울 때까지 강제 다양화


def _stats(dimension: str, preset: str, category: str) -> tuple[int, float]:
    with db.conn() as c:
        row = c.execute(
            "SELECT trials, reward_sum FROM template_stats"
            " WHERE dimension=? AND preset=? AND category=?",
            (dimension, preset, category)).fetchone()
    return (row["trials"], row["reward_sum"]) if row else (0, 0.0)


def _sample(dimension: str, preset: str, category: str) -> float:
    """Beta(성공+1, 실패+1) 샘플. 카테고리 표본 부족 시 전역('*')으로 폴백."""
    trials, reward = _stats(dimension, preset, category)
    if trials < MIN_TRIALS:
        g_trials, g_reward = _stats(dimension, preset, "*")
        trials, reward = trials + g_trials, reward + g_reward
    return random.betavariate(reward + 1, max(trials - reward, 0) + 1)


def choose_params(category: str) -> dict[str, str]:
    """job 하나에 적용할 차원별 프리셋 선택.

    3단계 스케줄 (초반 최대 탐색 → 수렴):
    1. 탐색기: 전역 표본이 프리셋당 EXPLORE_TRIALS 미만인 차원은
       가장 덜 시도된 프리셋을 강제 선택 (라운드로빈 커버리지 —
       초반에 최대한 다양한 방식으로 제작하기 위함).
    2. 프라이어기: 카테고리 표본 부족 시 category_priors 사용.
    3. 수렴기: 카테고리 조건부 Thompson sampling.
    """
    tpl = templates()
    priors = tpl.get("category_priors", {}).get(category, {})
    chosen: dict[str, str] = {}
    for dim in DIMENSIONS:
        presets = list(tpl.get(dim, {}))
        if not presets:
            continue
        global_trials = {p: _stats(dim, p, "*")[0] for p in presets}
        if min(global_trials.values()) < EXPLORE_TRIALS:
            chosen[dim] = min(presets, key=lambda p: global_trials[p])
            continue
        total_cat_trials = sum(_stats(dim, p, category)[0] for p in presets)
        if total_cat_trials < MIN_TRIALS and dim in priors:
            chosen[dim] = priors[dim]
        else:
            chosen[dim] = max(presets, key=lambda p: _sample(dim, p, category))
    return chosen


def variant_params(base: dict[str, str], category: str) -> dict[str, str]:
    """같은 대본의 변형: 차원 하나만 바꿔 원인 추적이 가능하게 한다."""
    tpl = templates()
    dims = [d for d in DIMENSIONS if len(tpl.get(d, {})) > 1]
    if not dims:
        return dict(base)
    dim = random.choice(dims)
    alternatives = [p for p in tpl[dim] if p != base.get(dim)]
    out = dict(base)
    out[dim] = random.choice(alternatives)
    return out


def record_result(params: dict[str, str], category: str, reward: float) -> None:
    """reward = 시청완주율(0~1). 카테고리별 + 전역('*') 동시 적재."""
    reward = max(0.0, min(1.0, reward))
    with db.conn() as c:
        for dim, preset in params.items():
            for cat in (category, "*"):
                c.execute(
                    "INSERT INTO template_stats (dimension, preset, category,"
                    " trials, reward_sum) VALUES (?,?,?,1,?)"
                    " ON CONFLICT(dimension, preset, category) DO UPDATE SET"
                    " trials=trials+1, reward_sum=reward_sum+excluded.reward_sum",
                    (dim, preset, cat, reward))


def resolve(params: dict[str, str]) -> dict[str, Any]:
    """프리셋 이름들 → 실제 파라미터 값 병합 (M4 입력)."""
    tpl = templates()
    out: dict[str, Any] = {"preset_names": params}
    for dim, preset in params.items():
        out.update(tpl.get(dim, {}).get(preset, {}))
    return out
