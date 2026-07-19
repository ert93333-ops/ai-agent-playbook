"""CLI 진입점.

  python -m app stage m1|m2|m3|m4|m5|policy|m6   # 개별 스테이지
  python -m app run-once                          # 파이프라인 한 바퀴
  python -m app run                               # 24시간 상주 (스케줄러)
  python -m app serve                             # 승인 대시보드
  python -m app ingest <file.mp4> --title T       # 로컬 파일 수동 투입 (Phase 1 테스트)
  python -m app status                            # job 상태 요약
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    ap = argparse.ArgumentParser(prog="shortform")
    sub = ap.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("stage")
    st.add_argument("name", choices=["m1", "m2", "m3", "m4", "m5", "policy", "m6"])
    sub.add_parser("run-once")
    sub.add_parser("run")
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8008)
    ing = sub.add_parser("ingest")
    ing.add_argument("file")
    ing.add_argument("--title", required=True)
    ing.add_argument("--track", default="kr")
    ing.add_argument("--category", default="global_meme")
    ing.add_argument("--license", default="own",
                     choices=["own", "licensed", "cc_by", "public"])
    sub.add_parser("status")

    args = ap.parse_args()

    if args.cmd == "stage":
        from . import policy
        from .stages import (m1_discover, m2_acquire, m3_analyze, m4_edit,
                             m5_render, m6_publish)
        {"m1": m1_discover.run, "m2": m2_acquire.run, "m3": m3_analyze.run,
         "m4": m4_edit.run, "m5": m5_render.run, "policy": policy.run,
         "m6": m6_publish.run}[args.name]()
    elif args.cmd == "run-once":
        from .scheduler import pipeline_tick
        pipeline_tick()
    elif args.cmd == "run":
        from .scheduler import main as run_sched
        run_sched()
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("app.dashboard.server:app", port=args.port)
    elif args.cmd == "ingest":
        from pathlib import Path
        from . import db
        path = Path(args.file).resolve()
        if not path.exists():
            sys.exit(f"file not found: {path}")
        job_id = db.create_job(
            args.track, category=args.category, license_type=args.license,
            source_url=f"file://{path}", source_title=args.title, priority=100,
            payload={"local_path": str(path), "angle_hint": "", "video_id": ""})
        print(f"job {job_id} created (DISCOVERED). 다음: python -m app run-once")
    elif args.cmd == "status":
        from . import db
        with db.conn() as c:
            rows = c.execute(
                "SELECT state, COUNT(*) n FROM jobs GROUP BY state").fetchall()
        for r in rows:
            print(f"{r['state']:16} {r['n']}")


if __name__ == "__main__":
    main()
