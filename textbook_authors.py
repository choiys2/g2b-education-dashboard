#!/usr/bin/env python3
"""
교과서 저자 DB(관리 탭 '📚 교과서 저자' 칸 + CP '초등 교원양성대학' 카드의 연결 지점).

  원자료: 비공개 저장소 strategy_room/textbook_authors.json (채팅으로 갱신) - 공개 저장소에는 이름·소속이 없다.
  개인 식별 번호·학교코드는 원자료에서부터 옮기지 않는다(이름·소속·직책·지역·과목·도서만).
  관리 칸: 관리 비밀번호 암호문 안에 data-p 로 들어가고, 검색·보기 전환은 템플릿의 tbAuthorsInit 이 그린다.
  CP 카드: 교원양성대학 교수 중 저자만 '과목 + 이름'(로그인 화면에서만, industry_view 가 붙인다).
"""
import html
import json
import re

E = html.escape


def load():
    try:
        from strategy_room import _private
        d = _private()
        f = d / "strategy_room" / "textbook_authors.json" if d else None
        return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None
    except Exception:
        return None


def category(org):
    o = org or ""
    if re.search(r"부설|부속", o):
        return "학교"
    if "대학" in o:
        return "대학"
    if re.search(r"학교|캠퍼스", o):
        return "학교"
    if re.search(r"교육청|지원청", o):
        return "교육청"
    return "기관·기타"


def univ_key(org):
    """'서울교육대학교 교육전문대학원' → '서울교육대학교', '(전)…' 는 그대로."""
    m = re.match(r"^(.*?대학교|.*?대학)(?:\s|$)", (org or "").strip())
    return m.group(1) if m and not org.startswith("(전)") else (org or "").strip()


def is_prof(role):
    return "교수" in (role or "") and "(전)" not in (role or "")


def _edu_keys():
    try:
        from pathlib import Path
        D = json.loads((Path(__file__).resolve().parent / "static_data/industry_trend_2027.json").read_text(encoding="utf-8"))
        return [(u.get("match") or u["name"]) for u in D.get("universities_edu") or []]
    except Exception:
        return []


def edu_univ_authors(data=None):
    """교원양성대학 13곳 키 → [{s: 과목, n: 이름}] (교수만, 과목 확인된 사람 먼저)."""
    data = data or load()
    if not data:
        return {}
    out = {}
    for k in _edu_keys():
        rows = []
        for a in data.get("authors") or []:
            if univ_key(a.get("o")) == k and is_prof(a.get("r")):
                subj = {}
                for b in a.get("b") or []:  # 과목별 학교급: 음악(중·고)
                    lv = subj.setdefault(b["s"], [])
                    if b["lv"][:1] not in lv:
                        lv.append(b["lv"][:1])
                rows.append({"s": " · ".join(f"{k}({'·'.join(v)})" for k, v in subj.items()), "n": a["n"]})
        rows.sort(key=lambda r: (not r["s"], r["n"]))
        if rows:
            out[k] = rows
    return out


def build(sec=None):
    data = load()
    if not data:
        return ""
    A = data.get("authors") or []
    edu = set(_edu_keys())
    rows = []
    for a in A:
        cat = category(a.get("o"))
        uk = univ_key(a.get("o")) if cat == "대학" else ""
        rows.append({"n": a.get("n", ""), "o": a.get("o", ""), "r": a.get("r", ""), "g": a.get("g", ""), "c": cat, "u": uk,
                     "e": 1 if uk in edu else 0, "b": a.get("b") or []})
    n_prof = sum(1 for r in rows if r["c"] == "대학" and is_prof(r["r"]))
    n_edu = sum(1 for r in rows if r["e"] and is_prof(r["r"]))
    n_tch = sum(1 for r in rows if r["c"] == "학교")
    n_rep = sum(1 for r in rows if r["b"])
    lv = data.get("books_by_level") or {}
    payload = {"rows": rows, "edu": sorted(edu)}
    tiles = "".join(f'<div style="flex:1 1 120px;min-width:0;border:1px solid var(--border);border-radius:10px;padding:8px 10px;background:var(--surface-2);">'
                    f'<div style="font-size:11.5px;color:var(--muted);">{E(k)}</div><b style="font-size:20px;">{v}</b></div>'
                    for k, v in [("저자 전체", f"{len(rows)}명"), ("대표저자", f"{n_rep}명"), ("대학 교수", f"{n_prof}명"),
                                 ("교원양성대학 교수", f"{n_edu}명"), ("현직 교사", f"{n_tch}명"),
                                 ("도서", f"{data.get('books_total', 0)}종")])
    return (
        '<section class="panel"><div class="panel-head"><div>'
        f'<p class="panel-title">📚 교과서 저자 <span style="font-size:12px;font-weight:600;color:var(--muted);margin-left:6px;">'
        f'{E(data.get("title", ""))} · 원자료 {E(data.get("source_date", ""))} · 반영 {E(data.get("updated", ""))}</span></p>'
        '<p class="panel-desc">비상교육 22개정 교과서·지도서·전자저작물 저자를 대학순·교과순으로 봅니다. 이름·소속·과목·도서명으로 검색하세요. '
        f'도서 초등 {lv.get("초등학교", 0)} · 중학 {lv.get("중학교", 0)} · 고등 {lv.get("고등학교", 0)}종.</p></div></div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">{tiles}</div>'
        f'<div id="tbAuthors" data-p="{E(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))}">'
        '<p style="color:var(--muted);font-size:13px;">저자 목록을 불러오는 중입니다.</p></div>'
        f'<p class="tt-note">{E(data.get("note", ""))} 개인 식별 번호·학교코드는 옮기지 않았습니다. '
        '연수 강사·자문·공동 개발 섭외 때 소속 대학·과목을 먼저 확인하는 용도입니다.</p></section>')


if __name__ == "__main__":
    d = load()
    print("원자료", "있음" if d else "없음")
    for k, v in edu_univ_authors(d).items():
        print(k, v)
