"""M7 — 24시간 상주 스케줄러 (APScheduler).

M1 매 2시간 / 파이프라인 워커 매 10분(동시 렌더 1) / 발행은 트랙 슬롯 cron.
프로세스가 재시작돼도 job 상태가 DB에 있으므로 이어서 진행된다(멱등).
"""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from . import policy
from .config import enabled_tracks
from .stages import m1_discover, m2_acquire, m3_analyze, m4_edit, m5_render, m6_publish


def pipeline_tick() -> None:
    """M2~M5 + 정책 판정. 순서대로 한 바퀴 — 각 스테이지는 멱등."""
    m2_acquire.run()
    m3_analyze.run()
    m4_edit.run()
    m5_render.run()
    policy.run()


def main() -> None:
    sched = BlockingScheduler()
    sched.add_job(m1_discover.run, "interval", hours=2, id="m1")
    sched.add_job(pipeline_tick, "interval", minutes=10, id="pipeline",
                  max_instances=1, coalesce=True)
    for track in enabled_tracks():
        for slot in track.publish_slots:
            hh, mm = slot.split(":")
            sched.add_job(m6_publish.run, CronTrigger(
                hour=int(hh), minute=int(mm), timezone=track.timezone),
                id=f"publish-{track.id}-{slot}")
    print("scheduler up:", [str(j) for j in sched.get_jobs()])
    sched.start()


if __name__ == "__main__":
    main()
