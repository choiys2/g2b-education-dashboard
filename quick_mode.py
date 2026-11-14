#!/usr/bin/env python3
"""
배포 방식 결정 - 빠른 배포(수집 생략, 마지막 전체 수집 묶음으로 조합·배포만) 후보인지 판단한다.

  빠른 배포 후보:
    - push 인데 바뀐 파일 중 deploy.yml 이 '단계로 실행하는' 수집 스크립트·워크플로·의존성이 하나도 없을 때
      (화면 템플릿·조합 코드·static_data·브리핑 등만 바뀐 경우)
    - repository_dispatch(비공개 주간보고 갱신) - 수집할 것이 없다
    - workflow_dispatch 에서 quick=true 를 고른 경우
  전체 수집: schedule(매일 06:00), 그 밖의 경우 전부.
실제 빠른 배포 여부는 다음 단계에서 묶음 복원에 성공했는지까지 보고 정한다.
출력: GITHUB_OUTPUT 에 candidate=true|false, reason=...
"""
import json
import os
import re
from pathlib import Path

ALWAYS_FULL = {".github/workflows/deploy.yml", "requirements.txt", "g2b_config.example.json", "run_pipeline.py",
               "check_g2b_health.py", "g2b_history_fallback.py", "fetch_g2b_listings.py", "quick_mode.py"}


def step_scripts():
    s = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")
    run_by_steps = set(re.findall(r"python\s+([\w./-]+\.py)", s))
    # 조합(combine)·지면·API·보고서 단계는 빠른 배포에서도 다시 돌므로 바뀌어도 괜찮다
    rerun = {"combine_dashboard.py", "build_news_briefing.py", "news_api_export.py", "weekly_digest.py", "ics_feed.py",
             "pdf_report.py", "exec_pack.py", "data_pack.py", "encrypt_pages.py", "gh_public_site.py"}
    return run_by_steps - rerun


def main():
    ev, out = os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("GITHUB_OUTPUT")
    payload = {}
    try:
        payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    except Exception:
        pass
    cand, reason = False, ev
    if ev == "repository_dispatch":
        cand, reason = True, "비공개 데이터 갱신 - 수집 불필요"
    elif ev == "workflow_dispatch":
        q = str((payload.get("inputs") or {}).get("quick", "false")).lower() == "true"
        cand, reason = q, "수동 실행(빠른 배포 선택)" if q else "수동 실행(전체 수집)"
    elif ev == "push":
        files = set()
        for c in payload.get("commits") or []:
            for k in ("added", "modified", "removed"):
                files.update(c.get(k) or [])
        heavy = sorted(f for f in files if f in ALWAYS_FULL or f in step_scripts())
        if not payload.get("commits") or not files:
            reason = "푸시 커밋 목록 없음 - 전체 수집"
        elif heavy:
            reason = "수집 스크립트 변경: " + ", ".join(heavy[:5])
        else:
            cand, reason = True, f"화면·조합 변경만 {len(files)}개 파일"
    print(f"빠른 배포 후보: {cand} ({reason})")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"candidate={'true' if cand else 'false'}\nreason={reason}\n")


if __name__ == "__main__":
    main()
