"""교육청 결과보고 — 이수자분석양식(xlsx)에 정리본을 '붙여넣기'.

openpyxl로 열었다 저장하면 양식의 그래프(차트)가 사라지므로, xlsx 내부 XML을 직접 고친다.
  - '1. 수강 상세현황' A:P 데이터만 교체(오른쪽 R:AE 집계 수식·서식은 그대로)
  - 피벗 캐시 refreshOnLoad=1 → 엑셀로 열 때 피벗·그래프 자동 새로고침(인계서의 '피벗분석-새로고침' 대체)
  - 계산 fullCalcOnLoad=1 → 수식 재계산
  - '3.설문조사(단일)' 응답 수·조사인원·종합 문구 입력
"""

import io
import posixpath
import re
import zipfile

from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
Q = lambda t: f"{{{NS}}}{t}"

DATA_SHEET = "1. 수강 상세현황"
SURVEY_SHEET = "3.설문조사(단일)"


def col_idx(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def split_ref(ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return m.group(1), int(m.group(2))


def col_name(i):
    s = ""
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class Sheet:
    def __init__(self, xml):
        self.tree = etree.fromstring(xml)
        self.data = self.tree.find(Q("sheetData"))
        self.rows = {int(r.get("r")): r for r in self.data.findall(Q("row"))}

    def row(self, n):
        if n in self.rows:
            return self.rows[n]
        new = etree.Element(Q("row"), r=str(n))
        after = [k for k in self.rows if k < n]
        if after:
            self.rows[max(after)].addnext(new)
        else:
            self.data.insert(0, new)
        self.rows[n] = new
        return new

    def cell(self, ref, create=True):
        col, n = split_ref(ref)
        row = self.rows.get(n) if not create else self.row(n)
        if row is None:
            return None
        ci = col_idx(col)
        for c in row.findall(Q("c")):
            cc, _ = split_ref(c.get("r"))
            if cc == col:
                return c
            if col_idx(cc) > ci:
                if not create:
                    return None
                new = etree.Element(Q("c"), r=ref)
                c.addprevious(new)
                return new
        if not create:
            return None
        new = etree.SubElement(row, Q("c"), r=ref)
        return new

    def style_of(self, ref):
        c = self.cell(ref, create=False)
        return c.get("s") if c is not None else None

    def set(self, ref, value, style=None, formula=None):
        c = self.cell(ref)
        keep = c.get("s") if style is None else style
        for k in list(c.attrib):
            if k not in ("r",):
                del c.attrib[k]
        for ch in list(c):
            c.remove(ch)
        if keep:
            c.set("s", keep)
        if formula is not None:
            etree.SubElement(c, Q("f")).text = formula.lstrip("=")
        elif value is None or value == "":
            pass
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            etree.SubElement(c, Q("v")).text = repr(value) if isinstance(value, float) else str(value)
        else:
            c.set("t", "inlineStr")
            is_ = etree.SubElement(c, Q("is"))
            t = etree.SubElement(is_, Q("t"))
            t.text = str(value)
            if t.text != t.text.strip():
                t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    def clear_cols(self, first_col, last_col, from_row):
        lo, hi = col_idx(first_col), col_idx(last_col)
        for n, row in self.rows.items():
            if n < from_row:
                continue
            for c in row.findall(Q("c")):
                if lo <= col_idx(split_ref(c.get("r"))[0]) <= hi:
                    row.remove(c)

    def bytes(self):
        return etree.tostring(self.tree, xml_declaration=True, encoding="UTF-8", standalone=True)


def _sheet_paths(files):
    wb = etree.fromstring(files["xl/workbook.xml"])
    rels = etree.fromstring(files["xl/_rels/workbook.xml.rels"])
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = {}
    for s in wb.find(Q("sheets")):
        t = target[s.get(f"{{{RNS}}}id")]
        out[s.get("name")] = posixpath.normpath(posixpath.join("xl", t)) if not t.startswith("/") else t[1:]
    return out


def fill(template_path, out_path, rows, columns, survey=None, summary_sentence=None):
    with zipfile.ZipFile(template_path) as z:
        files = {n: z.read(n) for n in z.namelist()}
        order = z.namelist()
    paths = _sheet_paths(files)

    # 1) 데이터 시트
    sh = Sheet(files[paths[DATA_SHEET]])
    styles = [sh.style_of(f"{col_name(i + 1)}2") for i in range(len(columns))]
    last = col_name(len(columns))
    sh.clear_cols("A", last, 2)
    for i, r in enumerate(rows, start=2):
        for j, h in enumerate(columns):
            v = r.get(h, "")
            sh.set(f"{col_name(j + 1)}{i}", v if v != "" else None, style=styles[j])
    end = len(rows) + 1
    af = sh.tree.find(Q("autoFilter"))
    if af is not None:
        af.set("ref", f"A1:{last}{max(end, 2)}")
    files[paths[DATA_SHEET]] = sh.bytes()

    # 2) 설문 시트 — 문항 i의 응답 수는 (11 + 2i)행 C:G
    if survey and SURVEY_SHEET in paths:
        sv = Sheet(files[paths[SURVEY_SHEET]])
        sv.set("B5", int(survey["조사인원"] or 0))
        for i, item in enumerate(survey["항목"]):
            r = 11 + 2 * i
            for j, v in enumerate(item["응답"]):
                sv.set(f"{'CDEFG'[j]}{r}", int(v))
                sv.set(f"{'CDEFG'[j]}{r - 1}", None, formula=f"={'CDEFG'[j]}{r}/$B$5")
        # 양식에 값으로 덮여 있던 종합 칸(F22 등)도 수식으로 되돌림
        for j, col in enumerate("CDEFG"):
            sv.set(f"{col}22", None, formula=f"=(SUM({col}10:{col}21)/6)/$B$5*100")
        if summary_sentence:
            sv.set("A24", summary_sentence)
        files[paths[SURVEY_SHEET]] = sv.bytes()

    # 3) 이름 정의(필터 범위)·재계산·피벗 새로고침
    wb = files["xl/workbook.xml"].decode("utf-8")
    sheet_name = re.escape(DATA_SHEET)
    wb = re.sub(rf"('{sheet_name}'!\$A\$1:\$[A-Z]+\$)\d+", rf"\g<1>{max(end, 2)}", wb)
    if "<calcPr" in wb:
        wb = re.sub(r"<calcPr([^/]*)/>", lambda m: "<calcPr" + re.sub(r'\s*fullCalcOnLoad="[^"]*"', "", m.group(1)) + ' fullCalcOnLoad="1"/>', wb)
    files["xl/workbook.xml"] = wb.encode("utf-8")
    for n in list(files):
        if n.startswith("xl/pivotCache/pivotCacheDefinition") and n.endswith(".xml"):
            x = files[n].decode("utf-8")
            if "refreshOnLoad" not in x:
                x = x.replace("<pivotCacheDefinition ", '<pivotCacheDefinition refreshOnLoad="1" ', 1)
            files[n] = x.encode("utf-8")
    # 수식 셀 위치가 바뀌었을 수 있으므로 calcChain 제거(엑셀이 다시 만든다)
    if "xl/calcChain.xml" in files:
        del files["xl/calcChain.xml"]
        order.remove("xl/calcChain.xml")
        rels = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
        files["xl/_rels/workbook.xml.rels"] = re.sub(r"<Relationship [^>]*calcChain[^>]*/>", "", rels).encode("utf-8")
        ct = files["[Content_Types].xml"].decode("utf-8")
        files["[Content_Types].xml"] = re.sub(r"<Override [^>]*calcChain[^>]*/>", "", ct).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in order:
            z.writestr(n, files[n])
    with open(out_path, "wb") as f:
        f.write(buf.getvalue())
