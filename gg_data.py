#!/usr/bin/env python3
"""
경기데이터드림 -> history/gg_b2s.json (주 1회, gg_data.yml) - B2S '경기 31개 시군' 패널용.

  - 학교 현황(학생수)(초,중,고,그외)  Schoolstdntcntsecndhd : 최신 기준연도, 시군 x 학교급 학교 수·학생 수
  - 경기도_학원 및 교습소 현황         TninsttInstutM        : 시군별 학원·교습소 수, 교습과정 분류 구성
  - 나라장터 연수 입찰(최근 12개월, 이미 누적 중인 history/training_bids.jsonl) : 시군 교육지원청 발주 건수
시군 단위 집계만 저장한다(학원 대표자명·전화·개별 주소·학교 연락처는 저장하지 않음).
환경변수: GG_DATA_KEY (경기데이터드림 인증키)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

KEY = os.environ.get("GG_DATA_KEY", "")
OUT = Path("history/gg_b2s.json")
SIGUN = ["수원시", "성남시", "고양시", "용인시", "부천시", "안산시", "안양시", "남양주시", "화성시", "평택시", "의정부시",
         "시흥시", "파주시", "광명시", "김포시", "군포시", "광주시", "이천시", "양주시", "오산시", "구리시", "안성시",
         "포천시", "의왕시", "하남시", "여주시", "양평군", "동두천시", "과천시", "가평군", "연천군"]
LV = {"초등학교": "초", "중학교": "중", "고등학교": "고"}


def fetch_all(svc, extra=None, size=200, cap=250):
    rows = []
    for page in range(1, cap + 1):
        q = {"KEY": KEY, "Type": "json", "pIndex": page, "pSize": size, **(extra or {})}
        url = f"https://openapi.gg.go.kr/{svc}?" + urllib.parse.urlencode(q)
        data = None
        for i in range(3):
            try:
                with urllib.request.urlopen(url, timeout=90) as r:
                    data = json.loads(r.read().decode("utf-8"))
                break
            except Exception as e:
                if i == 2:
                    print(f"  [경고] {svc} p{page} 실패: {str(e)[:100]}", file=sys.stderr)
                time.sleep(3 * (i + 1))
        body = (data or {}).get(svc)
        if not body or len(body) < 2:
            break
        got = body[1].get("row", [])
        rows += got
        total = next((h.get("list_total_count") for h in body[0]["head"] if "list_total_count" in h), 0)
        if len(rows) >= total or len(got) < size:
            break
        time.sleep(0.2)
    print(f"  {svc}: {len(rows)}행 / {page}쪽")
    return rows


def _i(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def main():
    if not KEY:
        print("GG_DATA_KEY 없음 - 건너뜀")
        return 0
    agg = {s: {"sigun": s, "schools": Counter(), "students": Counter(), "academy": 0, "tutoring": 0, "courses": Counter(), "bids": 0}
           for s in SIGUN}

    # 1) 학교·학생 수(최신 연도만)
    st = fetch_all("Schoolstdntcntsecndhd")
    years = sorted({str(r.get("STD_YY")) for r in st if r.get("STD_YY")})
    yy = years[-1] if years else ""
    for r in st:
        if str(r.get("STD_YY")) != yy or r.get("EXCLSN_YN") == "Y":
            continue
        s, lv = r.get("SIGUN_NM"), LV.get(r.get("SCHOOL_RK_NM"))
        if s in agg and lv:
            agg[s]["schools"][lv] += 1
            agg[s]["students"][lv] += _i(r.get("SUM_MATR"))
    print(f"학생수: {len(st)}행 · 기준연도 {yy}")

    # 2) 학원·교습소
    ac = fetch_all("TninsttInstutM")
    kinds = Counter()
    for r in ac:
        s = r.get("SIGUN_NM")
        if s not in agg:
            continue
        kind = (r.get("INDUTYPE_DIV_NM") or "").strip()
        kinds[kind] += 1
        if "교습" in kind:
            agg[s]["tutoring"] += 1
        else:
            agg[s]["academy"] += 1
        agg[s]["courses"][(r.get("CRSE_CLASS_NM") or "기타").strip() or "기타"] += 1
    print(f"학원·교습소: {len(ac)}행 · 구분 {dict(kinds.most_common(5))}")

    # 3) 나라장터 교원 연수 입찰(최근 12개월) - 시군 교육지원청 발주
    y1 = (date.today() - timedelta(days=365)).isoformat()
    p = Path("history/training_bids.jsonl")
    if p.exists():
        seen = set()
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            b = json.loads(line)
            no = (b.get("k") or "").rsplit("-", 1)[0]
            if (b.get("d") or "") < y1 or no in seen or b.get("r") != "경기":
                continue
            seen.add(no)
            org = b.get("o") or ""
            for s in SIGUN:
                stem = s[:-1]
                if stem in org and ("교육지원청" in org or "교육청" in org):
                    agg[s]["bids"] += 1
                    break

    rows = []
    for s, a in agg.items():
        stu = sum(a["students"].values())
        n_ac = a["academy"] + a["tutoring"]
        rows.append({"sigun": s, "schools": dict(a["schools"]), "n_schools": sum(a["schools"].values()),
                     "students": dict(a["students"]), "n_students": stu, "academy": a["academy"], "tutoring": a["tutoring"],
                     "per1k": round(n_ac / stu * 1000, 1) if stu else None,
                     "courses": a["courses"].most_common(4), "bids": a["bids"]})
    if not any(r["n_students"] for r in rows) and not any(r["academy"] for r in rows):
        print("수집 결과 없음 - 기존 파일 유지")
        return 0
    rows.sort(key=lambda r: -r["n_students"])
    tot_c = Counter()
    for a in agg.values():
        tot_c.update(a["courses"])
    out = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "student_year": yy, "rows": rows,
           "totals": {"schools": sum(r["n_schools"] for r in rows), "students": sum(r["n_students"] for r in rows),
                      "academy": sum(r["academy"] for r in rows), "tutoring": sum(r["tutoring"] for r in rows),
                      "courses": tot_c.most_common(8), "bids": sum(r["bids"] for r in rows)},
           "source": "경기데이터드림(학교 현황(학생수), 경기도_학원 및 교습소 현황) · 나라장터 연수 입찰 12개월"}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    t = out["totals"]
    print(f"저장: {OUT} · 학교 {t['schools']} · 학생 {t['students']:,} · 학원 {t['academy']:,} · 교습소 {t['tutoring']:,} · 연수 입찰 {t['bids']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
