#!/usr/bin/env python3
"""
데이터 신선도 - 출처별 마지막 수집 시각·상태를 모아 대시보드 상단 배지와 '데이터 신선도' 표에 싣는다.
수집 주기(cadence 일)를 넘기면 '지연', 2배를 넘기면 '중단'으로 본다. combine_dashboard.py 가 build(full_live) 를 부른다.
"""
import json
import re
from datetime import date, datetime
from pathlib import Path

# (출처, 파일, 시각 키(json) 또는 jsonl 의 날짜 필드, 수집 주기(일), 연결 탭)
SOURCES = [
    ("에듀테크 레이더(뉴스 7일)", "history/edutech_radar.json", "collected_at", 1, "에듀테크 전략 브리핑"),
    ("전략 브리핑(07:00)", "strategy_briefings", "*enc", 1, "에듀테크 전략 브리핑"),
    ("조간 지면", "briefings", "*json", 1, "뉴스"),
    ("나라장터 연수 입찰 누적", "history/training_bids.jsonl", "d", 4, "나라장터 종합"),
    ("학교·교육청 수의계약", "history/edu_contracts_status.json", "date", 2, "학교단위 발주"),
    ("경쟁사 낙찰·계약", "history/competitor_contracts_status.json", "date", 2, "경쟁사"),
    ("경쟁사 강좌 카탈로그", "history/competitor_course_catalog.json", "captured_date", 2, "콘텐츠·매출"),
    ("경쟁사 몰 카탈로그", "history/competitor_mall_catalog.json", "captured_date", 3, "콘텐츠·매출"),
    ("KERIS 조달", "history/keris_procurement.json", "updated", 2, "KERIS"),
    ("지방교육재정(예산)", "history/eduinfo_status.json", "date", 3, "시장 분석"),
    ("학교알리미 시장", "history/schoolinfo_status.json", "date", 3, "B2S"),
    ("영업 파이프라인(구글시트)", "history/pipeline_status.json", "date", 2, "경영 종합"),
    ("운영 시트(입찰 탭)", "history/sheets_ops_status.json", "date", 2, "경영 종합"),
    ("NEIS 학사일정 표본", "history/neis_schedule.json", "generated", 8, "B2S"),
    ("경기데이터드림 시군", "history/gg_b2s.json", "generated", 8, "B2S"),
    ("교사단체 소식", "history/teacher_group_news.json", "generated", 8, "교사 트렌드 2027"),
    ("교사 관심 검색어(데이터랩)", "history/teacher_interest_trends.json", "buzz_date", 8, "교사 트렌드 2027"),
    ("교사 크리에이터 유튜브", "history/teacher_creator_trends.json", "youtube.captured_date", 8, "교사 트렌드 2027"),
    ("일일 지표 누적", "history/daily_stats.jsonl", "date", 1, "경영 종합"),
]
DT = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}))?")


def _pick(d, key):
    for k in key.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _stamp(path, key):
    p = Path(path)
    if key.startswith("*"):
        ext = key[1:]
        fs = sorted(p.glob(f"????-??-??.{ 'enc.json' if ext == 'enc' else 'json'}")) if p.exists() else []
        return fs[-1].name[:10] if fs else None
    if not p.exists():
        return None
    if p.suffix == ".jsonl":
        best = ""
        with p.open(encoding="utf-8") as f:
            for line in f.readlines()[-400:]:
                try:
                    v = str(json.loads(line).get(key) or "")
                except Exception:
                    continue
                best = max(best, v)
        return best or None
    try:
        v = _pick(json.loads(p.read_text(encoding="utf-8")), key)
    except Exception:
        return None
    return str(v) if v else None


def build(full_live=None, today=None):
    today = today or date.today()
    rows = []
    for name, path, key, cad, tab in SOURCES:
        s = _stamp(path, key)
        m = DT.search(s or "")
        if not m:
            rows.append({"name": name, "tab": tab, "at": None, "age": None, "cad": cad, "state": "없음"})
            continue
        d = date.fromisoformat(m.group(1))
        age = (today - d).days
        state = "정상" if age <= cad else ("지연" if age <= cad * 2 else "중단")
        rows.append({"name": name, "tab": tab, "at": m.group(1) + (" " + m.group(2) if m.group(2) else ""), "age": age, "cad": cad, "state": state})
    g = full_live or {}
    if g:
        fb, asof = g.get("_fallback"), g.get("_asof") or str(g.get("generated_at") or "")[:10]
        age = (today - date.fromisoformat(asof[:10])).days if DT.search(asof or "") else None
        state = "대체본" if fb else ("정상" if age is not None and age <= 1 else "지연")
        rows.insert(0, {"name": "나라장터 실시간 수집", "tab": "나라장터 종합", "at": asof, "age": age, "cad": 1, "state": state,
                        "note": ({"history": "수집 실패 - 누적 이력으로 대체", "cache": "수집 실패 - 마지막 정상 수집분 사용"}.get(fb, f"대체본({fb})") if fb else "")})
    bad = [r for r in rows if r["state"] != "정상"]
    return {"checked": datetime.now().strftime("%Y-%m-%d %H:%M"), "rows": rows, "n": len(rows), "ok": len(rows) - len(bad),
            "bad": [r["name"] for r in bad]}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
