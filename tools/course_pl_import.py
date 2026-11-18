#!/usr/bin/env python3
"""
과정별 손익 엑셀(비바샘 과정별 손익 *.xlsx) → 비공개 저장소 content_pl/course_pl.json  (2026-11-18)

  수동 실행 도구: python tools/course_pl_import.py <엑셀> <비공개저장소>/content_pl/course_pl.json --asof 2025-12
  - 엑셀·결과 JSON은 공개 저장소에 두지 않는다(회사 내부 재무). 결과는 비공개 저장소에만 쓴다.
  - 시트: '2025년 12월 누적 기준(…)'(과정별 누적 매출·외주비·손익), '매출'(월별), '유료판매수'(유료 누적 판매)
  필요: openpyxl
"""
import argparse
import json
import re
import sys

import openpyxl


def num(v):
    return float(v) if isinstance(v, (int, float)) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("out")
    ap.add_argument("--asof", default="2025-12")
    a = ap.parse_args()
    wb = openpyxl.load_workbook(a.xlsx, data_only=True, read_only=True)
    main_ws = next(ws for ws in wb.worksheets if "누적 기준(월별콘텐츠" in ws.title and not ws.title.startswith("2018"))
    courses, seen = [], set()
    for r in list(main_ws.iter_rows(values_only=True))[5:]:
        name = (r[3] or "").strip() if isinstance(r[3], str) else ""
        cr = (r[1] or "").strip() if isinstance(r[1], str) else ""
        if cr == "합계":  # 합계 행 아래는 별도 표(순위 차트 등) — 여기서 멈춘다
            break
        if not name:
            continue
        rev, prod, rv, fee, ext, full = num(r[5]), num(r[6]) or 0, num(r[7]) or 0, num(r[8]) or 0, num(r[9]) or 0, num(r[13])
        if rev is None:
            continue
        key = (name, cr)
        if key in seen:
            continue
        seen.add(key)
        ty = (r[2] or "").strip().upper().replace("CP", "CP") if isinstance(r[2], str) else ""
        ty = {"자체": "자체", "제휴": "제휴", "CP": "CP", "자체+제휴": "자체+제휴"}.get(ty, ty or "-")
        p = str(r[4] or "").strip()
        courses.append({"n": name, "cr": cr or "기타", "ty": ty, "pass": p if re.match(r"^\d{2}\.\d{2}$", p) else "",
                        "rev": round(rev), "prod": round(prod), "review": round(rv), "fee": round(fee), "ext": round(ext),
                        "cm": round(rev - ext), "pl": round(full) if full is not None else None})
    # 월별 매출(연도 표시는 엑셀 머리글을 그대로 따른다)
    rows = list(wb["매출"].iter_rows(values_only=True))
    head, marks = rows[1], {i: v for i, v in enumerate(rows[0]) if isinstance(v, str) and re.search(r"\d{2}", v)}
    cols, year = [], None
    for i, hname in enumerate(head):
        if i in marks:
            m = re.search(r"(\d{2,4})", marks[i]).group(1)
            year = int(m) if len(m) == 4 else 2000 + int(m)
        if year and isinstance(hname, str) and re.fullmatch(r"0?\d{1,2}월", hname.strip()):
            cols.append((i, f"{year}-{int(hname.strip()[:-1]):02d}"))
    monthly, per = {}, {}
    for r in rows[2:]:
        nm = (r[0] or "").strip() if isinstance(r[0], str) else ""
        if not nm:
            continue
        for i, ym in cols:
            v = num(r[i]) if i < len(r) else None
            if v:
                monthly[ym] = monthly.get(ym, 0) + v
                per.setdefault(nm, {})[ym] = per.get(nm, {}).get(ym, 0) + v
    yms = [ym for _, ym in cols]
    last12, prev12 = yms[-12:], yms[-24:-12]
    for c in courses:
        m = per.get(c["n"], {})
        c["r12"] = round(sum(m.get(x, 0) for x in last12))
        c["p12"] = round(sum(m.get(x, 0) for x in prev12))
    # 유료 누적 판매 수
    try:
        pr = list(wb["유료판매수"].iter_rows(values_only=True))
        paid = {str(r[3]).strip(): r[13] for r in pr[3:] if r[3] and isinstance(r[13], (int, float))}
        for c in courses:
            if c["n"] in paid:
                c["paid"] = int(paid[c["n"]])
    except Exception:  # noqa: BLE001
        pass
    out = {"as_of": a.asof, "note": "참고 데이터 — 과정별 손익 자료 기준. 이후 갱신본으로 다시 반영 예정.",
           "months": [{"ym": ym, "v": round(monthly.get(ym, 0))} for ym in yms],
           "window": {"last12": [last12[0], last12[-1]] if last12 else None, "prev12": [prev12[0], prev12[-1]] if prev12 else None},
           "courses": courses}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"과정 {len(courses)}개 · 월 {len(yms)}개({yms[0] if yms else '-'}~{yms[-1] if yms else '-'}) · 누적 매출 {sum(c['rev'] for c in courses) / 1e8:.2f}억", file=sys.stderr)


if __name__ == "__main__":
    main()
