#!/usr/bin/env python3
"""
역량향상 사전진단(종합) 사이트의 "시도별 연수 목록" 표 -> static_data/public_training_list.json

www.survey.co.kr 은 ACCESS_KEY 로 접근하는 응답용 폼이라 API가 없고 자동수집 대상도 아니다.
그래서 화면에 뜬 표를 사람이 한 번 가져오고, 이 스크립트가 대시보드가 읽는 JSON으로 바꾼다.

입력은 둘 중 아무거나:
  1) 목록 화면을 저장한 HTML  (브라우저 '다른 이름으로 저장')
  2) 표를 드래그·복사해 붙여넣은 텍스트 (브라우저가 탭 구분 TSV로 넣어준다. CSV도 됨)

사용법:
  python parse_training_list.py seoul.html          # 기존 rows에 누적(중복 제거)
  python parse_training_list.py gyeonggi.tsv        # 시도별로 한 번씩 돌리면 합쳐짐
  python parse_training_list.py all.html --replace  # 기존 rows를 버리고 새로 씀

표에 어떤 컬럼이 있든 헤더 이름으로 찾으므로 컬럼 순서가 바뀌어도 동작한다.
'선택' 같은 버튼 컬럼은 무시한다.
"""
import sys, os, json, csv, io, re, argparse
from html.parser import HTMLParser

OUT_PATH = "static_data/public_training_list.json"

# 화면 헤더 -> JSON 키. 공백을 뺀 뒤 비교하므로 "운영 차시"/"운영차시" 둘 다 잡힌다.
HEADER_MAP = {
    "지역": "지역",
    "연수명": "연수명",
    "기수/회차": "기수", "기수회차": "기수", "기수": "기수", "회차": "기수",
    "시작일자": "시작일자", "시작일": "시작일자",
    "종료일자": "종료일자", "종료일": "종료일자",
    "운영차시": "차시", "차시": "차시",
    "운영기관": "운영기관", "주관기관": "운영기관",
}
FIELDS = ["지역", "연수명", "기수", "시작일자", "종료일자", "차시", "운영기관"]


class TableParser(HTMLParser):
    """문서 안의 모든 <table>을 '행 리스트'로 뽑는다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._table, self._row, self._cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def rows_from_html(text):
    p = TableParser()
    p.feed(text)
    for table in p.tables:
        for i, row in enumerate(table):
            squished = [c.replace(" ", "") for c in row]
            if "지역" in squished and "연수명" in squished:
                return [row] + table[i + 1:]
    raise SystemExit("표를 찾지 못했습니다: '지역'과 '연수명'이 함께 있는 헤더 행이 없습니다.")


def rows_from_text(text):
    sample = text.splitlines()[0] if text.strip() else ""
    delim = "\t" if "\t" in sample else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    for i, row in enumerate(rows):
        squished = [c.replace(" ", "").strip() for c in row]
        if "지역" in squished and "연수명" in squished:
            return rows[i:]
    raise SystemExit("표를 찾지 못했습니다: '지역'과 '연수명'이 함께 있는 헤더 행이 없습니다.")


def norm_date(s):
    """'26.10.01' / '2026-10-01' / '2026.10.01' -> '2026-10-01'. 못 읽으면 원문 그대로."""
    s = (s or "").strip()
    m = re.match(r"^(\d{2}|\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$", s)
    if not m:
        return s
    y, mo, d = m.groups()
    if len(y) == 2:
        y = "20" + y
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def norm_chasi(s):
    m = re.search(r"\d+", (s or "").replace(",", ""))
    return int(m.group()) if m else 0


def build_rows(table):
    header = [c.replace(" ", "").strip() for c in table[0]]
    col = {}
    for idx, name in enumerate(header):
        key = HEADER_MAP.get(name)
        if key and key not in col:
            col[key] = idx
    for need in ("지역", "연수명"):
        if need not in col:
            raise SystemExit(f"헤더에 '{need}' 컬럼이 없습니다. 읽은 헤더: {header}")

    out = []
    for raw in table[1:]:
        def cell(key):
            i = col.get(key)
            return raw[i].strip() if i is not None and i < len(raw) else ""

        지역, 연수명 = cell("지역"), cell("연수명")
        if not 지역 or not 연수명:
            continue
        out.append({
            "지역": 지역,
            "연수명": 연수명,
            "기수": cell("기수"),
            "시작일자": norm_date(cell("시작일자")),
            "종료일자": norm_date(cell("종료일자")),
            "차시": norm_chasi(cell("차시")),
            "운영기관": cell("운영기관"),
        })
    return out


def dedup_key(r):
    return (r["지역"], r["연수명"], r["시작일자"], r["운영기관"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="저장한 HTML 파일 또는 복사한 표(TSV/CSV) 파일")
    ap.add_argument("--replace", action="store_true", help="기존 rows를 버리고 새로 쓴다(기본은 누적)")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    text = open(args.input, encoding="utf-8", errors="replace").read()
    table = rows_from_html(text) if "<" in text[:2000] and "<t" in text.lower() else rows_from_text(text)
    new_rows = build_rows(table)

    if os.path.exists(args.out):
        doc = json.load(open(args.out, encoding="utf-8"))
    else:
        doc = {"source": "역량향상 사전진단(종합) — 시도별 연수 목록", "rows": []}

    kept = [] if args.replace else list(doc.get("rows", []))
    seen = {dedup_key(r) for r in kept}
    added = 0
    for r in new_rows:
        if dedup_key(r) in seen:
            continue
        seen.add(dedup_key(r))
        kept.append(r)
        added += 1

    kept.sort(key=lambda r: (r["지역"], r["시작일자"], r["연수명"]))
    doc["rows"] = kept
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    regions = sorted({r["지역"] for r in kept})
    print(f"{args.input}: 읽은 {len(new_rows)}건 / 새로 추가 {added}건 / 누적 {len(kept)}건")
    print(f"커버 시도 {len(regions)}개: {', '.join(regions)}")


if __name__ == "__main__":
    main()
