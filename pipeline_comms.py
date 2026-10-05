#!/usr/bin/env python3
"""
영업 소통 내역(구글시트 '26영업소통 DT', gid 1083489926) -> 사업별 운영·진행 핵심 상황 분석.

*** 개인정보·대외비 보호 (대시보드는 공개 배포) ***
- 소통 원문은 CI 메모리에서만 쓰고 live/·history/ 어디에도 저장하지 않는다.
- 이름·연락처·이메일 열은 아예 읽지 않는다(ROLE 판별에서 제외). 본문은 Gemini에 보내기 전
  전화·이메일·'홍길동 장학사' 같은 호칭 앞 이름을 지운다.
- 공개되는 것은 사업별 소통 건수·최근 소통일·경과일과, 이름을 쓰지 말라고 지시한 AI 요약(상황·이슈·다음 액션·리스크)뿐.
- AI 요약은 지역 단위로 묶어 호출하고(무료 한도), 입력이 바뀐 지역만 다시 만든다(history/pipeline_comms_ai.json).
  python pipeline_comms.py [out_json]
"""
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
COMMS_GID = os.environ.get("PIPELINE_COMMS_GID", "1083489926")
AI_CACHE = HERE / "history" / "pipeline_comms_ai.json"
STATUS_PATH = HERE / "history" / "pipeline_comms_status.json"
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
           "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
# 열 역할: 머리글에 이 단어가 들어 있으면 그 역할. PRIVATE 에 걸리는 열은 절대 안 읽는다.
PRIVATE = re.compile(r"연락|전화|휴대|핸드폰|메일|e-?mail|성명|이름|주무관|장학사|연구사|담당자|담당\s?공무원|직위|직급", re.I)
ROLES = [
    ("date", re.compile(r"일자|날짜|일시|소통일|접촉일|연락일|date", re.I)),
    ("region", re.compile(r"^지역$|시도|권역|지역")),
    ("org", re.compile(r"기관|교육청|지원청|학교명|발주처")),
    ("course", re.compile(r"연수명|사업명|과정명|연수|사업")),
    ("kind", re.compile(r"유형|구분|방법|채널|방식")),
    ("stage", re.compile(r"단계|상태|진행")),
    ("text", re.compile(r"내용|소통|협의|메모|비고|요청|이슈|결과|특이|상황|대화")),
    ("rep", re.compile(r"영업\s?담당|영업자|작성자")),
]
PHONE = re.compile(r"\d{2,4}[-.\s)]\d{3,4}[-.\s]\d{4}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
TITLED = re.compile(r"[가-힣]{2,4}\s?(장학사|장학관|주무관|연구사|연구관|선생님|교사|과장|팀장|사무관|부장|교감|교장|원장|국장|님)")


def scrub(t):
    t = PHONE.sub("[연락처]", t or "")
    t = EMAIL.sub("[메일]", t)
    return TITLED.sub(lambda m: m.group(1), t)


def detect_roles(header):
    roles = {}
    for i, h in enumerate(header):
        h = (h or "").strip()
        if not h or PRIVATE.search(h) and not re.search(r"영업\s?담당", h):
            continue
        for role, rx in ROLES:
            if role not in roles and rx.search(h):
                roles[role] = i
                break
    return roles


def parse_date(s, default_year=2026):
    s = (s or "").strip()
    m = re.search(r"(20\d{2})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(?<!\d)(\d{1,2})\s?[./월-]\s?(\d{1,2})", s)
        if not m:
            return None
        y, (mo, d) = default_year, map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def norm(s):
    return re.sub(r"[\s\W_]+", "", (s or "")).lower()


def region_of(*texts):
    blob = " ".join(t or "" for t in texts)
    for r in REGIONS:
        if r in blob:
            return r
    for full, r in (("충청북", "충북"), ("충청남", "충남"), ("전라북", "전북"), ("전라남", "전남"), ("경상북", "경북"), ("경상남", "경남")):
        if full in blob:
            return r
    return ""


def load_matrix():
    import own_pipeline_export as ope
    if not ope.SA_JSON:
        raise RuntimeError("GOOGLE_SHEETS_SA_JSON 없음")
    m = ope.fetch_via_service_account(COMMS_GID)
    return m, ope.STATUS.get("sheet_tab")


def parse(matrix):
    best = max(range(min(10, len(matrix))), key=lambda i: len(detect_roles(matrix[i])))
    header = matrix[best]
    roles = detect_roles(header)
    rows = []
    for r in matrix[best + 1:]:
        g = lambda k: (r[roles[k]] if k in roles and roles[k] < len(r) else "") or ""
        txt = g("text")
        d = parse_date(g("date"))
        if not (txt.strip() or g("course").strip()):
            continue
        rows.append({"date": d, "region": g("region").strip() or region_of(g("org")), "org": g("org").strip(),
                     "course": g("course").strip(), "kind": g("kind").strip(), "stage": g("stage").strip(),
                     "text": scrub(txt)[:600]})
    return rows, {k: (header[i] or "").strip() for k, i in roles.items()}, best + 1


def link(rows, records):
    """소통 행 -> 파이프라인 사업. 사업명(정규화) 포함 관계 우선, 없으면 기관명 일치."""
    keys = []
    for i, rec in enumerate(records):
        keys.append((i, norm(rec.get("courseName")), norm(rec.get("org")), rec.get("region") or ""))
    out = defaultdict(list)
    unlinked = 0
    for row in rows:
        c, o = norm(row["course"]), norm(row["org"])
        hit = [i for i, kc, ko, _ in keys if kc and c and (kc in c or c in kc) and (not o or not ko or ko[:4] in o or o[:4] in ko)]
        if not hit and o:
            hit = [i for i, kc, ko, _ in keys if ko and (ko == o or (len(o) >= 4 and (o in ko or ko in o)))]
        if not hit:
            unlinked += 1
        for i in hit[:3]:
            out[i].append(row)
    return out, unlinked


PROMPT = """너는 (주)비상교육 비바샘원격교육연수원 B2G 교원연수 사업 PMO다. 아래는 {region} 지역 위탁 연수 사업별 최근 소통 기록(교육청·지원청 담당 장학사와의 협의 메모, 개인정보 제거됨)이다.
기록에 있는 사실만 근거로 사업별 운영·진행 핵심 상황을 한국어 JSON으로 정리하라. 사람 이름·연락처·직위+이름은 절대 쓰지 마라('담당 장학사'처럼 역할로만). 추측 금지.
{{"region_summary": "지역 전체 상황 2문장", "items": [{{"id": "사업 id 그대로", "status": "현재 상황 1문장(40자 이내)", "issue": "핵심 이슈·요청(40자 이내, 없으면 빈 문자열)", "next": "다음 액션(30자 이내)", "risk": "높음|보통|낮음"}}]}}
사업 기록:
"""


def ai_summaries(by_region_payload):
    import gemini_client as gc
    if not gc.key():
        return {}, "GEMINI_API_KEY 없음"
    cache = json.loads(AI_CACHE.read_text(encoding="utf-8")) if AI_CACHE.exists() else {}
    err = None
    for region, payload in by_region_payload.items():
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        h = hashlib.sha1(blob.encode()).hexdigest()[:16]
        if cache.get(region, {}).get("h") == h:
            continue
        try:
            res = gc.generate_json(PROMPT.format(region=region) + blob[:30000])
        except Exception as e:
            err = gc.mask(e)[:200]
            continue
        items = {str(it.get("id")): {k: scrub(str(it.get(k, "")))[:120] for k in ("status", "issue", "next", "risk")}
                 for it in res.get("items", []) if it.get("id") is not None}
        cache[region] = {"h": h, "summary": scrub(str(res.get("region_summary", "")))[:300], "items": items,
                         "date": date.today().isoformat(), "model": gc.model().split("/")[-1]}
    AI_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache, err


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/pipeline_comms.json")
    status = {"date": date.today().isoformat(), "gid": COMMS_GID}
    try:
        pipe = json.loads((HERE / "live" / "own_pipeline_export.json").read_text(encoding="utf-8"))
        records = pipe.get("records", [])
        matrix, tab = load_matrix()
        rows, roles, hrow = parse(matrix)
        status.update({"tab": tab, "header_row": hrow, "roles": roles, "rows": len(rows),
                       "dated": sum(1 for r in rows if r["date"])})
    except Exception as e:
        status["error"] = str(e)[:300]
        STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        out.write_text(json.dumps({"available": False, "error": status["error"]}, ensure_ascii=False), encoding="utf-8")
        print(f"[경고] 소통 내역 조회 실패: {e}", file=sys.stderr)
        return
    today = date.today()
    linked, unlinked = link(rows, records)
    status["linked_courses"], status["unlinked_rows"] = len(linked), unlinked
    per = {}
    payload = defaultdict(list)
    for i, rec in enumerate(records):
        rs = sorted([r for r in linked.get(i, [])], key=lambda r: r["date"] or date.min)
        dated = [r for r in rs if r["date"]]
        last = dated[-1]["date"] if dated else None
        per[i] = {"n": len(rs), "n30": sum(1 for r in dated if (today - r["date"]).days <= 30),
                  "last": last.isoformat() if last else "", "days": (today - last).days if last else None,
                  "kinds": sorted({r["kind"] for r in rs if r["kind"]})[:4]}
        if rs:
            reg = rec.get("region") or region_of(rec.get("org")) or "기타"
            payload[reg].append({"id": i, "사업": rec.get("courseName"), "기관": rec.get("org"), "상태": rec.get("status"),
                                 "계약": rec.get("contractProgress"),
                                 "기록": [f"{r['date'] or ''} {r['kind']} {r['stage']} {r['text']}".strip() for r in rs[-8:]]})
    cache, ai_err = ai_summaries(payload) if payload else ({}, None)
    if ai_err:
        status["ai_error"] = ai_err
    regions = {}
    for reg, c in cache.items():
        if reg in payload:
            regions[reg] = {"summary": c.get("summary", ""), "date": c.get("date"), "model": c.get("model")}
            for sid, it in c.get("items", {}).items():
                if sid.isdigit() and int(sid) in per:
                    per[int(sid)]["ai"] = it
    out.write_text(json.dumps({"available": True, "tab": tab, "rows": len(rows), "linked": len(linked), "unlinked": unlinked,
                               "fetched": (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                               "per": per, "regions": regions}, ensure_ascii=False), encoding="utf-8")
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"소통 분석: {len(rows)}건, 사업 연결 {len(linked)}개, 미연결 {unlinked}건, AI 지역 {len(regions)}")


if __name__ == "__main__":
    main()
