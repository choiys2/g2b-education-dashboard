"""결과보고 웹앱 빌드 — 양식 파일을 웹 페이지(app.html)에 내장한다.

양식은 개인정보·거래처 정보가 있어 저장소에 넣지 않는다. 담당자 PC의 원본 양식으로 빌드:
  python result_report/web/build_web.py \
      --report-hwpx 결과보고서양식.hwpx --invoice-xls 청구서양식.xls \
      --analysis-xlsx 이수자분석양식.xlsx --out dist/결과보고_자동화.html

빌드가 하는 일
  - 청구서 xls → xlsx 변환(LibreOffice), 과정 줄 30칸으로 확장(브라우저에서 쓰지 않는 줄은 숨김)
  - 이수자분석양식 비식별화: 수강 상세 A:P 비우기, 피벗 캐시의 성명·생년월일·나이스·휴대폰·이수번호 제거,
    더 이상 쓰지 않는 공유문자열 비우기
  - 이수자 명단 서식 양식 생성
  - 위 4개 + 한글 결과보고서 양식을 base64로 app.html에 삽입
"""

import argparse
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

INVOICE_LINES = 30
PERSONAL_FIELDS = ("성명", "생년월일", "나이스식별번호", "휴대폰번호", "이수번호")
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


LABELS = {"사업명": "사 업 명", "수신처": "수 신 처", "청구일자": "청 구 일 자", "등록번호": "등 록 번 호",
          "공급자 주소": "주        소", "공급자 전화": "전 화 번 호", "공급자 이메일": "E-mail", "대표자명": "대표자명"}


def _norm(t):
    return "".join(str(t).split())


def invoice_xlsx(xls_path, out_path):
    """청구서 xls → xlsx. 라벨('사 업 명', '순', '교육기부' 등)로 칸을 찾아 양식이 한두 줄 밀려도 동작.
    과정 줄을 INVOICE_LINES로 늘리고, 브라우저가 쓸 좌표(layout)를 돌려준다."""
    import rr_invoice as ri
    with ri.office() as desk:
        doc = desk.loadComponentFromURL(ri._url(xls_path), "_blank", 0, ri._props(Hidden=True))
        try:
            sh = doc.Sheets.getByIndex(0)
            rng = sh.getCellRangeByName
            txt = lambda c, r: sh.getCellByPosition(c, r).getString()
            grid = {(c, r): _norm(txt(c, r)) for r in range(80) for c in range(16)}
            find = lambda label, col=None: next((rc for rc, v in sorted(grid.items(), key=lambda x: (x[0][1], x[0][0]))
                                                  if v == _norm(label) and (col is None or rc[0] == col)), None)
            head = find("순", 1)
            don = find("교육기부", 1)
            if not head or not don:
                raise SystemExit("청구서 양식에서 '순' 머리글이나 '교육기부' 줄을 찾지 못했습니다")
            first, last_tpl = head[1] + 3, don[1]          # 1-based: 머리글 2줄 다음부터 교육기부 앞까지
            n_tpl = last_tpl - first + 1
            for ref in (f"C{first}:C{last_tpl}", f"L{first}:M{last_tpl}"):
                rng(ref).merge(False)
            if INVOICE_LINES > n_tpl:
                sh.Rows.insertByIndex(last_tpl - 1, INVOICE_LINES - n_tpl)
            last = first + INVOICE_LINES - 1
            for r in range(first, last + 1):
                for a, b in ri.ROW_MERGES:
                    rng(f"{a}{r}:{b}{r}").merge(False)
                    rng(f"{a}{r}:{b}{r}").merge(True)
            rng(f"B{first}:O{last}").clearContents(1 | 2 | 4 | 16)
            layout = {"FIRST": first, "LINES": INVOICE_LINES, "DON": last + 1, "TOTAL": last + 2, "NOTE": last + 3}
            for key, label in LABELS.items():
                rc = find(label)
                if rc:
                    col = "G" if rc[0] < 6 else "M"
                    layout[key] = f"{col}{rc[1] + 1}"
            dams = sorted((rc for rc, v in grid.items() if v == _norm("담 당 자")), key=lambda x: (x[1], x[0]))
            if dams:
                layout["수신 담당자"] = f"G{dams[0][1] + 1}"
            if len(dams) > 1:
                layout["공급자 담당자"] = f"M{dams[1][1] + 1}"
            doc.storeToURL(ri._url(out_path), ri._props(FilterName="Calc MS Excel 2007 XML", Overwrite=True))
            return layout
        finally:
            doc.close(True)


def sanitize_analysis(src, out_path):
    with zipfile.ZipFile(src) as z:
        files = {n: z.read(n) for n in z.namelist()}
        order = z.namelist()
    import rr_xlsx_template as xt
    paths = xt._sheet_paths(files)
    sh = xt.Sheet(files[paths[xt.DATA_SHEET]])
    styles = [sh.style_of(f"{xt.col_name(i)}2") for i in range(1, 17)]
    sh.clear_cols("A", "P", 2)
    for i, s in enumerate(styles, 1):  # 브라우저가 서식을 가져갈 빈 2행
        sh.set(f"{xt.col_name(i)}2", None, style=s)
    files[paths[xt.DATA_SHEET]] = sh.bytes()

    # 남은 시트가 참조하는 공유문자열만 남기고 나머지는 빈 문자열로(인덱스 유지)
    used = set()
    for p in paths.values():
        t = etree.fromstring(files[p])
        for c in t.iter(f"{{{NS}}}c"):
            if c.get("t") == "s":
                v = c.find(f"{{{NS}}}v")
                if v is not None:
                    used.add(int(v.text))
    sst = etree.fromstring(files["xl/sharedStrings.xml"])
    for i, si in enumerate(sst.findall(f"{{{NS}}}si")):
        if i not in used:
            for ch in list(si):
                si.remove(ch)
            etree.SubElement(si, f"{{{NS}}}t")
    files["xl/sharedStrings.xml"] = etree.tostring(sst, xml_declaration=True, encoding="UTF-8", standalone=True)

    for n in list(files):
        if n.startswith("xl/pivotCache/pivotCacheDefinition"):
            d = etree.fromstring(files[n])
            names = [f.get("name") for f in d.iter(f"{{{NS}}}cacheField")]
            d.set("refreshOnLoad", "1")
            files[n] = etree.tostring(d, xml_declaration=True, encoding="UTF-8", standalone=True)
            rec_name = n.replace("pivotCacheDefinition", "pivotCacheRecords")
            if rec_name in files:
                idx = {i for i, nm in enumerate(names) if nm in PERSONAL_FIELDS}
                r = etree.fromstring(files[rec_name])
                for rec in r.findall(f"{{{NS}}}r"):
                    for i, cell in enumerate(rec):
                        if i in idx:
                            cell.tag = f"{{{NS}}}s"
                            cell.attrib.clear()
                            cell.set("v", "-")
                files[rec_name] = etree.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True)

    leaked = [n for n, b in files.items() if re.search(rb"J10\d{7}|010-\d{4}-\d{4}", b)]
    if leaked:
        raise SystemExit(f"비식별화 실패: {leaked}")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in order:
            z.writestr(n, files[n])


def list_template(out_path):
    import openpyxl
    from build_result_report import LIST_COLUMNS, LIST_WIDTHS, _sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "이수자 명단"
    _sheet(ws, LIST_COLUMNS, [[""] * len(LIST_COLUMNS)], LIST_WIDTHS)
    ws.freeze_panes = None
    wb.save(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-hwpx", required=True)
    ap.add_argument("--invoice-xls", required=True)
    ap.add_argument("--analysis-xlsx", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="rr_web_")
    try:
        inv = os.path.join(tmp, "invoice.xlsx")
        ana = os.path.join(tmp, "analysis.xlsx")
        lst = os.path.join(tmp, "list.xlsx")
        layout = invoice_xlsx(a.invoice_xls, inv)
        print("청구서 좌표:", layout)
        sanitize_analysis(a.analysis_xlsx, ana)
        list_template(lst)
        b64 = lambda p: base64.b64encode(open(p, "rb").read()).decode()
        blob = {"report": b64(a.report_hwpx), "invoice": b64(inv), "analysis": b64(ana), "list": b64(lst)}
        html = open(os.path.join(HERE, "app.html"), encoding="utf-8").read()
        js = ("const TEMPLATES = {" + ",".join(f'{k}:"{v}"' for k, v in blob.items()) + "};\n"
              + "const INVOICE_LAYOUT = " + json.dumps(layout, ensure_ascii=False) + ";")
        html = html.replace("/*__TEMPLATES__*/", js, 1)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"{a.out}  {len(html) / 1e6:.1f}MB")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
