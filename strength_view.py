#!/usr/bin/env python3
"""
비상 강점 분야(진로·진학 / 인문소양·독서 / 한국사·역사 / 과학·탐구 / 수학) 종합 보기 - API 호출 없음.

  ③ 샘몰 상품화 우선순위: 분야마다 B2G 발주(나라장터 12개월) · 교사 검색 관심(데이터랩) · 교사몰 인기 상품 ·
     경쟁사 강좌 수 vs 자사 강좌 수를 한 줄에 놓고 '단독 상품 / 교재 묶음 차별화 / 대표 상품' 판단을 붙인다.
  ① 채택 학교 → 연수 고객 전환: 학교 단위 계산은 화면(로그인 뒤 교과서 채택 데이터)에서 한다.
     여기서는 교과명 → 강점 분야 연결 규칙과 분야별 추천 연수만 넘긴다(학교 정보 없음).

  build(training_topic_data, mall) -> dict  (combine_dashboard.py 가 호출)
"""
import json
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
ORDER = ["career", "humanities", "history", "science", "math"]
# 교과서 교과명 -> 강점 분야(화면에서 정규식으로 쓴다). 국어·문학·독서·화법은 인문소양·독서로 본다.
SUBJECT_RE = {
    "career": "진로",
    "humanities": "국어|문학|독서|화법|언어|작문|고전|철학|인문",
    "history": "역사|한국사",
    "science": "과학|물리|화학|생명|지구",
    "math": "수학|확률|미적분|기하|대수",
}
# 데이터랩 수집이 아직 새 주제를 모르면(첫 주) 가까운 기존 묶음으로 대신 본다
INTEREST_FALLBACK = {"career": "credit", "science": "subject", "math": "subject"}


def _interest(tid):
    p = HERE / "history" / "teacher_interest_trends.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8")).get("datalab") or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    T = d.get("topics") or {}
    key, approx = (tid, False) if T.get(tid) else (INTEREST_FALLBACK.get(tid), True)
    s = [v for _, v in (T.get(key) or []) if v is not None]
    if len(s) < 16:
        return None
    last, prev = s[-8:], s[-16:-8]
    a, b = sum(last) / 8, sum(prev) / 8
    return {"avg": round(a, 1), "trend": round((a - b) / b * 100) if b else None, "approx": approx,
            "basis": key, "date": d.get("captured_date")}


def _g2b_months():
    import training_topics as tt
    today = date.today()
    since, mid = (today - timedelta(days=365)).isoformat(), (today - timedelta(days=92)).isoformat()
    out = {t: {"n": 0, "n3": 0, "amt": 0, "samples": []} for t in ORDER}
    p = HERE / "history" / "training_bids.jsonl"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = r.get("d") or ""
        if d < since or not tt.is_training_bid(r.get("t"), r.get("o")):
            continue
        for tid in tt.classify_topics(r.get("t")):
            if tid in out:
                o = out[tid]
                o["n"] += 1
                o["amt"] += r.get("a") or 0
                if d >= mid:
                    o["n3"] += 1
                o["samples"].append({"d": d, "t": r.get("t"), "o": r.get("o")})
    for o in out.values():
        o["samples"] = sorted(o["samples"], key=lambda x: x["d"], reverse=True)[:3]
    return out


def build(training_topic_data=None, mall=None):
    import training_topics as tt
    topics = {t["id"]: t for t in (training_topic_data or {}).get("topics", [])}
    pairs = {p["topic"]: p for p in (mall or {}).get("pairs", [])} if (mall or {}).get("available") else {}
    g2b = _g2b_months()
    has_cat = bool((training_topic_data or {}).get("has_catalog"))
    rows = []
    for tid in ORDER:
        meta = tt.TOPIC_META.get(tid)
        if not meta:
            continue
        t, cov = topics.get(tid, {}), (topics.get(tid) or {}).get("coverage") or {}
        own, comp = cov.get("own"), cov.get("comp_avg")
        mp = pairs.get(tid) or {}
        it = _interest(tid)
        # 판단(설명 가능한 단순 규칙)
        if not has_cat or own is None:
            verdict, why = "판단 보류", "경쟁사 강좌 목록이 들어오면 판단합니다."
        elif own == 0 and (comp or 0) > 0:
            verdict, why = "샘몰 단독 상품 1순위", f"경쟁사 평균 {comp}개인데 자사 강좌가 없습니다."
        elif own < (comp or 0):
            verdict, why = "교재 묶음으로 차별화", f"자사 {own}개 < 경쟁사 평균 {comp}개 — 강좌 수 경쟁보다 비상 교재·교과서 연계로 차별화."
        elif own == 0:
            verdict, why = "신규 개척(시장 미성숙)", "자사·경쟁사 모두 강좌가 거의 없습니다 — 시범 과정으로 수요 확인."
        else:
            verdict, why = "샘몰 대표 상품 전면 배치", f"자사 {own}개 ≥ 경쟁사 평균 {comp}개 — 이미 강점, 노출·묶음 판매로 확대."
        props = [{"level": l, "title": c[0], "content": c[1]} for l, c in meta[5].items()]
        rows.append({
            "id": tid, "name": meta[1], "subject_re": SUBJECT_RE[tid],
            "g2b": g2b.get(tid), "interest": it,
            "mall": {"n_prod": mp.get("n_prod", 0), "score": mp.get("score", 0),
                     "products": [{"n": x.get("n"), "p": x.get("p")} for x in (mp.get("products") or [])[:3]]},
            "own": own, "comp_avg": comp, "comp_share": cov.get("comp_share"),
            "verdict": verdict, "why": why, "proposals": props, "policy_note": meta[4],
        })
    return {"generated": date.today().isoformat(), "has_catalog": has_cat, "rows": rows}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1)[:3000])
