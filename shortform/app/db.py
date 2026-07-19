"""SQLite 스키마 + 상태 머신.

상태 전이는 반드시 transition()으로만 수행한다 — 허용되지 않은 전이는
예외를 던져 파이프라인 버그를 조기에 드러낸다 (PLAYBOOK §6-2 검증 후 전진).
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .config import DB_PATH

# 정상 흐름. BLOCKED_RIGHTS/FAILED/REJECTED는 어느 상태에서든 진입 가능한 종료 상태.
FLOW = [
    "DISCOVERED", "RIGHTS_OK", "ACQUIRED", "ANALYZED", "EDITED", "RENDERED",
    "APPROVED", "PUBLISHED_YT", "PUBLISHED_IG", "DONE",
]
TERMINAL = {"BLOCKED_RIGHTS", "FAILED", "REJECTED", "DONE"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'DISCOVERED',
    category TEXT,
    license_type TEXT,
    source_url TEXT,
    source_title TEXT,
    priority REAL DEFAULT 0,
    payload TEXT DEFAULT '{}',          -- 스테이지 산출 메타(JSON): keywords, insights, script, titles...
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    variant_of INTEGER,                 -- M9: 원본 job id (변형이면)
    template_params TEXT DEFAULT '{}',  -- M9: layout/tempo/voice/... 프리셋 이름들
    created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS benchmarks (          -- M1 후킹 벤치마크
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT, video_id TEXT UNIQUE, title TEXT,
    views INTEGER, hook_patterns TEXT, collected_at REAL
);
CREATE TABLE IF NOT EXISTS blacklist (
    channel_url TEXT PRIMARY KEY, reason TEXT, added_at REAL
);
CREATE TABLE IF NOT EXISTS policy_decisions (    -- M10 판정 기록 (감사·재학습용)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER, decided_by TEXT,             -- engine | operator
    decision TEXT,                               -- approve | reject | block
    risk_score REAL, perf_score REAL,
    features TEXT, reason TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS policy_state (        -- 트랙별 자율화 레벨 (0-2절)
    track_id TEXT PRIMARY KEY, level INTEGER DEFAULT 0, updated_at REAL
);
CREATE TABLE IF NOT EXISTS performance (         -- M8 성과 수집 (지연 라벨)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER, platform TEXT, measured_at REAL,
    views INTEGER, avg_view_pct REAL, likes INTEGER,
    comments INTEGER, claim_flag INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS template_stats (      -- M9 카테고리 조건부 밴딧 통계
    dimension TEXT, preset TEXT, category TEXT DEFAULT '*',
    trials INTEGER DEFAULT 0, reward_sum REAL DEFAULT 0,
    PRIMARY KEY (dimension, preset, category)
);
CREATE TABLE IF NOT EXISTS uploads (             -- 일일 상한 집계용
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER, platform TEXT, remote_id TEXT, uploaded_at REAL
);
"""


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def create_job(track_id: str, *, category: str, license_type: str,
               source_url: str, source_title: str, priority: float,
               payload: dict[str, Any] | None = None) -> int:
    now = time.time()
    with conn() as c:
        cur = c.execute(
            "INSERT INTO jobs (track_id, category, license_type, source_url,"
            " source_title, priority, payload, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (track_id, category, license_type, source_url, source_title,
             priority, json.dumps(payload or {}, ensure_ascii=False), now, now))
        return cur.lastrowid


def get_job(job_id: int) -> dict[str, Any]:
    with conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(f"job {job_id} not found")
    job = dict(row)
    job["payload"] = json.loads(job["payload"])
    job["template_params"] = json.loads(job["template_params"])
    return job


def jobs_in_state(state: str, track_id: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT id FROM jobs WHERE state=?"
    args: list[Any] = [state]
    if track_id:
        q += " AND track_id=?"
        args.append(track_id)
    q += " ORDER BY priority DESC, id"
    with conn() as c:
        ids = [r["id"] for r in c.execute(q, args)]
    return [get_job(i) for i in ids]


def transition(job_id: int, to_state: str, *, error: str | None = None,
               payload_update: dict[str, Any] | None = None) -> None:
    job = get_job(job_id)
    frm = job["state"]
    ok = (
        to_state in TERMINAL - {"DONE"}
        or (frm in FLOW and to_state in FLOW and FLOW.index(to_state) == FLOW.index(frm) + 1)
        # 인스타 미설정 시 PUBLISHED_YT → DONE 스킵 허용
        or (frm == "PUBLISHED_YT" and to_state == "DONE")
    )
    if not ok:
        raise ValueError(f"illegal transition {frm} -> {to_state} (job {job_id})")
    payload = job["payload"]
    if payload_update:
        payload.update(payload_update)
    with conn() as c:
        c.execute(
            "UPDATE jobs SET state=?, error=?, payload=?, updated_at=? WHERE id=?",
            (to_state, error, json.dumps(payload, ensure_ascii=False),
             time.time(), job_id))


def update_payload(job_id: int, update: dict[str, Any]) -> None:
    job = get_job(job_id)
    job["payload"].update(update)
    with conn() as c:
        c.execute("UPDATE jobs SET payload=?, updated_at=? WHERE id=?",
                  (json.dumps(job["payload"], ensure_ascii=False), time.time(), job_id))


def record_failure(job_id: int, err: str, max_retries: int = 3) -> bool:
    """재시도 카운트 증가. 한도 초과 시 FAILED 전이하고 False 반환."""
    job = get_job(job_id)
    retries = job["retry_count"] + 1
    with conn() as c:
        c.execute("UPDATE jobs SET retry_count=?, error=?, updated_at=? WHERE id=?",
                  (retries, err, time.time(), job_id))
    if retries >= max_retries:
        transition(job_id, "FAILED", error=err)
        return False
    return True


def autonomy_level(track_id: str) -> int:
    with conn() as c:
        row = c.execute("SELECT level FROM policy_state WHERE track_id=?",
                        (track_id,)).fetchone()
    return row["level"] if row else 0


def set_autonomy_level(track_id: str, level: int) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO policy_state (track_id, level, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(track_id) DO UPDATE SET level=excluded.level,"
            " updated_at=excluded.updated_at",
            (track_id, level, time.time()))


def blacklist_channel(channel_url: str, reason: str) -> None:
    if not channel_url:
        return
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO blacklist (channel_url, reason, added_at)"
                  " VALUES (?,?,?)", (channel_url, reason, time.time()))


def uploads_today(platform: str) -> int:
    day_start = time.time() - (time.time() % 86400)
    with conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM uploads WHERE platform=? AND uploaded_at>=?",
            (platform, day_start)).fetchone()
    return row["n"]
