#!/usr/bin/env python3
"""
비바샘 자체 영업 파이프라인 구글시트 -> live/own_pipeline_export.json

*** 개인정보 보호 방침 (반드시 지킬 것) ***
원본 시트에는 담당 공무원 연락처/이메일/실명(주무관) 컬럼이 그대로 들어있다.
이 스크립트는 SAFE_FIELDS에 명시된 컬럼만 읽고, 그 외 컬럼(연락처/메일/주무관/담당 등)은
절대 파싱하지도, 저장하지도 않는다. 이 대시보드는 GitHub Pages로 공개 배포되므로
공무원 개인정보가 한 줄이라도 새어나가면 안 된다.

담당 영업자 실명도 하드코딩하지 않고, 매 실행마다 등장 빈도순으로 "영업자 A/B/C..."를
동적으로 부여한다(고정된 이름 매핑을 코드에 남기지 않기 위함).

*** 시트 접근 방식 (2026-08-19 변경) ***
원본 시트가 비공개로 전환되면서, 로그인 없이 누구나 열 수 있던 gviz 공개 조회
엔드포인트가 더는 안 먹힌다. 그렇다고 시트를 다시 "링크가 있는 모든 사용자" 로
풀어버리면 원본 시트 전체(화이트리스트 밖 컬럼 포함)가 링크 유출 시 그대로
노출된다 - 그건 이 파이프라인이 막으려는 것과 정반대다. 그래서 구글 서비스계정
전용 인증(Sheets API v4)으로 바꾼다: 서비스계정 이메일에만 "뷰어"로 시트를
공유하면, 그 계정 자격증명(GitHub Secret으로 보관)을 가진 이 파이프라인만
원본 시트를 읽을 수 있다. 공개 배포되는 대시보드에는 여전히 SAFE_FIELDS로
거른 값만 나간다는 점은 이전과 동일 - 이 변경은 "원본 시트"의 접근 통제만
강화하는 것이다.
GOOGLE_SHEETS_SA_JSON 환경변수(서비스계정 JSON 키 전체 내용)가 있으면 이
방식을 쓰고, 없으면 기존 공개 gviz 방식으로 자동 폴백한다(하위 호환).
"""
import json, os, re, sys, urllib.request, urllib.parse, urllib.error
from collections import defaultdict, Counter

SHEET_ID = os.environ.get("PIPELINE_SHEET_ID", "1qF-wdKmD5buPLZKPwqIn9jA5fv69NDg1K6bUF4vo3Hw")
SHEET_GID = os.environ.get("PIPELINE_SHEET_GID", "274729463")
SA_JSON = os.environ.get("GOOGLE_SHEETS_SA_JSON", "")

# 시트 헤더 -> 안전한 내부 필드명. 이 목록에 없는 컬럼(연락처/메일/주무관 등)은 아예 안 읽는다.
SAFE_FIELDS = {
    "상태": "status", "기수": "gisu", "분야": "field", "연수명": "courseName",
    "지역": "region", "기관명": "org", "영업 담당": "salesRep",
    "신청시작": "recruitStart", "신청종료": "recruitEnd",
    "연수시작": "trainStart", "연수종료": "trainEnd",
    "계약진행": "contractProgress", "계약일": "contractDate",
    "목표인원": "targetCount", "신청현황": "appliedCount",
    "예상매출": "expectedRevenueMonth", "총예산": "targetAmount",
}
REGIONS = ["서울","부산","대구","인천","광주","대전","울산","세종","경기","강원",
           "충북","충남","전북","전남","경북","경남","제주"]


def fetch_gviz():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?" + urllib.parse.urlencode({"gid": SHEET_GID})
    with urllib.request.urlopen(url, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    m = re.search(r"setResponse\((.*)\);?\s*$", raw.strip(), re.S)
    return json.loads(m.group(1))


def rows_from_gviz(payload):
    cols = payload["table"]["cols"]
    col_field = []
    for c in cols:
        label = (c.get("label") or "").strip()
        col_field.append(SAFE_FIELDS.get(label))  # None이면 그 컬럼은 버림(화이트리스트 밖)

    records = []
    for row in payload["table"]["rows"]:
        rec = {}
        for i, cell in enumerate(row.get("c") or []):
            field = col_field[i] if i < len(col_field) else None
            if not field:
                continue  # 화이트리스트 밖 컬럼(연락처/메일/주무관 등)은 절대 안 읽음
            v = cell.get("f") if cell and cell.get("f") is not None else (cell.get("v") if cell else None)
            rec[field] = v if v is not None else ""
        if any(str(v).strip() for v in rec.values()):
            records.append(rec)
    return records


def _sheets_api_get(url, access_token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_via_service_account():
    """서비스계정 자격증명으로 Sheets API v4를 호출해 values.get 결과를 gviz와
    동일한 {행렬} 형태로 반환한다. google-auth가 JWT 서명·토큰 교환을 처리한다."""
    from google.oauth2 import service_account
    import google.auth.transport.requests as ga_requests

    info = json.loads(SA_JSON)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    creds.refresh(ga_requests.Request())
    token = creds.token

    # gid는 웹 UI/gviz 전용 식별자라 API v4는 못 알아듣는다 - 먼저 시트 메타데이터에서
    # gid에 대응하는 탭 "제목"을 찾는다(예: "26운영dt").
    meta = _sheets_api_get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?fields=sheets.properties",
        token)
    title = None
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if str(props.get("sheetId")) == str(SHEET_GID):
            title = props.get("title")
            break
    if not title:
        raise RuntimeError(f"gid={SHEET_GID}에 해당하는 시트 탭을 찾지 못함")

    range_q = urllib.parse.quote(f"'{title}'", safe="")
    values_url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{range_q}"
                  f"?valueRenderOption=FORMATTED_VALUE")
    data = _sheets_api_get(values_url, token)
    return data.get("values", [])


def rows_from_matrix(matrix):
    """Sheets API v4 values.get 결과([[헤더...], [행...], ...])를 gviz 방식과
    동일하게 SAFE_FIELDS 화이트리스트만 걸러 records로 변환한다."""
    if not matrix:
        return []
    header = matrix[0]
    col_field = [SAFE_FIELDS.get((h or "").strip()) for h in header]

    records = []
    for row in matrix[1:]:
        rec = {}
        for i, field in enumerate(col_field):
            if not field:
                continue  # 화이트리스트 밖 컬럼은 절대 안 읽음
            v = row[i] if i < len(row) else ""
            rec[field] = v
        if any(str(v).strip() for v in rec.values()):
            records.append(rec)
    return records


def to_num(s):
    if not s:
        return 0
    m = re.search(r"-?\d[\d,]*", str(s).replace(",", ""))
    try:
        return int(str(s).replace(",", "").strip() or 0)
    except Exception:
        return 0


def anonymize_reps(records):
    """실명을 코드에 하드코딩하지 않고, 매 실행마다 빈도순으로 동적 부여."""
    counts = Counter(r.get("salesRep") for r in records if r.get("salesRep"))
    ordered = [name for name, _ in counts.most_common()]
    mapping = {name: f"영업자 {chr(65+i)}" for i, name in enumerate(ordered)}
    for r in records:
        if r.get("salesRep") in mapping:
            r["salesRep"] = mapping[r["salesRep"]]
    return records


def analyze(records):
    by_status = Counter(r["status"] for r in records if r.get("status"))
    by_contract = Counter(r["contractProgress"] for r in records if r.get("contractProgress"))
    total_target = sum(to_num(r.get("targetAmount")) for r in records)
    rates = []
    for r in records:
        m = re.search(r"([\d.]+)", str(r.get("appliedCount", "")))
    by_region = defaultdict(lambda: {"count": 0, "amount": 0})
    by_rep = defaultdict(lambda: {"count": 0, "amount": 0})
    by_field = defaultdict(lambda: {"count": 0, "amount": 0})
    by_month = defaultdict(lambda: {"count": 0, "amount": 0})
    for r in records:
        amt = to_num(r.get("targetAmount"))
        reg = r.get("region") or "(미정)"
        by_region[reg]["count"] += 1
        by_region[reg]["amount"] += amt
        rep = r.get("salesRep") or "(미정)"
        by_rep[rep]["count"] += 1
        by_rep[rep]["amount"] += amt
        fld = r.get("field") or "(미정)"
        by_field[fld]["count"] += 1
        by_field[fld]["amount"] += amt
        mo = r.get("expectedRevenueMonth")
        if mo:
            by_month[mo]["count"] += 1
            by_month[mo]["amount"] += amt

    return {
        "kpi": {"total": len(records), "totalTarget": total_target,
                "byStatus": dict(by_status), "byContract": dict(by_contract)},
        "byRegion": {k: v for k, v in by_region.items()},
        "byRep": {k: v for k, v in by_rep.items()},
        "byField": {k: v for k, v in by_field.items()},
        "byMonth": {k: v for k, v in by_month.items()},
    }


def fetch_records():
    if SA_JSON:
        return rows_from_matrix(fetch_via_service_account())
    return rows_from_gviz(fetch_gviz())


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "live/own_pipeline_export.json"
    try:
        records = fetch_records()
    except Exception as e:
        print(f"[경고] 시트 조회 실패(비공개로 전환됐거나 서비스계정 미공유일 수 있음): {e}", file=sys.stderr)
        json.dump({"records": [], "kpi": {"total": 0}, "byRegion": {}, "byRep": {}, "byField": {}, "byMonth": {}},
                   open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return
    records = anonymize_reps(records)
    analysis = analyze(records)
    analysis["records"] = records
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"saved {out_path}: {len(records)}건, 안전 필드 {len(SAFE_FIELDS)}개만 사용")


if __name__ == "__main__":
    main()
