#!/usr/bin/env python3
"""
'기업·대학 트렌드 2027' 탭 데이터 (combine_dashboard.py 에서 호출)

  공개: static_data/industry_trend_2027.json(시장 변화·RISE 개요·예산·대학 후보·확인할 것·업데이트 이력)
        history/keris_procurement.json(AI 교원연수 위탁 낙찰 흐름), briefings/*.json(RISE·대학·기업 AI 교육 기사)
  비공개: static_data/industry_trend_private.enc.json(업체별 현황·협력 방향·결론) - STRATEGY_KEY 복호화(로그인 뒤 화면)
"""
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).parent
NEWS_RE = re.compile(r"RISE|라이즈 ?사업|지역혁신중심|네패스|팀모노리스|산학협력|AI 재도약|첨단분야 인재|반도체 인재|AI 인재양성|글로컬대학|대학 AI|AI 교육사업")
SKIP_SEC = re.compile(r"증시|시황|경제|금융|해외|환율")


def _j(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def _plain(t):
    return re.sub(r"<[^>]+>", "", t or "").strip()


def build(key=None):
    D = _j("static_data/industry_trend_2027.json")
    if not D:
        return None
    K = _j("history/keris_procurement.json", {}) or {}
    awards = []
    for k, a in (K.get("awards") or {}).items():
        t = a.get("t") or ""
        if re.search(r"AI|인공지능|디지털", t) and re.search(r"연수|교원|교사", t) and a.get("winner"):
            parts = (K.get("participants") or {}).get(k, [])
            awards.append({"d": a.get("d"), "t": t, "winner": a.get("winner"), "amt": a.get("amt"), "n": a.get("n") or len(parts),
                           "bidders": [p.get("corp") for p in parts][:10],
                           "u": f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={k.split('-')[0]}&bidPbancOrd={k.split('-')[-1]}"})
    awards.sort(key=lambda x: x["d"] or "", reverse=True)
    news = []
    for f in sorted((HERE / "briefings").glob("*.json"), reverse=True):
        try:
            b = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        imp = [(_plain(i.get("news")), _plain(i.get("impact"))) for i in b.get("implications") or []]
        for sec in b.get("sections") or []:
            if SKIP_SEC.search(sec.get("name") or ""):
                continue
            for it in sec.get("items") or []:
                txt = _plain(it.get("title")) + " " + _plain(it.get("body"))
                if NEWS_RE.search(txt):
                    impact = next((v for k, v in imp if k and k[:8] in txt), "")
                    news.append({"d": b.get("date") or f.stem, "t": _plain(it.get("title")), "b": _plain(it.get("body"))[:200],
                                 "impact": impact[:220], "u": f"../news/{b.get('date') or f.stem}.html"})
        if len(news) >= 40:
            break
    out = {**D, "keris_ai": awards[:20], "news": news}
    key = key or os.environ.get("STRATEGY_KEY", "")
    ep = HERE / "static_data/industry_trend_private.enc.json"
    if key and ep.exists():
        try:
            import strategy_crypto
            out["private"] = strategy_crypto.decrypt(json.loads(ep.read_text(encoding="utf-8")), key)
        except Exception as e:
            print(f"기업·대학 트렌드 비공개 메모: 복호화 실패({type(e).__name__})")
    return out


if __name__ == "__main__":
    d = build()
    print(len(d["keris_ai"]), [(a["d"], a["winner"], a["amt"]) for a in d["keris_ai"]][:8])
    print(len(d["news"]), [n["t"][:40] for n in d["news"]][:10])
