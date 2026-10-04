#!/usr/bin/env python3
"""
학교알리미(schoolinfo.go.kr) 공시정보로 AI 중점·선도학교의 교원 수·학생 수를 붙인다.

- API: https://www.schoolinfo.go.kr/openApi.do?apiKey=..&apiType=..&sidoCode=..&sggCode=..&schulKndCode=..&pbanYr=..
  (2026년 이후 발급 키는 시군구 코드 필수) 키는 GitHub Secret SCHOOLINFO_KEY.
- apiType 22 = 직위별 교원 현황, 09 = 학년별·학급별 학생수. 응답은 시군구 단위 전체 학교 목록.
- 시도·시군구 코드표(static_data/schoolinfo_regions.json)와 apiType 코드는 MIT 라이선스
  오픈소스 chrisryugj/schoolinfo-mcp 를 참고했다.
- 대상 학교(static_data/ai_schools_2026.json)가 있는 시군구만 호출한다. 결과는 live/schoolinfo_export.json,
  응답 필드 진단은 history/schoolinfo_status.json(git 추적)에 남긴다.
"""
import json
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
BASE = "https://www.schoolinfo.go.kr/openApi.do"
KIND = {"초": "02", "중": "03", "고": "04", "특수": "05"}
TYPES = {"22": "teachers", "09": "students"}
FULL = {"서울": ["서울특별시"], "부산": ["부산광역시"], "대구": ["대구광역시"], "인천": ["인천광역시"],
        "광주": ["광주광역시", "전남광주통합특별시"], "대전": ["대전광역시"], "울산": ["울산광역시"],
        "세종": ["세종특별자치시"], "경기": ["경기도"], "강원": ["강원특별자치도"], "충북": ["충청북도"],
        "충남": ["충청남도"], "전북": ["전북특별자치도"], "전남": ["전라남도", "전남광주통합특별시"],
        "경북": ["경상북도"], "경남": ["경상남도"], "제주": ["제주특별자치도"]}
SKIP_KEY = re.compile(r"CODE|_CD$|YR|YEAR|NO$|ZIP|TEL|FAX|DT$|DATE", re.I)
TOTAL_KEY = re.compile(r"SUM|TOT|TOTAL|ALL", re.I)


def call(key, api_type, sido, sgg, kind, year):
    q = {"apiKey": key, "apiType": api_type, "sidoCode": sido, "sggCode": sgg, "schulKndCode": kind}
    if year:
        q["pbanYr"] = year
    req = Request(f"{BASE}?{urlencode(q)}", headers={"User-Agent": "g2b-education-dashboard"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("resultCode") != "success":
                return None, data.get("resultMsg") or str(data)[:200]
            return data.get("list") or [], None
        except Exception as e:
            err = str(e)[:200]
            time.sleep(1 + attempt)
    return None, err


# 학교알리미 응답 확인 결과(2026-10-04 진단): 교원(22) 총원 = COL_S(남 COL_SM + 여 COL_SW), 학생(09) 총원 = COL_S_SUM
EXACT = {"22": "COL_S", "09": "COL_S_SUM"}


def total_of(row, api_type=None):
    f = EXACT.get(api_type)
    if f and str(row.get(f, "")).replace(",", "").isdigit():
        return int(str(row[f]).replace(",", "")), f
    return _guess_total(row)


def _guess_total(row):
    """행에서 합계로 보이는 숫자 필드를 쓰고, 없으면 숫자 필드 합으로 추정한다(필드명은 진단 파일로 검수)."""
    nums = {}
    for k, v in row.items():
        if SKIP_KEY.search(k):
            continue
        try:
            nums[k] = float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            pass
    tot = [v for k, v in nums.items() if TOTAL_KEY.search(k)]
    if tot:
        return int(max(tot)), "합계필드"
    return (int(sum(nums.values())), "필드합") if nums else (None, "없음")


def sgg_codes(region_full, sigungu, regions):
    sgg = regions.get(region_full, {}).get("sgg", {})
    t = (sigungu or "").strip()
    if not t:
        return []
    if t in sgg:
        kids = [c for n, c in sgg.items() if n.startswith(t + " ")]
        return [sgg[t]] + kids
    return [c for n, c in sgg.items() if n.startswith(t)]


def main():
    key = os.environ.get("SCHOOLINFO_KEY")
    status_path = HERE / "history" / "schoolinfo_status.json"
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "live/schoolinfo_export.json")
    if not key:
        print("[경고] SCHOOLINFO_KEY 없음 - 학교알리미 조회 건너뜀", file=sys.stderr)
        return
    regions = json.loads((HERE / "static_data" / "schoolinfo_regions.json").read_text(encoding="utf-8"))
    schools = json.loads((HERE / "static_data" / "ai_schools_2026.json").read_text(encoding="utf-8"))["schools"]
    year = os.environ.get("SCHOOLINFO_YEAR") or str(date.today().year)

    targets = {}  # (sidoCode, sggCode, kind) -> set(names)
    for s in schools:
        kind = KIND.get(s.get("학교급"))
        if not kind:
            continue
        for full in FULL.get(s.get("소속지역"), []):
            if full not in regions:
                continue
            for code in sgg_codes(full, s.get("시군구"), regions):
                targets.setdefault((regions[full]["code"], code, kind), set()).add(s["학교명"])
    # B2S 잠재 수요: 전국 모든 시군구×학교급(초·중·고)의 교원 수(22)도 받는다. 학생 수(09)는 선도학교 매칭 대상만.
    short = {f: k for k, fs in FULL.items() for f in fs}
    sgg_name = {}
    for full, reg in regions.items():
        names = reg.get("sgg", {})
        for nm, code in names.items():
            if any(o.startswith(nm + " ") for o in names):  # 하위 구가 있는 시(수원시 등)는 시 코드로는 자료가 없다
                continue
            key_ = (reg["code"], code)
            if key_ not in sgg_name:
                sgg_name[key_] = (short.get(full, full), nm)
    mpath = HERE / "history" / "schoolinfo_market.json"
    mprev = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    fresh = mprev.get("date", "") >= (date.today() - timedelta(days=7)).isoformat()
    if not fresh:  # 공시는 연 단위라 전국 수집은 주 1회면 충분하다
        for (sido, code) in sgg_name:
            for kind in ("02", "03", "04"):
                targets.setdefault((sido, code, kind), set())
    print(f"학교알리미: 호출 대상 {len(targets)}개 (시군구×학교급) × {len(TYPES)}항목, 공시연도 {year}")
    market = {}  # SCHUL_CODE -> {n, s, g, k, t}

    found, samples, errors, method, n_err = {}, {}, [], {}, 0
    for (sido, sgg, kind), names in sorted(targets.items()):
        for api_type, field in TYPES.items():
            if api_type == "09" and not names:
                continue
            rows, err = call(key, api_type, sido, sgg, kind, year)
            if rows is None and year:
                rows, err = call(key, api_type, sido, sgg, kind, str(int(year) - 1))  # 해당 연도 미공시면 전년도(pbanYr 필수)
            if rows is None:
                n_err += 1
                if len(errors) < 20:
                    errors.append(f"{api_type}/{sido}/{sgg}/{kind}: {err}")
                continue
            if rows and api_type not in samples:
                samples[api_type] = {k: (str(v)[:40]) for k, v in rows[0].items()}
            for r in rows:
                nm = str(r.get("SCHUL_NM") or "").strip()
                if api_type == "22" and r.get("SCHUL_CODE") and (sido, sgg) in sgg_name:
                    t, _ = total_of(r, "22")
                    if t:
                        sd, gn = sgg_name[(sido, sgg)]
                        market[r["SCHUL_CODE"]] = {"n": nm, "s": sd, "g": gn, "k": {"02": "초", "03": "중", "04": "고"}.get(kind, kind), "t": t}
                if nm in names:
                    val, how = total_of(r, api_type)
                    rec = found.setdefault(f"{sido}|{nm}", {"name": nm, "code": r.get("SCHUL_CODE")})
                    if val is not None:
                        rec[field] = max(val, rec.get(field) or 0)
                        method[api_type] = how
            time.sleep(0.08)

    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({"year": year, "schools": found}, ensure_ascii=False), encoding="utf-8")
    # B2S 잠재 수요용 전국 학교별 교원 수(b2s_demand.py 가 집계). 공시는 1년 단위라 history 에 두고,
    # 이번 수집이 이전보다 크게 적으면(일시 장애) 덮어쓰지 않는다.
    prev_n = len(mprev.get("schools", []))
    if not fresh and market and len(market) >= prev_n * 0.8:
        rows = sorted(market.values(), key=lambda r: (r["s"], r["g"], r["k"], r["n"]))
        mpath.write_text(json.dumps({"year": year, "date": date.today().isoformat(), "schools": rows},
                                    ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    status_path.write_text(json.dumps({"date": date.today().isoformat(), "matched": len(found), "market_schools": len(market),
                                       "targets": len(targets), "method": method, "errors": errors, "error_count": n_err,
                                       "sample_fields": samples}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"학교알리미: 매칭 {len(found)}교, 오류 {len(errors)}건, 산출 방식 {method}")


if __name__ == "__main__":
    main()
