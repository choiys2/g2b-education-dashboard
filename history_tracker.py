#!/usr/bin/env python3
"""
매일 파이프라인 실행 결과의 핵심 지표만 history/daily_stats.jsonl 에 한 줄씩 append한다.
live/ 전체는 .gitignore로 매번 덮어써지지만, 이 파일은 git에 커밋되어 다년치가 쌓인다.
용량을 작게 유지하려고 원자료 전체가 아니라 요약 통계만 남긴다.

향후 이 history가 쌓이면(수십~수백 일치) 예측 모델(계절성/추세)이나 경쟁사 활동 추이
분석에 실제로 쓸 수 있는 시계열이 된다 - 하루치로는 아무것도 못 한다는 걸 대시보드에도
정직하게 밝혀야 한다.
"""
import json, os, sys
from datetime import datetime


def summarize(g2b_full, ai_rows, pipe):
    trend = g2b_full.get("trend", {})
    months = trend.get("months", [])
    latest_month_idx = len(months) - 1
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "g2b_total_detail": len(g2b_full.get("detail", [])),
        "g2b_notice_latest_month": trend.get("입찰공고", [None])[latest_month_idx] if months else None,
        "g2b_award_latest_month": trend.get("낙찰", [None])[latest_month_idx] if months else None,
        "ai_rows_count": len(ai_rows),
        "ai_rows_amount_sum": sum(r.get("amount", 0) for r in ai_rows),
        "top_competitor": (g2b_full.get("competitor") or [{}])[0].get("낙찰업체"),
        "top_competitor_amount": (g2b_full.get("competitor") or [{}])[0].get("총낙찰금액"),
        "own_pipeline_total": pipe.get("kpi", {}).get("total", 0),
        "own_pipeline_target": pipe.get("kpi", {}).get("totalTarget", 0),
    }


def main():
    hist_path = "history/daily_stats.jsonl"
    os.makedirs("history", exist_ok=True)

    with open("live/g2b_full_export.json", encoding="utf-8") as f:
        g2b_full = json.load(f)
    # AI_ROWS/PIPE는 combine_dashboard.py가 매번 다시 계산하므로 여기선 최소 재계산만
    try:
        with open("live/own_pipeline_export.json", encoding="utf-8") as f:
            pipe_raw = json.load(f)
    except FileNotFoundError:
        pipe_raw = {}

    ai_rows_count_path = "live/_ai_rows_count.json"
    ai_rows = []
    if os.path.exists(ai_rows_count_path):
        with open(ai_rows_count_path, encoding="utf-8") as f:
            ai_rows = json.load(f)

    row = summarize(g2b_full, ai_rows, {"kpi": pipe_raw.get("kpi", {})})

    today = row["date"]
    lines = []
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
    # 같은 날짜 중복 방지: 오늘자 기존 줄은 빼고 새로 추가(하루 여러 번 돌려도 하루 1건 유지)
    lines = [l for l in lines if json.loads(l).get("date") != today]
    lines.append(json.dumps(row, ensure_ascii=False))

    with open(hist_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"history/daily_stats.jsonl 누적 {len(lines)}일치, 오늘({today}) 기록 완료")


if __name__ == "__main__":
    main()
