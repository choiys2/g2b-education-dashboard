#!/usr/bin/env python3
"""
구글시트 탭 진단(1회성): 탭 이름·행 수·머리글만 기록한다(셀 값은 저장하지 않음).
history/sheet_probe.json -> 콘텐츠DT·입찰DT·매출·SME·정산 연동 설계용.
"""
import json
import re
import urllib.parse
from datetime import date
from pathlib import Path

import own_pipeline_export as ope

OUT = Path(__file__).parent / "history" / "sheet_probe.json"


def header_of(rows):
    """처음 6줄 중 '글자 머리글'이 가장 많은 줄(숫자·날짜·긴 문장 제외, 12자 이내)."""
    def score(r):
        return sum(1 for c in r if c and len(c.strip()) <= 12 and not re.search(r"\d{3,}|@|\d{2,4}[-./]\d", c))
    best = max(range(min(6, len(rows))), key=lambda i: score(rows[i]), default=None)
    if best is None:
        return None, []
    return best + 1, [c.strip()[:12] if c and len(c.strip()) <= 12 and not re.search(r"\d{3,}|@", c) else "·" for c in rows[best]][:40]


def main():
    tok = ope._sa_token()
    meta = ope._sheets_api_get(f"https://sheets.googleapis.com/v4/spreadsheets/{ope.SHEET_ID}?fields=sheets.properties", tok)
    out = {"date": date.today().isoformat(), "tabs": []}
    for s in meta.get("sheets", []):
        p = s.get("properties", {})
        t = p.get("title", "")
        item = {"title": t, "gid": p.get("sheetId"), "rows": (p.get("gridProperties") or {}).get("rowCount")}
        # 머리글을 남기는 탭은 업무 데이터 탭으로 한정(소통·학교 명단 탭은 머리글 추정 줄에 실명이 섞일 수 있어 제외)
        if re.search(r"콘텐츠|입찰|매출|정산|운영|이수", t) and not re.search(r"소통|학교|채택|지원청", t):
            try:
                rng = urllib.parse.quote(f"'{t}'!A1:AN6", safe="")
                vals = ope._sheets_api_get(f"https://sheets.googleapis.com/v4/spreadsheets/{ope.SHEET_ID}/values/{rng}", tok).get("values", [])
                rng2 = urllib.parse.quote(f"'{t}'!A:A", safe="")
                col = ope._sheets_api_get(f"https://sheets.googleapis.com/v4/spreadsheets/{ope.SHEET_ID}/values/{rng2}", tok).get("values", [])
                hr, hd = header_of(vals)
                if hr and hr <= 2:  # 1~2행이 아닌 줄을 머리글로 고르면 데이터 행일 수 있어 남기지 않는다
                    item["header_row"], item["header"] = hr, hd
                item["filled_rows"] = len([r for r in col if r and r[0].strip()])
            except Exception as e:
                item["error"] = str(e)[:120]
        out["tabs"].append(item)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"탭 {len(out['tabs'])}개")


if __name__ == "__main__":
    main()
