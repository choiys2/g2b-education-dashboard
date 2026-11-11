#!/usr/bin/env python3
"""
C. 교육청 예산 캘린더 - 시도별 '본예산 의결 → 추경 → 연수 발주' 흐름과 제안 시점 (API 호출 없음)

  - 예산 소식: 조간 지면(briefings/*.json, 공개 기사 제목) + 에듀테크 레이더(7일 뉴스)에서
    시도명 + 예산/추경/미편성/편성 이 함께 나온 기사 제목과 금액을 뽑는다(기사에 있는 수치만)
  - 발주 시기: 나라장터 연수 입찰 누적(history/training_bids.jsonl, 12개월) 시도별 월 분포 → 발주가 몰리는 달
  - 일반 일정(지방교육재정 관행): 본예산 시도의회 의결 12월 중순 · 1회 추경 편성 3~4월·의결 5~6월 · 2회 추경 9~10월
    → 시도별 공식 일정이 아니라 '보통 그렇다'는 기준선으로 표시한다
  build() -> dict  (combine_dashboard.py 가 호출)
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
ALIAS = [("전남광주", "전남"), ("충청북도", "충북"), ("충청남도", "충남"), ("전라북도", "전북"), ("전북특별자치도", "전북"), ("전라남도", "전남"),
         ("경상북도", "경북"), ("경상남도", "경남"), ("강원특별자치도", "강원"), ("제주특별자치도", "제주"), ("경기도", "경기"), ("세종시", "세종")]
SIDO_RE = re.compile("|".join([a for a, _ in ALIAS] + SIDO))
BUDGET_RE = re.compile(r"예산|추경|미편성|본예산|교부금|세출|편성")
EDU_RE = re.compile(r"교육청|교육감|교육|학교")
AMT_RE = re.compile(r"\d[\d,.]*\s?조(?:\s?[\d,천]+\s?억)?(?:\s?원)?|\d[\d,]*(?:천[\d,]*)?\s?억(?:\s?원)?")  # '7천550억'·'2조4,098억' 포함
KIND = [("미편성", r"미편성|미반영|부족|삭감|감액|긴축"), ("증액", r"증액|늘|\+|증가|확대|↑"), ("편성", r"편성|예산안|본예산")]
# 일반 일정(월): 시도의회 본예산 의결, 1회 추경, 2회 추경
CYCLE = [{"m": 11, "label": "본예산 시의회 심의", "kind": "의회"}, {"m": 12, "label": "본예산 의결", "kind": "의회"},
         {"m": 3, "label": "1회 추경 편성", "kind": "추경"}, {"m": 5, "label": "1회 추경 의결", "kind": "추경"},
         {"m": 6, "label": "1회 추경 의결", "kind": "추경"}, {"m": 9, "label": "2회 추경 편성", "kind": "추경"}, {"m": 10, "label": "2회 추경 의결", "kind": "추경"}]


def _sido(text):
    for m in SIDO_RE.finditer(text or ""):
        w = m.group(0)
        return dict(ALIAS).get(w, w)
    return ""


def _news():
    """(date, title, url, src) 목록 - 공개 기사 제목만."""
    out = []
    for p in sorted((HERE / "briefings").glob("*.json"))[-90:]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        day = d.get("date") or p.stem
        L = d.get("lead") or {}
        out.append((day, L.get("headline", ""), "", "조간"))
        for s in d.get("sections") or []:
            for it in s.get("items") or []:
                out.append((day, it.get("title", ""), it.get("url", ""), "조간"))
    try:
        r = json.loads((HERE / "history" / "edutech_radar.json").read_text(encoding="utf-8"))
        for it in r.get("items") or []:
            out.append(((it.get("orig_date") or it.get("date") or "")[:10], it.get("title", ""), it.get("orig") or it.get("url", ""), it.get("source", "")))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return out


def _peaks():
    today = date.today()
    since = (today - timedelta(days=365)).isoformat()
    by = defaultdict(Counter)
    p = HERE / "history" / "training_bids.jsonl"
    if not p.exists():
        return {}
    import training_topics as tt
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        d = r.get("d") or ""
        if d < since or not tt.is_training_bid(r.get("t"), r.get("o")):
            continue
        by[r.get("r") or "전국"][int(d[5:7])] += 1
    return by


def build():
    news = _news()
    seen, items = set(), defaultdict(list)
    for d, t, u, src in news:
        if not t or not BUDGET_RE.search(t) or not EDU_RE.search(t):
            continue
        sd = _sido(t)
        if not sd:
            continue
        key = re.sub(r"\W", "", t)[:40]
        if key in seen:
            continue
        seen.add(key)
        kind = next((k for k, rx in KIND if re.search(rx, t)), "기타")
        items[sd].append({"d": d, "t": t, "u": u if (u or "").startswith("https://") else "", "src": src,
                          "amt": [a.strip() for a in AMT_RE.findall(t)][:3], "kind": kind})
    peaks = _peaks()
    nat = peaks.get("전국", Counter())
    rows = []
    for sd in SIDO:
        c = peaks.get(sd, Counter())
        months = [c.get(m, 0) for m in range(1, 13)]
        tot = sum(months)
        top = [m for m, _ in sorted(((m, v) for m, v in enumerate(months, 1) if v), key=lambda x: -x[1])[:3]]
        N = sorted(items.get(sd, []), key=lambda x: x["d"], reverse=True)[:6]
        short = any(x["kind"] == "미편성" for x in N)
        # 제안 시점: 발주가 가장 많은 달의 2~3개월 전(없으면 전국 3~5월 기준 → 1~2월), 미편성 지역은 추경 편성(3월) 전
        pk = top[0] if top else 4
        start = (pk - 3 - 1) % 12 + 1
        end = (pk - 2 - 1) % 12 + 1
        advice = (f"추경 대기형 — 미편성 사업은 1회 추경(3월 편성) 전 1~2월에 제안" if short
                  else f"발주 집중 {pk}월 → {start}~{end}월에 제안서·과정 준비")
        rows.append({"sido": sd, "months": months, "n": tot, "peak": top, "news": N, "short": short,
                     "advice": advice, "propose": [1, 2] if short else [start, end]})
    return {"generated": date.today().isoformat(), "cycle": CYCLE, "national_months": [nat.get(m, 0) for m in range(1, 13)],
            "rows": rows, "n_news": sum(len(r["news"]) for r in rows),
            "note": "예산 소식은 기사 제목에 나온 수치만 씁니다. 의회·추경 일정은 지방교육재정 일반 관행(시도별 공식 일정 아님)."}


if __name__ == "__main__":
    b = build()
    for r in b["rows"]:
        print(r["sido"], r["n"], r["peak"], r["short"], r["advice"], [(x["d"], x["t"][:40], x["amt"]) for x in r["news"][:2]])
