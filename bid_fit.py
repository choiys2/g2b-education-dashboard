#!/usr/bin/env python3
"""
입찰 참가 가능 여부(Go/No-Go) 판정 - 제안요청서 AI 분석 결과(rfp_analysis.py)의 참가자격·평가방식을
자사 프로필(static_data/own_profile.json)과 대조한다. 추가 API 호출 없이 규칙으로만 판정.

판정: 불가(자격 미충족 확실) / 확인 필요(미검증 프로필 항목에 걸림·문서에 자격 없음) / 가능
승부처: 기술(협상에 의한 계약·기술 비중 높음) / 가격(적격자 중 최저가) / 미상
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
REGIONS = {"서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천", "광주": "광주", "대전": "대전", "울산": "울산",
           "세종": "세종", "경기": "경기", "강원": "강원", "충청북도": "충북", "충북": "충북", "충청남도": "충남", "충남": "충남",
           "전북": "전북", "전라북도": "전북", "전남": "전남", "전라남도": "전남", "경북": "경북", "경상북도": "경북",
           "경남": "경남", "경상남도": "경남", "제주": "제주", "전남광주": "전남광주"}
REGION_LIMIT = re.compile(r"(본점|주된\s?영업소|소재지|소재|주사무소)")
SMALL = re.compile(r"소기업|소상공인")
SME = re.compile(r"중소기업(확인서|자)|중소기업자간")
CODE = re.compile(r"[\(（]\s*(?:업종코드\s*)?(\d{4})\s*[\)）]")
TRAVEL = {"1261", "1262", "1263", "1264"}  # 종합·국외·국내여행업


def load_profile():
    return json.loads((HERE / "static_data" / "own_profile.json").read_text(encoding="utf-8"))


def judge(ai, profile=None):
    p = profile or load_profile()
    quals = [q for q in (ai.get("qualifications") or []) if q]
    text = " ".join(quals)
    hard, check, ok = [], [], []

    # 1) 지역 제한: "OO 소재 업체", "본점 소재지가 OO" 등
    if REGION_LIMIT.search(text):
        named = {v for k, v in REGIONS.items() if k in text}
        if "전남광주" in named:
            named |= {"전남", "광주"}
        named.discard("전남광주")
        hq = p["hq_region"]["value"]
        if named and hq not in named:
            (hard if p["hq_region"]["verified"] else check).append(f"지역 제한({'·'.join(sorted(named))}) - 본사 {hq}")
        elif named:
            ok.append(f"지역 제한 충족({hq})")

    # 2) 기업 규모 제한
    size, sv = p["company_size"]["value"], p["company_size"]["verified"]
    if SMALL.search(text) and size != "소기업":
        (hard if sv else check).append(f"소기업·소상공인 제한 - 자사 {size}{'' if sv else '(추정)'}")
    elif SME.search(text) and size not in ("중소기업", "소기업"):
        (hard if sv else check).append(f"중소기업 제한 - 자사 {size}{'' if sv else '(추정)'}")

    # 3) 업종(경쟁입찰참가자격) 코드: 자격 항목 하나 안에 나열된 코드는 '또는', 항목끼리는 '그리고'로 본다
    own_codes = p["industry_codes"]["value"]
    for q in quals:
        codes = set(CODE.findall(q))
        if not codes:
            continue
        if codes & set(own_codes):
            ok.append("업종 등록 충족(" + ",".join(f"{c} {own_codes[c]}" for c in sorted(codes & set(own_codes))) + ")")
        elif codes <= TRAVEL:
            hard.append("여행업 등록 필요(연수 아닌 여행 상품)")
        else:
            (hard if p["industry_codes"]["verified"] else check).append(f"업종 코드 {','.join(sorted(codes))} 등록 확인")
    if re.search(r"직접생산", text):
        check.append("직접생산확인증명서 요구 - 보유 품목 확인")
    if not quals:
        check.append("문서에서 참가자격을 찾지 못함 - 공고문 확인")

    verdict = "불가" if hard else ("확인 필요" if check else "가능")
    ev = ai.get("evaluation") or ""
    if re.search(r"협상", ev) or re.search(r"기술\D{0,6}(9\d|8\d)", ev):
        play = "기술"
    elif re.search(r"최저가|적격", ev):
        play = "가격"
    else:
        play = "미상"
    return {"verdict": verdict, "reasons": hard + check, "ok": ok, "play": play}


if __name__ == "__main__":
    import sys
    for line in open(sys.argv[1] if len(sys.argv) > 1 else HERE / "history" / "rfp_analysis.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r.get("ai"):
            print(judge(r["ai"]), r["t"][:40])
