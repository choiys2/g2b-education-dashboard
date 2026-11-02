#!/usr/bin/env python3
"""
'교사 트렌드 2027' 탭 데이터 - 이미 모으는 신호를 연수 주제(training_topics 13개) 단위로 합친다.
combine_dashboard.py 에서 호출. 수치는 전부 데이터에서 계산하고, 키워드 이름·설명 문장만 Gemini 가 짓는다
(키가 없거나 실패하면 주제명으로 대체). AI 결과는 history/teacher_trend2027_ai.json 에 캐시(주 1회·순위 변동 시 갱신).

  신호(0~1 정규화)            가중   출처
  공공 수요(연수 입찰 12개월)   .25   training_topics (나라장터)
  검색 관심(데이터랩 지수)      .20   teacher_interest_trends (네이버)
  커뮤니티(블로그·카페 글 수)   .10   teacher_interest_trends (네이버·다음)
  교사 크리에이터(영상 주제)    .15   teacher_creator_trends (유튜브)
  교사몰(인기 상품 수요)        .10   competitor_mall_catalog (티처몰)
  경쟁사 신규 강좌(90일)        .20   competitor_new_courses (티처빌·아이스크림 등)
  성장률 = 입찰 증감·검색 4주 변화·경쟁사 출시 증감의 평균
  성숙도 = 규모(점수) × 성장 -> 부상(작고 빠름) / 확산(크고 빠름) / 성숙(크고 느림) / 관망(작고 느림)
분기 리포트: 분기마다 순위 스냅샷(history/teacher_trend_snapshots.json)을 남겨 직전 분기와 비교.
"""
import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import training_topics
from mall_trends import TOPIC_NAME, topics_of

H = Path(__file__).parent / "history"
AI_CACHE = H / "teacher_trend2027_ai.json"
SNAP = H / "teacher_trend_snapshots.json"
W = {"demand": .25, "search": .20, "buzz": .10, "creator": .15, "mall": .10, "comp": .20}
SIG_NAME = {"demand": "공공 수요", "search": "검색 관심", "buzz": "커뮤니티", "creator": "유튜브", "mall": "교사몰", "comp": "경쟁사 출시"}
NAME_ID = {v: k for k, v in TOPIC_NAME.items()}


def _jsonl(name):
    p = H / name
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def _norm(d, minmax=False):
    vals = [v for v in d.values() if v is not None]
    mx, mn = max(vals or [0]), (min(vals or [0]) if minmax else 0)
    return {k: ((v - mn) / (mx - mn) if mx > mn and v is not None else None) for k, v in d.items()}


def _quarter(d):
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def signals(training, trends, mall, today):
    ids = [t[0] for t in training_topics.TOPICS]
    tt = {t["id"]: t for t in (training or {}).get("topics", [])}
    inter = {r["id"]: r for r in ((trends or {}).get("interest") or {}).get("rows", [])}
    heat = {NAME_ID.get(r["topic"]): r["heat"] for r in (trends or {}).get("heat", [])}
    pairs = {p["topic"]: p for p in (mall or {}).get("pairs", [])}
    # 경쟁사 신규 강좌: 최근 90일 vs 그 앞 90일
    c90, c_prev, c_titles = {}, {}, {}
    cut, cut2 = (today - timedelta(days=90)).isoformat(), (today - timedelta(days=180)).isoformat()
    for r in _jsonl("competitor_new_courses.jsonl"):
        d = r.get("first_seen", "")
        for t in topics_of(r.get("title", "")):
            if d >= cut:
                c90[t] = c90.get(t, 0) + 1
                c_titles.setdefault(t, []).append(f"{r.get('company', '')}: {r.get('title', '')}")
            elif d >= cut2:
                c_prev[t] = c_prev.get(t, 0) + 1
    raw = {
        "demand": {i: (tt.get(i) or {}).get("n") for i in ids},
        "search": {i: (inter.get(i) or {}).get("idx") for i in ids},
        "buzz": {i: (math.log10(inter[i]["posts"] + 1) if inter.get(i, {}).get("posts") else None) for i in ids},
        "creator": {i: heat.get(i) for i in ids},
        "mall": {i: (pairs.get(i) or {}).get("demand") for i in ids},
        "comp": {i: c90.get(i, 0) for i in ids},
    }
    if not any(raw["comp"].values()):
        raw["comp"] = {i: None for i in ids}
    nz = {k: _norm(v, minmax=(k == "buzz")) for k, v in raw.items()}  # 글 수는 로그값끼리 차이가 작아 최소~최대로 펼친다
    rows = []
    for i in ids:
        parts = {k: nz[k][i] for k in W if nz[k][i] is not None}
        wsum = sum(W[k] for k in parts) or 1
        score = round(100 * sum(W[k] * v for k, v in parts.items()) / wsum)
        grs = []
        if (tt.get(i) or {}).get("growth") is not None and (tt[i].get("prior") or 0) >= 3:
            grs.append(tt[i]["growth"])
        if (inter.get(i) or {}).get("mom") is not None:
            grs.append(inter[i]["mom"])
        if c_prev.get(i, 0) >= 2:
            grs.append(round((c90.get(i, 0) / c_prev[i] - 1) * 100))
        growth = round(sum(max(-100, min(200, g)) for g in grs) / len(grs)) if grs else None
        cov = (tt.get(i) or {}).get("coverage") or {}
        rows.append({
            "id": i, "name": TOPIC_NAME.get(i, i), "score": score, "growth": growth,
            "parts": {SIG_NAME[k]: round(v * 100) for k, v in parts.items()},
            "ev": {"입찰 12개월": (tt.get(i) or {}).get("n"), "입찰 증감%": (tt.get(i) or {}).get("growth"),
                   "검색 지수": (inter.get(i) or {}).get("idx"), "검색 4주%": (inter.get(i) or {}).get("mom"),
                   "블로그·카페 글": (inter.get(i) or {}).get("posts"), "유튜브 비중%": heat.get(i),
                   "경쟁사 신규 90일": c90.get(i, 0) if raw["comp"][i] is not None else None,
                   "교사몰 수요": (pairs.get(i) or {}).get("demand")},
            "own": cov.get("own") if cov else (inter.get(i) or {}).get("own"),
            "comp_avg": cov.get("comp_avg"),
            "samples": {"입찰": [], "경쟁사": c_titles.get(i, [])[:4],
                        "유튜브": [v["t"] for v in (trends or {}).get("videos", []) if TOPIC_NAME.get(i) in v.get("topics", [])][:3],
                        "교사몰": [p["n"] for p in (pairs.get(i) or {}).get("products", [])[:3]]},
            "proposal": next((p["title"] for p in (tt.get(i) or {}).get("proposals", [])), ""),
            "policy": (tt.get(i) or {}).get("policy_note", ""),
        })
    # 성숙도: 점수 중앙값 × 성장 10%
    med = sorted(r["score"] for r in rows)[len(rows) // 2]
    for r in rows:
        big, fast = r["score"] >= med, (r["growth"] or 0) >= 10
        r["stage"] = "확산" if big and fast else "부상" if fast else "성숙" if big else "관망"
    # 최근 입찰 공고명 예시(AI 근거용)
    y = (today - timedelta(days=120)).isoformat()
    for b in sorted(_jsonl("training_bids.jsonl"), key=lambda b: b.get("d", ""), reverse=True):
        if b.get("d", "") < y:
            break
        for t in training_topics.classify_topics(b.get("t", "")):
            s = next((r for r in rows if r["id"] == t), None)
            if s and len(s["samples"]["입찰"]) < 4:
                s["samples"]["입찰"].append(b["t"])
    rows.sort(key=lambda r: -r["score"])
    return rows


PROMPT = """너는 한국 초·중등 교원연수 시장 분석가다. 아래는 교원 연수 주제별로 공공 입찰·네이버 검색·블로그/카페·유튜브 교사 채널·교사몰·경쟁 연수원 신규 강좌 신호를 합친 점수와 근거, 실제 사례 제목이다.
이것으로 '교사 트렌드 2027' 키워드 정확히 10개를 만들어라(트렌드 코리아처럼 짧고 기억에 남는 한국어 이름, 2~12자).
규칙:
- 각 키워드는 아래 주제 id 중 하나에 속해야 한다(점수 상위 주제 위주, 한 주제에서 최대 2개).
- 근거 문장(why)에는 아래 표에 있는 숫자만 쓴다. 표에 없는 수치·사실·기관명을 지어내지 않는다.
- action 은 원격교육연수원(비바샘연수원)이 2027년에 할 구체적 과정 개발·마케팅 한 문장.
- 과장·유행어 남발 금지, 존댓말 아닌 평서문.
JSON 배열만 출력: [{"keyword":"", "topic":"주제id", "summary":"한 문장 정의", "why":"근거 한 문장", "action":"실행 한 문장"}]

주제 데이터:
"""


def ai_keywords(rows, today):
    """캐시 우선. 상위 8개 주제 순서가 바뀌었거나 7일 지나면 다시 생성."""
    top = rows[:8]
    sig = hashlib.sha1(json.dumps([r["id"] for r in top]).encode()).hexdigest()[:10]
    try:
        cache = json.loads(AI_CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    fresh = cache.get("sig") == sig and cache.get("date", "") >= (today - timedelta(days=7)).isoformat()
    if fresh and cache.get("keywords"):
        return cache["keywords"], cache.get("date"), "cache"
    try:
        import gemini_client as g
        if not g.key():
            raise RuntimeError("no key")
        brief = [{"id": r["id"], "주제": r["name"], "점수": r["score"], "성장%": r["growth"], "단계": r["stage"],
                  "근거": {k: v for k, v in r["ev"].items() if v is not None}, "자사과정수": r["own"],
                  "사례": {k: v for k, v in r["samples"].items() if v}} for r in top]
        out = g.generate_json(PROMPT + json.dumps(brief, ensure_ascii=False), temperature=0.6)
        ids = {r["id"] for r in rows}
        kws = [{k: str(x.get(k, ""))[:160] for k in ("keyword", "topic", "summary", "why", "action")}
               for x in (out if isinstance(out, list) else []) if x.get("topic") in ids and x.get("keyword")][:10]
        if len(kws) >= 6:
            AI_CACHE.write_text(json.dumps({"sig": sig, "date": today.isoformat(), "keywords": kws}, ensure_ascii=False, indent=1), encoding="utf-8")
            return kws, today.isoformat(), "ai"
    except Exception as e:
        print(f"  [교사 트렌드 2027] AI 키워드 생략: {str(e)[:120]}")
    if cache.get("keywords"):
        return cache["keywords"], cache.get("date"), "cache"
    return [{"keyword": r["name"], "topic": r["id"], "summary": r["policy"], "why": "",
             "action": f"'{r['proposal']}' 과정 검토" if r["proposal"] else ""} for r in rows[:10]], None, "rule"


def quarter_report(rows, today):
    q = _quarter(today)
    try:
        snaps = json.loads(SNAP.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        snaps = {}
    snaps[q] = {"date": today.isoformat(), "rank": [{"id": r["id"], "score": r["score"], "stage": r["stage"]} for r in rows]}
    SNAP.write_text(json.dumps(dict(sorted(snaps.items())[-12:]), ensure_ascii=False, indent=1), encoding="utf-8")
    prev_q = max((k for k in snaps if k < q), default=None)
    if not prev_q:
        return {"quarter": q, "prev": None, "items": []}
    prev = {x["id"]: (i + 1, x) for i, x in enumerate(snaps[prev_q]["rank"])}
    items = []
    for i, r in enumerate(rows):
        p = prev.get(r["id"])
        items.append({"id": r["id"], "name": r["name"], "rank": i + 1, "prev_rank": p[0] if p else None,
                      "d_score": r["score"] - p[1]["score"] if p else None,
                      "stage": r["stage"], "prev_stage": p[1]["stage"] if p else None})
    return {"quarter": q, "prev": prev_q, "items": items}


def build(training=None, trends=None, mall=None, today=None):
    today = today or date.today()
    rows = signals(training, trends, mall, today)
    if not any(r["score"] for r in rows):
        return {"available": False}
    kws, kw_date, kw_src = ai_keywords(rows, today)
    by = {r["id"]: r for r in rows}
    for k in kws:
        r = by.get(k["topic"]) or {}
        k.update({"topic_name": r.get("name", ""), "score": r.get("score"), "growth": r.get("growth"),
                  "stage": r.get("stage"), "own": r.get("own"), "ev": {a: b for a, b in (r.get("ev") or {}).items() if b is not None}})
    for r in rows:
        r.pop("samples", None)
    return {"available": True, "generated": today.isoformat(), "keywords": kws, "kw_date": kw_date, "kw_src": kw_src,
            "topics": rows, "weights": {SIG_NAME[k]: v for k, v in W.items()}, "quarter": quarter_report(rows, today)}


if __name__ == "__main__":
    import mall_trends
    import teacher_trends_view
    tr = training_topics.build_from_files({}, "비바샘연수원", None)
    o = build(tr, teacher_trends_view.build([]), mall_trends.build([]))
    for r in o["topics"]:
        print(r["score"], r["growth"], r["stage"], r["name"], r["parts"])
    print(o["kw_src"], [k["keyword"] for k in o["keywords"]])
    print(o["quarter"])
