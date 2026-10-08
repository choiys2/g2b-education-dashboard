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
        if re.search(r"콘텐츠|입찰|매출|정산|SME|강사|만족|결과|계약|제작|개발|이수|운영|B2C|학교", t, re.I):
            try:
                rng = urllib.parse.quote(f"'{t}'!A1:AN6", safe="")
                vals = ope._sheets_api_get(f"https://sheets.googleapis.com/v4/spreadsheets/{ope.SHEET_ID}/values/{rng}", tok).get("values", [])
                rng2 = urllib.parse.quote(f"'{t}'!A:A", safe="")
                col = ope._sheets_api_get(f"https://sheets.googleapis.com/v4/spreadsheets/{ope.SHEET_ID}/values/{rng2}", tok).get("values", [])
                item["header_row"], item["header"] = header_of(vals)
                item["filled_rows"] = len([r for r in col if r and r[0].strip()])
            except Exception as e:
                item["error"] = str(e)[:120]
        out["tabs"].append(item)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"탭 {len(out['tabs'])}개")


if __name__ == "__main__":
    main()
