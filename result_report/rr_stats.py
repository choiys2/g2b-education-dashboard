"""교육청 결과보고 — 2단계: 집계·만족도·청구금액 계산.

분석양식(이수자분석양식.xlsx)의 COUNTIF/피벗 수식과 같은 기준으로 계산해,
엑셀을 열지 않아도 한글 보고서·청구서에 같은 숫자가 들어가게 한다.
"""

from collections import Counter, defaultdict

from rr_clean import POSITION_SLOTS, SCHOOL_TYPES, credit_of

LEVELS = [("유치원", lambda c: c == "유치원"), ("초등", lambda c: c.startswith("초등")),
          ("중등", lambda c: c.startswith("중학")), ("고등", lambda c: c.startswith("고등")),
          ("특수", lambda c: c.startswith("특수")), ("교육청", lambda c: c == "교육청"),
          ("기타", lambda c: c == "기타")]

SURVEY_ITEMS = [("내용 전문성", "강연자는 연수 주제에 대한 전문성을 확보하고 있습니까?"),
                ("학습 난이도", "연수의 전반적인 난이도는 적정했나요?"),
                ("현장 적용성", "학교 현장에서 적용이 가능한 연수 주제였습니까?"),
                ("학습의 편의성", "학습하기 편안한 원격연수 환경을 제공했습니까?"),
                ("CS 운영", "운영상 친절한 서비스를 받았다고 생각하십니까?"),
                ("추천 지수", "동료 교사에게 추천하고 싶은 강좌였습니까?")]


def _cnt(rows):
    done = sum(1 for r in rows if r["점수"] == "이수")
    return {"참여": len(rows), "이수": done, "미이수": len(rows) - done,
            "이수율": done / len(rows) if rows else 0.0}


def summarize(rows):
    s = {"총": _cnt(rows)}
    s["학교급"] = {k: _cnt([r for r in rows if f(r["구분"])]) for k, f in LEVELS}
    s["학교구분"] = {k: _cnt([r for r in rows if r["학교구분"] == k]) for k in SCHOOL_TYPES}
    s["학점"] = {f"{c}학점": _cnt([r for r in rows if credit_of(r["연수시간"]) == c]) for c in (1, 2)}
    s["직위"] = {k: _cnt([r for r in rows if r["직위"] == k]) for k in POSITION_SLOTS}

    by_course = defaultdict(list)
    for r in rows:
        by_course[r["과정명"]].append(r)
    courses = []
    for name, rs in by_course.items():
        c = _cnt(rs)
        c.update(과정명=name, 학점=credit_of(rs[0]["연수시간"]), 연수시간=rs[0]["연수시간"])
        courses.append(c)
    # 분석양식 피벗과 같은 순서: 이수 많은 순 → 참여 많은 순 → 과정명
    courses.sort(key=lambda c: (-c["이수"], -c["참여"], c["과정명"]))
    s["과정"] = courses

    by_school = defaultdict(list)
    for r in rows:
        by_school[(r["구분"], r["학교명"])].append(r)
    schools = []
    for (lvl, name), rs in by_school.items():
        c = _cnt(rs)
        c.update(학교명=name, 구분=lvl)
        schools.append(c)
    schools.sort(key=lambda c: (-c["이수"], -c["참여"], c["학교명"]))
    s["학교"] = schools
    top = {}
    for c in schools:
        top.setdefault(c["구분"], c)
    s["학교급별_최다학교"] = top

    people = {(r["성명"], r["생년월일"]) for r in rows}
    done_people = {(r["성명"], r["생년월일"]) for r in rows if r["점수"] == "이수"}
    per_person = Counter((r["성명"], r["생년월일"]) for r in rows)
    s["인원"] = {"신청인원": len(people), "이수인원": len(done_people),
                 "1인당과정수": len(rows) / len(people) if people else 0,
                 "과정수분포": dict(sorted(Counter(per_person.values()).items()))}

    s["기수"] = sorted({r["기수"] for r in rows})
    s["연수기간"] = sorted({r["연수기간"] for r in rows})
    s["시도"] = sorted({r["시도교육청"] for r in rows})
    return s


def survey(counts, respondents):
    """counts: {항목: [매우그렇다, 그렇다, 보통, 그렇지않다, 매우그렇지않다]}.
    추천 지수는 보기 3개 설문이라 1·2·3번 응답을 매우그렇다·그렇다·보통 칸에 넣는다(인계서 규칙)."""
    items = []
    for name, q in SURVEY_ITEMS:
        c = [int(x or 0) for x in counts.get(name, [0] * 5)]
        n = respondents or sum(c) or 1
        score = (5 * c[0] + 4 * c[1] + 3 * c[2] + 2 * c[3] + c[4]) / n
        items.append({"구분": name, "문항": q, "응답": c, "비율": [x / n for x in c],
                      "점수": score, "백분율": score / 5, "만족비율": (c[0] + c[1]) / n})
    k = len(items)
    total = {"점수": sum(i["점수"] for i in items) / k,
             "백분율": sum(i["백분율"] for i in items) / k,
             "만족비율": sum(i["만족비율"] for i in items) / k,
             "비율": [sum(i["비율"][j] for i in items) / k for j in range(5)]}
    return {"조사인원": respondents, "항목": items, "종합": total}


def invoice(courses, unit_price, budget):
    """courses: summarize()['과정']. unit_price: {1: 30000, 2: 50000}. budget: 계약(초기 견적) 금액.
    이수 인원 × 학점별 단가로 산정하고, 예산을 넘는 금액은 '교육기부'로 차감한다."""
    lines = []
    for c in sorted(courses, key=lambda c: (c["학점"], c["과정명"])):
        if c["이수"] <= 0:
            continue
        price = int(unit_price[c["학점"]])
        lines.append({"학점": c["학점"], "과정명": c["과정명"], "인원": c["이수"],
                      "단가": price, "금액": c["이수"] * price})
    gross = sum(l["금액"] for l in lines)
    donation = min(0, int(budget) - gross) if budget else 0
    return {"내역": lines, "산정금액": gross, "교육기부": donation, "청구금액": gross + donation,
            "총이수": sum(l["인원"] for l in lines), "예산": int(budget or 0)}
