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
    ("경쟁사 강좌 카탈로그", "history/competitor_course_catalog.json", "captured_date", 8, "콘텐츠·매출"),
    ("경쟁사 몰 카탈로그", "history/competitor_mall_catalog.json", "captured_date", 8, "콘텐츠·매출"),
    ("KERIS 조달", "history/keris_procurement.json", "updated", 2, "KERIS"),
    ("지방교육재정(예산)", "history/eduinfo_status.json", "date", 3, "시장 분석"),
    ("학교알리미 시장", "history/schoolinfo_status.json", "date", 3, "B2S"),
    ("영업 파이프라인(구글시트)", "history/pipeline_status.json", "date", 2, "경영 종합"),
    ("운영 시트(입찰 탭)", "history/sheets_ops_status.json", "date", 2, "경영 종합"),
    ("NEIS 학사일정 표본", "history/neis_schedule.json", "generated", 8, "B2S"),
    ("경기데이터드림 시군", "history/gg_b2s.json", "generated", 8, "B2S"),
    ("교사단체 소식", "history/teacher_group_news.json", "generated", 8, "교사 트렌드 2027"),
    ("학교단위 발주(나라장터)", "history/school_goods.json", "updated", 8, "학교단위 발주"),
    ("시도 AIEP 조달", "history/aiep_market.json", "updated", 8, "시도 AIEP"),
    ("협력 후보 스크랩", "history/partner_news.json", "generated", 8, "기업·대학 트렌드 2027"),
    ("학원·교습소 집계(나이스)", "history/academy_stats.json", "generated", 8, "관리"),
    ("교과서 선정 여론(네이버)", "history/opinion_radar.json", "generated", 8, "관리"),
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
    T = tabs(full_live)
    return {"checked": T["built"], "rows": rows, "n": len(rows), "ok": len(rows) - len(bad),
            "bad": [r["name"] for r in bad], "tabs": T["tabs"], "built": T["built"]}


# ---------------- 탭 머리 '데이터 기준' 띠 (사용자 지시 2026-11-22: 탭별 갱신 날짜·시각을 탭 위에 항상 노출) ----------------
# CP 화면에도 나가므로 이름은 일반 표현만(출처·도구·포털명 금지). 주기: d=매일, w=매주, m=수시(사람이 고칠 때)
# (표시 이름, 파일, 시각 키, 주기, jsonl 이면 최신 자료일 키)
MANUAL_ASOF = {  # 날짜 키가 없는 수동 파일: (기준일, 내용 지문). 파일을 고치면 날짜·지문을 같이 고친다.
    # 지문이 다르면(고쳤는데 날짜를 안 고침) 빌드 로그에 경고하고 기록된 날짜(더 오래된 쪽)를 그대로 쓴다 - 보수적으로 '오래됨'이 뜨게.
    # 깊은 git 이력이 있으면 git 날짜가 우선.
    "static_data/industry_trend_2027.json": ("2026-11-15", "3de025b58c"),
    "static_data/aiep_platforms.json": ("2026-11-10", "325bb6561f"),
    "static_data/region_programs.json": ("2026-11-10", "1b667fc052"),
    "static_data/textbook_adoption.enc.json": ("2026-11-10", "bd75b28dea"),
    "static_data/eco_tasks.json": ("2026-11-12", "2a9b4107e5"),
    "static_data/pool_people.enc.json": ("2026-11-09", "764497a722"),
    "static_data/branch_network.enc.json": ("2026-11-12", "d215256665"),
    "static_data/aiep_private.enc.json": ("2026-11-10", "ac0d617f9b"),
    "static_data/industry_trend_private.enc.json": ("2026-11-10", "2a7532287c"),
    "static_data/own_profile.json": ("2026-10-04", "19f8142806"),
}
LIVE = ("*live", None)
TAB_SOURCES = {
    "market": [("교육재정 통계", "history/eduinfo_status.json", "date", "d"), ("학교 시장 정보", "history/schoolinfo_status.json", "date", "d"), ("공고 집계", *LIVE, "d")],
    "strategy": [("에듀테크 뉴스", "history/edutech_radar.json", "collected_at", "d"), ("전략 브리핑", "strategy_briefings", "*enc", "d"), ("조간", "briefings", "*json", "d")],
    "keris": [("KERIS 공고·낙찰", "history/keris_procurement.json", "updated", "d")],
    "g2bfull": [("자사 강점 프로필", "static_data/own_profile.json", "", "m"), ("입찰·계약 공고", *LIVE, "d"), ("연수 공고(최근 건)", "history/training_bids.jsonl", "d", "r"),
                ("경쟁사 계약", "history/competitor_contracts_status.json", "date", "d"), ("경쟁사 낙찰(최근 건)", "history/competitor_wins.jsonl", "date", "r")],
    "neti": [("연수 이수 통계", "static_data/neti_completion.json", "as_of", "m")],
    "g2b": [("AI·에듀테크 공고", *LIVE, "d")],
    "school": [("학교 직접 발주", "history/school_goods.json", "updated", "w"), ("학교·교육청 수의계약", "history/edu_contracts_status.json", "date", "d")],
    "leading": [("AI 중점학교 명단", "static_data/ai_schools_2026.json", "captured", "m"), ("AI 중점학교 동향", "static_data/ai_school_updates.json", "checked", "m")],
    "competitor": [("경쟁사 강좌", "history/competitor_course_catalog.json", "captured_date", "w"), ("경쟁사 몰 상품", "history/competitor_mall_catalog.json", "captured_date", "w"),
                   ("경쟁사 계약", "history/competitor_contracts_status.json", "date", "d")],
    "trend2027": [("교사단체·강사 공급 정리", "static_data/teacher_groups.json", "generated", "m"), ("강사풀", "static_data/pool_people.enc.json", "", "m"),
                  ("교사 관심 검색어", "history/teacher_interest_trends.json", "buzz_date", "w"), ("교사 크리에이터", "history/teacher_creator_trends.json", "youtube.captured_date", "w"),
                  ("교사단체 소식", "history/teacher_group_news.json", "generated", "r"), ("AI 키워드 분석", "history/teacher_trend2027_ai.json", "date", "w")],
    "biz2027": [("기업·대학 동향 정리", "static_data/industry_trend_2027.json", "", "m"), ("협력 후보 소식", "history/partner_news.json", "generated", "w"),
                ("기업 협력 메모", "static_data/industry_trend_private.enc.json", "", "m")],
    "aiep": [("AIEP 조달", "history/aiep_market.json", "updated", "d"), ("시도 플랫폼 정리", "static_data/aiep_platforms.json", "", "m"), ("시도 협력 메모", "static_data/aiep_private.enc.json", "", "m")],
    "pipeline": [("영업 파이프라인", "history/pipeline_status.json", "date", "d"), ("입찰 운영 현황", "history/sheets_ops_status.json", "date", "d")],
    "branch": [("총판 현황", "static_data/branch_summary.json", "as_of", "m"), ("총판 지역망", "static_data/branch_network.enc.json", "", "m")],
    "adopt": [("교과서 채택 현황", "static_data/textbook_adoption.enc.json", "", "m")],
    "b2s": [("학교 시장 정보", "history/schoolinfo_status.json", "date", "d"), ("학사일정 표본", "history/neis_schedule.json", "generated", "w"),
            ("경기 시군 통계", "history/gg_b2s.json", "generated", "w"), ("2025 학교 구매 실적", "static_data/school_contract_national_2025.json", "generated_at", "m")],
    "content": [("과정 매출·인증", "_private/content_pl/course_pl.json", "as_of", "m"), ("경쟁사 강좌", "history/competitor_course_catalog.json", "captured_date", "w")],
    "eco": [("교사 생태계 변화", "history/teacher_ecosystem.json", "generated", "w"), ("생태계 정리표", "static_data/teacher_ecosystem.json", "as_of", "m"), ("생태계 과제", "static_data/eco_tasks.json", "", "m")],
    "search": [("검색 대상 공고", *LIVE, "d")],
    "network": [("연결 데이터", *LIVE, "d"), ("지역 연계 사업", "static_data/region_programs.json", "", "m")],
    "beta": [("경쟁사 낙찰(최근 건)", "history/competitor_wins.jsonl", "date", "r")],
}
CAD = {"d": ("매일", 2, 4), "w": ("매주", 8, 15), "m": ("수시", 90, 10 ** 6), "r": ("발생 시", 45, 10 ** 6)}  # (표시, 1단계 기준일, 2단계 기준일)
# 상태: d·w = 정상/지연/중단(수집이 멈춤), m = 정상/오래됨(사람이 고칠 때가 됨), r = 정상/새 자료 없음(수집은 되지만 새 건이 안 생김)


def _git_date(path):
    import subprocess
    try:
        if subprocess.run(["git", "rev-parse", "--is-shallow-repository"], capture_output=True, text=True, timeout=5).stdout.strip() == "true":
            return None
        return subprocess.run(["git", "log", "-1", "--format=%cs", "--", path], capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def _manual(path):
    d, fp = MANUAL_ASOF.get(path, (None, None))
    try:
        import hashlib
        if fp and hashlib.md5(Path(path).read_bytes()).hexdigest()[:10] != fp:
            print(f"[경고] 수동 자료 기준일 갱신 필요: {path} (내용이 바뀌었는데 freshness.MANUAL_ASOF 날짜가 그대로)")
    except OSError:
        pass
    return d


def tabs(full_live=None, now=None):
    """탭별 데이터 기준 시각. at = 가장 오래된 구성 자료의 기준(보수적), latest = 가장 최근 수집."""
    try:
        from zoneinfo import ZoneInfo
        now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        now = now or datetime.now()
    today = now.date()
    g = full_live or {}
    live_at = (str(g.get("_asof") or g.get("generated_at") or "")[:16]) or now.strftime("%Y-%m-%d %H:%M")
    if live_at and len(live_at) == 10 and live_at == now.strftime("%Y-%m-%d"):  # 오늘 수집분일 때만 이번 배포 시각을 붙인다
        live_at = live_at + " " + now.strftime("%H:%M")
    out = {}
    for tab, srcs in TAB_SOURCES.items():
        items = []
        for lab, path, key, cad in srcs:
            if path == "*live":
                s = live_at
            elif not key:
                s = _git_date(path) or _manual(path)
            else:
                s = _stamp(path, key)
            s = str(s or "")
            m = DT.search(s) or re.search(r"(\d{4}-\d{2})(?!-)", s)
            if not m:
                items.append({"l": lab, "at": None, "cad": CAD[cad][0], "state": "없음"})
                continue
            ds = m.group(1) if len(m.group(1)) == 10 else m.group(1) + "-01"
            age = (today - date.fromisoformat(ds)).days
            at = m.group(1) + (" " + m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else "")
            st = "정상" if age <= CAD[cad][1] else {"m": "오래됨", "r": "새 자료 없음"}.get(cad) or ("지연" if age <= CAD[cad][2] else "중단")
            if path == "*live" and g.get("_fallback"):
                st = "대체본"
            items.append({"l": lab, "at": at, "age": max(age, 0), "cad": CAD[cad][0], "state": st})
        out[tab] = items
    return {"built": now.strftime("%Y-%m-%d %H:%M"), "tabs": out}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
