#!/usr/bin/env python3
"""
2026 AI 중점학교 · AI·디지털 활용 선도학교 명단(엑셀) -> 대시보드용 JSON

원본: static_data/ai_schools_2026.xlsx (각 시도교육청 누리집 공개 명단을 모으고 나이스 학교기본정보로
연락처·주소를 붙인 영업 관리용 엑셀). 같은 파일이 대시보드에서 그대로 내려받기로 제공된다.
명단이 바뀌면 엑셀만 교체하고 이 스크립트를 다시 돌려 JSON을 커밋한다(CI에는 openpyxl이 없어도 되게).

  python ai_schools_2026.py [xlsx] [out_json]

두 사업에 모두 선정된 학교(겸임)는 (시도, 학교명) 기준 1개 학교로 합친다.
영업 관리 칸(담당자·연락일·진행상태·메모)은 공개 사이트에 싣지 않는다.
"""
import json
import sys
from pathlib import Path

import openpyxl

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "static_data/ai_schools_2026.xlsx")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "static_data/ai_schools_2026.json")
SHEETS = {"AI 중점학교": "AI 중점", "AI·디지털 선도학교": "디지털 선도"}
GRADE = {"초": "초", "중": "중", "고": "고", "특수/기타": "특수"}


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True)
    schools = {}
    for sheet, prog in SHEETS.items():
        for r in wb[sheet].iter_rows(min_row=5, values_only=True):
            if not r[6]:
                continue
            key = (r[1], r[6])
            s = schools.setdefault(key, {
                "소속지역": r[1], "학교명": r[6], "학교급": GRADE.get(r[4], "특수"),
                "교육지원청": r[2] or "", "시군구": r[3] or "", "설립": r[5] or "",
                "tel": r[9] or "", "homepage": r[10] or "", "addr": r[11] or "",
                "사업": [], "ai_type": "", "dig_type": "", "class_count": None,
            })
            s["사업"].append(prog)
            if prog == "AI 중점":
                s["ai_type"] = r[7] or ""
            else:
                s["dig_type"] = r[7] or ""
            for k, v in (("교육지원청", r[2]), ("시군구", r[3]), ("설립", r[5]), ("tel", r[9]), ("homepage", r[10]), ("addr", r[11])):
                if v and not s[k]:
                    s[k] = v
    rows = []
    for s in schools.values():
        parts = []
        if "AI 중점" in s["사업"]:
            parts.append("AI 중점" + (f"({s['ai_type']})" if s["ai_type"] and s["ai_type"] != "확인필요" else ""))
        if "디지털 선도" in s["사업"]:
            parts.append("디지털 선도" + ("(연구학교)" if s["dig_type"] == "연구학교" else ""))
        s["유형"] = " · ".join(parts)
        s["겸임"] = len(s["사업"]) > 1
        rows.append(s)
    rows.sort(key=lambda s: (s["소속지역"], s["학교급"], s["학교명"]))

    # 시도별 공개 현황(교육부 지정 수 대비 확보 수, 명단 공개 여부)
    status = []
    for r in wb["시도별 현황"].iter_rows(min_row=6, max_row=22, values_only=True):
        if not r[0] or r[0] == "전국":
            continue
        status.append({"region": r[0], "ai_moe": r[1] if isinstance(r[1], int) else None, "ai_got": r[2] or 0,
                       "ai_open": r[4] == "공개", "dig_announced": r[5] if isinstance(r[5], int) else None,
                       "dig_got": r[6] or 0, "dig_open": r[7] == "공개", "note": r[9] or ""})
    out = {"source": "각 시도교육청 누리집 공개 선정 명단(2026) · 연락처: 나이스 교육정보 개방포털 학교기본정보(2026.10 조회)",
           "captured": "2026-10", "xlsx": "ai_schools_2026.xlsx", "status": status, "schools": rows}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n_ai = sum("AI 중점" in s["사업"] for s in rows)
    n_dig = sum("디지털 선도" in s["사업"] for s in rows)
    print(f"saved {OUT}: 학교 {len(rows)}교 (AI 중점 {n_ai}, 디지털 선도 {n_dig}, 겸임 {sum(s['겸임'] for s in rows)})")


if __name__ == "__main__":
    main()
