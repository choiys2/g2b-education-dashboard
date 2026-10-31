#!/usr/bin/env python3
"""
나라장터 API 점검·장애 + 보관된 정상 수집분(캐시)도 없을 때의 마지막 대체:
저장소에 매일 누적되는 history/ 기록으로 live/full_live.json 을 근사 재구성한다(API 호출 없음).

  - 입찰공고: history/training_bids.jsonl (교원연수 관련 입찰공고 누적, 올해 1/1 이후) -> 점수 재계산
             마감일은 누적 기록에 없어 '진행 중 공고'는 비운다.
  - 낙찰정보: history/competitor_wins.jsonl (경쟁사 낙찰 누적) - 경쟁사 외 낙찰은 없다.
  - 사전규격: 누적 기록이 없어 비운다.
  - 발주계획: history/order_plans.jsonl 최근 등록분.
화면 상단 안내(live/g2b_stale.json)에 '누적 기록 기반 일부 표시'를 적는다.
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

from fetch_g2b_listings import extract_eligibility
from score_listings import score_listing

H = Path(__file__).parent / "history"


def _jsonl(name):
    p = H / name
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _url(key):
    no, _, ordv = (key or "").partition("-")
    return f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={no}&bidPbancOrd={ordv or '000'}" if no else "https://www.g2b.go.kr/"


def build():
    y0 = f"{date.today().year}-01-01"
    bids = {}
    for r in _jsonl("training_bids.jsonl"):
        if (r.get("d") or "") < y0:
            continue
        no = r["k"].rsplit("-", 1)[0]
        if no in bids and bids[no]["_bid_key"] > r["k"]:  # 재공고는 최신 차수만
            continue
        bids[no] = {"공고명": r.get("t", ""), "발주기관": r.get("o", ""), "지역": r.get("r", ""), "예산": _int(r.get("a")),
                    "마감일": "", "공고일": r.get("d", ""), "url": r.get("u") or _url(r["k"]), "_출처": "입찰공고",
                    "_bid_key": r["k"], "자격": extract_eligibility({}), "공공조달분류": ""}
    bid_rows = sorted((score_listing(b) for b in bids.values()), key=lambda x: x["점수"], reverse=True)
    wins = [{"공고명": (w.get("course") or "").strip(), "발주기관": w.get("org", ""), "낙찰업체": w.get("competitor", ""),
             "낙찰금액": _int(w.get("amount")), "낙찰율(%)": w.get("rate", ""), "참여업체수": w.get("metric", ""),
             "개찰일": w.get("date", ""), "url": _url(w.get("_key")), "_출처": "낙찰정보", "_bid_key": w.get("_key", "")}
            for w in _jsonl("competitor_wins.jsonl") if (w.get("date") or "") >= y0]
    wins.sort(key=lambda r: r["개찰일"], reverse=True)
    plans = _jsonl("order_plans.jsonl")
    last = max((p.get("d") or "" for p in plans), default="")
    plans = [{"공고명": p.get("t", ""), "발주기관": p.get("o", ""), "지역": p.get("r", ""), "예산": _int(p.get("a")),
              "발주예정월": p.get("m", ""), "계약방법": p.get("how", ""), "등록일": p.get("d", "")}
             for p in plans if last and (p.get("d") or "")[:7] == last[:7]]
    asof = max([b["공고일"] for b in bid_rows] + [w["개찰일"] for w in wins] or [""])
    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "analytics_days": (date.today() - date(date.today().year, 1, 1)).days + 1,
            "action": {"입찰공고": [], "사전규격": []},
            "analytics": {"입찰공고": bid_rows, "사전규격": [], "낙찰정보": wins},
            "발주계획_오늘스냅샷": plans, "_fallback": "history", "_asof": asof}


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/full_live.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    full = build()
    out.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    a = full["analytics"]
    print(f"누적 기록 기반 대체: 입찰공고 {len(a['입찰공고'])} · 낙찰(경쟁사) {len(a['낙찰정보'])} · 발주계획 {len(full['발주계획_오늘스냅샷'])} · 최근 {full['_asof']}")
    try:
        from build_dashboard import render_v2
        render_v2(full, str(out.parent / "dashboard_live.html"))
    except Exception as e:  # 단독 요약 페이지는 부가물 - 실패해도 통합 대시보드는 진행
        print(f"  [경고] 단독 요약 페이지 생성 실패: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
