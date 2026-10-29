#!/usr/bin/env python3
"""
교사 관심사 수집(주 1회, mall_catalog.yml) - 연수 주제 13개 기준 검색·쇼핑·커뮤니티 신호.

  - 네이버 데이터랩 검색어 트렌드(NAVER_CLIENT_ID/SECRET): 주제별 대표 검색어 묶음의 52주 주간 검색 지수.
    요청마다 기준 묶음('교사')을 함께 넣어 기준=100 으로 환산 -> 요청이 달라도 주제끼리 비교 가능.
    연령은 25~54세(교사 연령대)로 거른다(학부모 검색도 섞일 수 있음).
  - 네이버 쇼핑인사이트: 교사몰 상품군과 겹치는 쇼핑 키워드의 52주 클릭 추이.
  - 네이버 블로그·카페 검색, 카카오(다음) 블로그·카페 검색(KAKAO_REST_KEY): 주제 검색어의 누적 글 수.
    지난주 누적과의 차이 = 주간 새 글 수(첫 주는 기준선만 저장).
키가 없는 출처는 건너뛰고 기존 값을 유지한다. 공개 집계치와 글 제목만 저장한다(작성자·연락처 없음).
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

OUT = Path("history/teacher_interest_trends.json")
ANCHOR = {"groupName": "기준", "keywords": ["교사", "선생님"]}
AGES = ["4", "5", "6", "7", "8", "9"]  # 25~54세
# 연수 주제(training_topics.TOPICS id) -> 교사가 실제로 검색할 법한 대표어(데이터랩 묶음, 첫 단어는 블로그·카페 검색어)
TOPIC_KEYWORDS = {
    "ai": ["AI 수업", "에듀테크 수업", "AI 교육 연수", "디지털 교과서", "생성형 AI 수업"],
    "credit": ["고교학점제", "진로 수업", "학업설계", "최소성취수준"],
    "rights": ["교권 보호", "교육활동 침해", "교권 침해", "교사 민원"],
    "care": ["학교폭력 예방", "생활지도", "사회정서학습", "회복적 생활교육", "학생 상담"],
    "basic": ["기초학력", "문해력 수업", "한글 지도", "느린 학습자 지도"],
    "lesson": ["수업 나눔", "과정중심평가", "서논술형 평가", "프로젝트 수업", "질문 수업"],
    "neulbom": ["늘봄학교", "방과후 프로그램", "늘봄 프로그램"],
    "inclusive": ["통합교육", "다문화 학생", "특수교육", "경계선 지능"],
    "safety": ["학교 안전교육", "성교육 수업", "응급처치 교육"],
    "citizen": ["생태전환교육", "미디어 리터러시", "민주시민교육", "기후 수업"],
    "leader": ["학급경영", "신규교사", "교사 연수", "교사 성장"],
    "subject": ["수학 수업", "과학 실험 수업", "영어 수업 활동", "국어 수업"],
    "parent": ["학부모 상담", "학부모 소통", "학부모 민원"],
}
# 쇼핑인사이트: (분야 cid, 키워드 묶음) - 교사몰 상위 카테고리와 겹치는 상품군. 첫 수집 후 0인 묶음은 조정한다.
SHOP = [
    ("50000008", "학용품", ["학용품", "필기구"]),
    ("50000008", "학급 선물", ["학급 선물", "단체 선물"]),
    ("50000005", "교구", ["교구", "보드게임"]),
    ("50000005", "만들기 키트", ["만들기 키트", "DIY 키트"]),
    ("50000003", "코딩·로봇", ["코딩 로봇", "코딩 교구"]),
]


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def naver_headers():
    return {"X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"], "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"]}


def datalab(start, end):
    out, ids = {}, list(TOPIC_KEYWORDS)
    for i in range(0, len(ids), 4):  # 요청당 묶음 5개 한도 = 주제 4 + 기준 1
        chunk = ids[i:i + 4]
        body = {"startDate": start, "endDate": end, "timeUnit": "week", "ages": AGES,
                "keywordGroups": [ANCHOR] + [{"groupName": t, "keywords": TOPIC_KEYWORDS[t]} for t in chunk]}
        try:
            d = http("https://openapi.naver.com/v1/datalab/search", body, naver_headers())
        except Exception as e:
            print(f"  [데이터랩 실패] {chunk}: {e}", file=sys.stderr)
            continue
        res = {r["title"]: {p["period"]: p["ratio"] for p in r["data"]} for r in d.get("results", [])}
        base = res.get("기준", {})
        base_avg = (sum(base.values()) / len(base)) if base else 0
        for t in chunk:
            s = res.get(t, {})
            out[t] = [[k, round(v / base_avg * 100, 2) if base_avg else 0] for k, v in sorted(s.items())]
    return out


def shopping(start, end):
    out = {}
    for cid, name, kws in SHOP:
        body = {"startDate": start, "endDate": end, "timeUnit": "week", "category": cid,
                "keyword": [{"name": name, "param": kws}]}
        try:
            d = http("https://openapi.naver.com/v1/datalab/shopping/category/keywords", body, naver_headers())
            r = (d.get("results") or [{}])[0]
            out[name] = [[p["period"], p["ratio"]] for p in r.get("data", [])]
        except Exception as e:
            print(f"  [쇼핑인사이트 실패] {name}: {e}", file=sys.stderr)
    return out


def strip(s):
    return re.sub(r"<[^>]+>", "", s or "").replace("&quot;", '"').replace("&amp;", "&")[:90]


def naver_buzz():
    out = {}
    for t, kws in TOPIC_KEYWORDS.items():
        q = urllib.parse.quote(kws[0] + " 교사")
        row = {}
        for kind in ("blog", "cafearticle"):
            try:
                d = http(f"https://openapi.naver.com/v1/search/{kind}.json?query={q}&display=10&sort=date", headers=naver_headers())
                row[kind] = d.get("total", 0)
                if kind == "blog":
                    row["titles"] = [strip(i.get("title")) for i in d.get("items", [])[:5]]
            except Exception as e:
                print(f"  [네이버 검색 실패] {t}/{kind}: {e}", file=sys.stderr)
        out[t] = row
    return out


def kakao_buzz():
    out, key = {}, os.environ["KAKAO_REST_KEY"]
    for t, kws in TOPIC_KEYWORDS.items():
        q = urllib.parse.quote(kws[0] + " 교사")
        row = {}
        for kind in ("blog", "cafe"):
            try:
                d = http(f"https://dapi.kakao.com/v2/search/{kind}?query={q}&size=1", headers={"Authorization": "KakaoAK " + key})
                row[kind] = d.get("meta", {}).get("total_count", 0)
            except Exception as e:
                print(f"  [카카오 검색 실패] {t}/{kind}: {e}", file=sys.stderr)
        out[t] = row
    return out


def main():
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    out, today = dict(prev), date.today()
    end, start = (today - timedelta(days=1)).isoformat(), (today - timedelta(weeks=52)).isoformat()
    have_naver = bool(os.environ.get("NAVER_CLIENT_ID") and os.environ.get("NAVER_CLIENT_SECRET"))
    if have_naver:
        dl = datalab(start, end)
        if dl:
            out["datalab"] = {"captured_date": today.isoformat(), "topics": dl, "ages": "25~54세"}
        sh = shopping(start, end)
        if sh:
            out["shopping"] = {"captured_date": today.isoformat(), "keywords": sh}
        nb = naver_buzz()
        print(f"데이터랩 주제 {len(dl)} · 쇼핑 {len(sh)} · 네이버 글수 {len(nb)}")
    else:
        nb = {}
        print("NAVER 키 없음 - 네이버 건너뜀")
    kb = kakao_buzz() if os.environ.get("KAKAO_REST_KEY") else {}
    print(f"카카오 글수 {len(kb)}" if kb else "KAKAO_REST_KEY 없음 - 카카오 건너뜀")
    if nb or kb:
        hist = prev.get("buzz_hist", {})  # {날짜: {주제: {naver_blog,..}}} 최근 12주
        snap = {}
        for t in TOPIC_KEYWORDS:
            n, k = nb.get(t, {}), kb.get(t, {})
            snap[t] = {"naver_blog": n.get("blog"), "naver_cafe": n.get("cafearticle"), "kakao_blog": k.get("blog"), "kakao_cafe": k.get("cafe")}
        hist[today.isoformat()] = snap
        for d in sorted(hist)[:-12]:
            hist.pop(d)
        out["buzz_hist"] = hist
        out["buzz_titles"] = {t: nb[t].get("titles", []) for t in nb}
        out["buzz_date"] = today.isoformat()
    if out != prev:
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
