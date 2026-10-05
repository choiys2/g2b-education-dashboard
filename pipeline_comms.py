#!/usr/bin/env python3
"""
영업 소통 내역(구글시트 '26영업소통 DT', gid 1083489926) -> 사업별 운영·진행 핵심 상황 분석.

*** 개인정보·대외비 보호 (대시보드는 공개 배포) ***
- 소통 원문은 CI 메모리에서만 쓰고 live/·history/ 어디에도 저장하지 않는다.
- 이름·연락처·이메일 열은 아예 읽지 않는다(ROLE 판별에서 제외). 본문은 Gemini에 보내기 전
  전화·이메일·'홍길동 장학사' 같은 호칭 앞 이름을 지운다.
- 공개 범위는 숫자 지표뿐(2026-10-05 사용자 결정): 소통 건수(30일/이전 30일/전체), 최근 소통일·경과일,
  소통 유형 분포, 이슈 분류 태그 건수(예산·일정·모집 등 정해진 범주명만), 규칙 기반 관리 신호.
  문장 요약·원문 발췌는 만들지 않고, 소통 원문을 외부 AI로 보내지도 않는다.
  python pipeline_comms.py [out_json]
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
COMMS_GID = os.environ.get("PIPELINE_COMMS_GID", "1083489926")
STATUS_PATH = HERE / "history" / "pipeline_comms_status.json"
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
           "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
# 열 역할: 머리글에 이 단어가 들어 있으면 그 역할. PRIVATE 에 걸리는 열은 절대 안 읽는다.
PRIVATE = re.compile(r"연락|전화|휴대|핸드폰|메일|e-?mail|성명|이름|주무관|장학사|연구사|담당|직위|직급|소통자|작성자|기록자|상대|대상자", re.I)
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
    if re.fullmatch(r"4\d{4}(\.\d+)?", s):  # 스프레드시트 일련번호(1899-12-30 기준)
        return date(1899, 12, 30) + timedelta(days=int(float(s)))
    m = re.search(r"(20\d{2})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})", s) or re.search(r"(?<!\d)(2\d)[./-](\d{1,2})[./-](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        y = y + 2000 if y < 100 else y
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


DIAG = {}


def parse(matrix):
    best = max(range(min(10, len(matrix))), key=lambda i: len(detect_roles(matrix[i])))
    header = matrix[best]
    roles = detect_roles(header)
    # 진단(공개 저장소에 커밋): 머리글 이름과 날짜 열 표본만. 본문·이름 값은 남기지 않는다.
    DIAG["header"] = [(h or "").strip()[:20] for h in header][:50]
    if "date" in roles:
        DIAG["date_samples"] = [r[roles["date"]] for r in matrix[best + 1:best + 40] if roles["date"] < len(r) and r[roles["date"]]][:5]
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


# 이슈 분류: 원문에서 범주 '이름'만 센다(문장은 게시하지 않음)
ISSUES = [("예산", r"예산|추경|단가|금액|정산|결산"), ("일정", r"일정|연기|지연|변경|늦|마감|기한"),
          ("모집", r"모집|신청|인원|미달|홍보|공문"), ("계약", r"계약|견적|수의|입찰|품의|발주"),
          ("운영", r"강사|콘텐츠|시스템|오류|접속|출결|수료|만족도"), ("민원", r"민원|불만|항의|클레임|문제\s?제기"),
          ("확대", r"추가|확대|차년도|내년|2027|재계약|후속")]
ISSUE_RX = [(k, re.compile(v)) for k, v in ISSUES]
KIND_RX = re.compile(r"전화|통화|방문|대면|비대면|메일|문자|카톡|메신저|회의|미팅|협의회|공문|온라인|화상|설명회")


def kind_label(k):
    """소통 유형은 정해진 어휘만 게시(셀에 사람 이름 등이 섞여도 새지 않게)."""
    m = KIND_RX.search(k or "")
    return m.group(0) if m else "기타"


def signal(status, n, days, n30, prev30):
    """규칙 기반 관리 신호(문장 없이 등급만)."""
    if re.search(r"완료|종료|취소|정산", status or ""):
        return "종료"
    if not n:
        return "기록 없음"
    if days is not None and days > 30:
        return "주의"
    if n30 < prev30 / 2 and prev30 >= 2:
        return "관심"
    return "정상"


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/pipeline_comms.json")
    status = {"date": date.today().isoformat(), "gid": COMMS_GID}
    try:
        pipe = json.loads((HERE / "live" / "own_pipeline_export.json").read_text(encoding="utf-8"))
        records = pipe.get("records", [])
        matrix, tab = load_matrix()
        rows, roles, hrow = parse(matrix)
        status.update({"tab": tab, "header_row": hrow, "roles": roles, **DIAG, "rows": len(rows),
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
    per, kinds_all, issues_all = {}, defaultdict(int), defaultdict(int)
    for i, rec in enumerate(records):
        rs = linked.get(i, [])
        dated = [r for r in rs if r["date"]]
        last = max((r["date"] for r in dated), default=None)
        n30 = sum(1 for r in dated if (today - r["date"]).days <= 30)
        prev30 = sum(1 for r in dated if 30 < (today - r["date"]).days <= 60)
        kinds = defaultdict(int)
        for r in rs:
            if r["kind"]:
                kl = kind_label(r["kind"])
                kinds[kl] += 1
                kinds_all[kl] += 1
        iss = defaultdict(int)
        for r in rs:
            for k, rx in ISSUE_RX:
                if rx.search(r["text"]):
                    iss[k] += 1
                    issues_all[k] += 1
        days = (today - last).days if last else None
        per[i] = {"n": len(rs), "n30": n30, "prev30": prev30, "last": last.isoformat() if last else "",
                  "days": days, "kinds": dict(kinds), "issues": dict(iss),
                  "signal": signal(rec.get("status"), len(rs), days, n30, prev30)}
    months = defaultdict(int)
    for r in rows:
        if r["date"] and r["date"].year >= today.year - 1:
            months[r["date"].strftime("%Y-%m")] += 1
    out.write_text(json.dumps({"available": True, "tab": tab, "rows": len(rows), "linked": len(linked), "unlinked": unlinked,
                               "fetched": (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
                               "per": per, "kinds": dict(kinds_all), "issues": dict(issues_all),
                               "issue_labels": [k for k, _ in ISSUES], "months": dict(sorted(months.items()))},
                              ensure_ascii=False), encoding="utf-8")
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"소통 분석: {len(rows)}건, 사업 연결 {len(linked)}개, 미연결 {unlinked}건")


if __name__ == "__main__":
    main()
