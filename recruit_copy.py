#!/usr/bin/env python3
"""
모집률 조기경보(ops_insights.recruit_alerts) 중 '경보·주의' 사업의 홍보 문구 초안 - Gemini, CI에서만 호출.
- 입력: live/own_pipeline_export.json (사업명·기관·기간·목표/신청 인원만 보낸다. 소통 원문·개인정보는 보내지 않음)
- 출력: live/recruit_copy.json {사업명: {"sms": 문자 90자, "notice": 공문·게시판 안내 3~4문장, "point": 홍보 포인트}}
- 운영DT 사업명이 들어가므로 history/(공개 저장소)에 캐시하지 않는다. 하루 1회, 최대 MAX건을 한 번의 호출로.
"""
import json
import sys
from datetime import date
from pathlib import Path

import gemini_client as gc
import ops_insights

HERE = Path(__file__).parent
MAX = 6
PROMPT = """너는 교원 원격연수 기관(비바샘원격교육연수원)의 연수 모집 홍보 담당자다. 아래 사업들은 모집 기간 대비 신청률이 낮다.
교육청이 학교에 안내할 때 쓸 홍보 문구를 사업마다 써라. 과장·허위(무료·학점 등 데이터에 없는 혜택) 금지, 데이터에 없는 사실은 쓰지 마라.
반드시 아래 JSON 형식(배열 순서 = 입력 순서):
{"items": [{"sms": "학교 교원 대상 문자 1건(90자 이내, 마감일 포함)",
            "notice": "공문·게시판용 안내 3~4문장(대상·기간·신청 방법 안내 자리는 [신청 링크]로 둔다)",
            "point": "이 연수를 고를 이유 한 줄(30자 이내)"}]}
사업 목록:
"""


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/recruit_copy.json")
    try:
        recs = json.loads((HERE / "live" / "own_pipeline_export.json").read_text(encoding="utf-8")).get("records", [])
    except FileNotFoundError:
        return
    alerts = [a for a in ops_insights.recruit_alerts(recs)["items"] if a["level"] in ("경보", "주의")][:MAX]
    if not alerts or not gc.key():
        print(f"모집 홍보 문구: 대상 {len(alerts)}건 - 건너뜀")
        return
    brief = [{"사업명": a["course"], "발주기관": a["org"], "분야": a["field"], "모집기간": f"{a['start']}~{a['end']}",
              "남은일수": a["days_left"], "목표인원": a["target"], "현재신청": a["applied"]} for a in alerts]
    try:
        r = gc.generate_json(PROMPT + json.dumps(brief, ensure_ascii=False), temperature=0.5)
        items = r.get("items") if isinstance(r, dict) else r
        res = {}
        for a, it in zip(alerts, items or []):
            if isinstance(it, dict):
                res[a["course"]] = {"sms": str(it.get("sms", ""))[:140], "notice": str(it.get("notice", ""))[:600],
                                    "point": str(it.get("point", ""))[:60]}
        out.write_text(json.dumps({"date": date.today().isoformat(), "model": gc.model().split("/")[-1], "items": res},
                                  ensure_ascii=False), encoding="utf-8")
        print(f"모집 홍보 문구: {len(res)}건")
    except Exception as e:
        print(f"[경고] 모집 홍보 문구 실패: {gc.mask(e)[:200]}", file=sys.stderr)


if __name__ == "__main__":
    main()
