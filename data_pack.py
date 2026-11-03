#!/usr/bin/env python3
"""
대시보드 데이터 팩 - vs-insight.pages.dev/full/ 의 모든 탭 데이터를 '채팅에서 검색·인용하기 좋은' Markdown(+전체 CSV)으로
비공개 저장소(vs-insight-private)의 data_pack/ 에 매일 저장한다. Claude 채팅 프로젝트 지식으로 연결해 검색·질의·PPT 근거로 쓴다.

- 입력: live/data_pack_raw.json(combine_dashboard.py 가 화면에 넣은 데이터 그대로), live/owner_pack.json(대표 전용)
- 출력: <out>/index.md(목차·기준일·사용법), <out>/NN_탭이름.md(표는 파일당 최대 MAX_ROWS행),
        <out>/csv/*.csv(잘린 표의 전체 행 - 엑셀·차트·PPT 수치용)
- 공개 저장소·사이트에는 쓰지 않는다. deploy.yml 이 _private/data_pack 으로만 넘긴다.
  python data_pack.py _private/data_pack
"""
import csv
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
MAX_ROWS = 300        # Markdown 표 한 개 최대 행(나머지는 CSV)
MAX_COLS = 14
MAX_CELL = 160
MAX_FILE = 700_000    # Markdown 파일 한 개 최대 글자 수

# (파일 번호·이름, 화면 탭, 설명, [데이터 키])
GROUPS = [
    ("00_경영종합_대표전용", "관리 🔒", "경영 종합 지표·AI 브리핑·경쟁사 변화 감지·결과보고 현황(대표 전용)", ["__OWNER__"]),
    ("01_시장분석", "시장 분석", "시도별 학교·교원 현황과 합계", ["__DATA_JSON__", "__TOTALS_JSON__"]),
    ("02_AI에듀테크_발주리스트", "AI·에듀테크 발주 리스트", "교육청·연수원 AI·에듀테크 관련 입찰공고·사전규격·낙찰(스코어 포함)", ["__AI_ROWS_JSON__"]),
    ("03_나라장터_종합", "나라장터 종합", "나라장터 교육 분야 종합 집계", ["__G2B_FULL_JSON__", "__G2B_STALE_JSON__"]),
    ("04_AI중점_선도학교", "AI 중점·선도학교", "AI 중점·선도학교 목록·지역별 현황", ["__LEADING_ROWS_JSON__", "__LEADING_BY_REGION_JSON__", "__AI_SCHOOL_STATUS_JSON__"]),
    ("05_경쟁사", "경쟁사 연수 분석", "경쟁사 연수 과정·계약(수의 포함)·배너 점유", ["__COMPETITOR_TRAINING_JSON__", "__CONTRACTS_JSON__", "__BANNER_JSON__"]),
    ("06_교사트렌드_연수주제", "교사 트렌드 2027", "연수 주제별 수요·성장·자사/경쟁사 커버리지, 교사 트렌드 2027 키워드", ["__TRAINING_TOPICS_JSON__", "__TREND2027_JSON__"]),
    ("07_B2G영업_파이프라인", "B2G영업", "자사 파이프라인·영업 소통·제안요청서 AI 분석·조기 경보·운영 현황", ["__PIPE_JSON__", "__PIPE_COMMS_JSON__", "__RFP_JSON__", "__EARLY_WARNING_JSON__", "__OPS_JSON__", "__SHEETS_OPS_JSON__", "__VIZ_JSON__"]),
    ("08_B2S_샘몰", "B2S·샘몰 기획", "학교 시장(학교알리미)·학교 타깃 레이더·샘몰 상품 우선순위", ["__B2S_MARKET_JSON__", "__B2S_BOARD_JSON__"]),
    ("09_콘텐츠_매출_교육재정", "콘텐츠·매출", "2026 매출 현황·교육청 재정(KOSIS)", ["__REV26_JSON__", "__KOSIS_FINANCE_JSON__"]),
    ("10_KERIS조달", "KERIS 조달", "KERIS 조달 현황", ["__KERIS_JSON__"]),
    ("11_교원연수_이수현황", "교원연수 이수 현황", "NETI 교원연수 이수 현황", ["__NETI_JSON__"]),
    ("12_학교단위_발주", "학교단위 발주", "학교·교육청 수의계약(학교단위 발주)", ["__EDU_CNTR_JSON__"]),
    ("13_베타", "베타 기능", "경쟁사 트렌드·파이프라인 모멘텀·낙찰가 추정·추세 예측(베타)", ["__BETA_JSON__"]),
    ("14_집합연수_장소_날씨", "B2G영업(집합연수)", "집합연수 후보 장소·지역 날씨", ["__TOUR_JSON__", "__WEATHER_JSON__"]),
]
LABEL = {
    "__OWNER__": "대표 전용 묶음", "__DATA_JSON__": "시도별 학교 데이터", "__TOTALS_JSON__": "합계",
    "__AI_ROWS_JSON__": "AI·에듀테크 발주 건", "__G2B_FULL_JSON__": "나라장터 종합", "__G2B_STALE_JSON__": "대체 수집 표시",
    "__LEADING_ROWS_JSON__": "선도학교 목록", "__LEADING_BY_REGION_JSON__": "지역별 선도학교", "__AI_SCHOOL_STATUS_JSON__": "AI 학교 현황",
    "__COMPETITOR_TRAINING_JSON__": "경쟁사 연수 과정", "__CONTRACTS_JSON__": "계약정보(경쟁사·자사)", "__BANNER_JSON__": "배너 점유",
    "__TRAINING_TOPICS_JSON__": "연수 주제 수요", "__TREND2027_JSON__": "교사 트렌드 2027",
    "__PIPE_JSON__": "자사 파이프라인", "__PIPE_COMMS_JSON__": "영업 소통", "__RFP_JSON__": "제안요청서 AI 분석",
    "__EARLY_WARNING_JSON__": "조기 경보", "__OPS_JSON__": "운영 현황", "__SHEETS_OPS_JSON__": "시트 운영 데이터", "__VIZ_JSON__": "시각화 집계",
    "__B2S_MARKET_JSON__": "학교 시장", "__B2S_BOARD_JSON__": "B2S 보드", "__REV26_JSON__": "2026 매출", "__KOSIS_FINANCE_JSON__": "교육청 재정",
    "__KERIS_JSON__": "KERIS 조달", "__NETI_JSON__": "교원연수 이수", "__EDU_CNTR_JSON__": "학교단위 수의계약", "__BETA_JSON__": "베타",
    "__TOUR_JSON__": "집합연수 장소", "__WEATHER_JSON__": "날씨",
}


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def _scalar(v):
    return v is None or isinstance(v, (str, int, float, bool))


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        s = f"{v:,.2f}".rstrip("0").rstrip(".")
    elif isinstance(v, int) and not isinstance(v, bool):
        s = f"{v:,}" if abs(v) >= 10000 else str(v)
    elif _scalar(v):
        s = str(v)
    else:
        s = json.dumps(v, ensure_ascii=False, default=str)
    s = re.sub(r"\s+", " ", s).replace("|", "/")
    return s[:MAX_CELL] + ("…" if len(s) > MAX_CELL else "")


def _slug(s):
    return re.sub(r"[^0-9A-Za-z가-힣_]+", "_", s).strip("_")[:60] or "data"


class Writer:
    def __init__(self, out, stem):
        self.out, self.stem, self.lines, self.csvs, self.rows = out, stem, [], [], 0

    def table(self, rows, path):
        cols = [k for k, _ in Counter(k for r in rows for k, v in r.items() if _scalar(v) or isinstance(v, (list, dict))).most_common()]
        # 짧은 값(스칼라) 열을 앞에, 열 수 제한
        cols = sorted(cols, key=lambda k: -sum(1 for r in rows if _scalar(r.get(k)) and r.get(k) not in (None, "")))[:MAX_COLS]
        if not cols:
            return
        self.rows += len(rows)
        shown = rows[:MAX_ROWS]
        self.lines += [f"_{len(rows):,}행 · 열 {len(cols)}개" + (f" · 앞 {MAX_ROWS}행만 표시(전체는 CSV)" if len(rows) > MAX_ROWS else "") + "_", "",
                       "| " + " | ".join(_cell(c) for c in cols) + " |", "|" + "---|" * len(cols)]
        self.lines += ["| " + " | ".join(_cell(r.get(c)) for c in cols) + " |" for r in shown]
        self.lines.append("")
        if len(rows) > MAX_ROWS or len({k for r in rows for k in r}) > MAX_COLS:
            allc = list(dict.fromkeys(k for r in rows for k in r))
            name = f"{self.stem}__{_slug(path)}.csv"
            (self.out / "csv").mkdir(exist_ok=True)
            with open(self.out / "csv" / name, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(allc)
                for r in rows:
                    w.writerow([v if _scalar(v) else json.dumps(v, ensure_ascii=False, default=str) for v in (r.get(c) for c in allc)])
            self.csvs.append((name, len(rows)))
            self.lines += [f"→ 전체 데이터: `csv/{name}` ({len(rows):,}행, 열 {len(allc)}개)", ""]

    def render(self, obj, title, depth, path):
        h = "#" * min(depth, 6)
        if obj is None or obj == {} or obj == []:
            return
        if _scalar(obj):
            self.lines += [f"- **{title}**: {_cell(obj)}"]
            return
        if isinstance(obj, list):
            if obj and all(isinstance(x, dict) for x in obj):
                self.lines += ["", f"{h} {title}", ""]
                self.table(obj, path)
            elif all(_scalar(x) for x in obj):
                vals = ", ".join(_cell(x) for x in obj[:200])
                self.lines += [f"- **{title}** ({len(obj)}개): {vals}" + (" …" if len(obj) > 200 else "")]
            else:
                self.lines += ["", f"{h} {title}", ""]
                for i, x in enumerate(obj[:100]):
                    self.render(x, f"{title} [{i + 1}]", depth + 1, f"{path}_{i}")
            return
        # dict
        sc = {k: v for k, v in obj.items() if _scalar(v)}
        nest = {k: v for k, v in obj.items() if not _scalar(v)}
        # 값이 전부 dict 인 dict(예: 지역→지표)는 표 하나로 펼친다
        if nest and not sc and len(nest) >= 3 and all(isinstance(v, dict) and all(_scalar(x) for x in v.values()) for v in nest.values()):
            self.lines += ["", f"{h} {title}", ""]
            self.table([{"key": k, **v} for k, v in nest.items()], path)
            return
        self.lines += ["", f"{h} {title}", ""]
        if sc:
            self.lines += [f"- **{k}**: {_cell(v)}" for k, v in sc.items()] + [""]
        for k, v in nest.items():
            if depth >= 6:
                self.lines.append(f"- **{k}**: {_cell(v)}")
            else:
                self.render(v, str(k), depth + 1, f"{path}_{k}")


def build(out):
    raw = {}
    try:
        raw = json.loads((HERE / "live/data_pack_raw.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("[경고] live/data_pack_raw.json 없음 - 대표 전용 묶음만 시도")
    try:
        raw["__OWNER__"] = json.loads((HERE / "live/owner_pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if out.exists():
        shutil.rmtree(out)  # 어제 파일 중 오늘 사라진 표가 남지 않게 통째로 다시 쓴다
    out.mkdir(parents=True)
    today = _today().isoformat()
    idx = []
    for stem, tab, desc, keys in GROUPS:
        w = Writer(out, stem)
        w.lines += [f"# {stem.split('_', 1)[1].replace('_', ' ')} — {today}", "",
                    f"> 대시보드 탭: **{tab}** · {desc}", "> 출처: vs-insight.pages.dev/full/ (매일 06시 자동 갱신) · 대표 전용 · 외부 공유 금지", ""]
        has = False
        for k in keys:
            v = raw.get(k)
            if v in (None, {}, []):
                continue
            has = True
            w.render(v, LABEL.get(k, k), 2, k.strip("_").lower())
        if not has:
            continue
        text = "\n".join(w.lines) + "\n"
        if len(text) > MAX_FILE:
            text = text[:MAX_FILE] + f"\n\n_…파일 크기 한도로 여기서 자름. 전체 수치는 csv/ 폴더 참고._\n"
        (out / f"{stem}.md").write_text(text, encoding="utf-8")
        idx.append((stem, tab, desc, w.rows, w.csvs, len(text)))
    lines = [f"# 대시보드 데이터 팩 — {today}", "",
             "> vs-insight.pages.dev/full/ 의 모든 탭 데이터를 매일 06시에 자동으로 옮긴 것입니다(대표 전용 · 외부 공유 금지).",
             "> 해석·요약은 `exec_pack/latest.md`, 원자료 검색·표·수치는 이 폴더를 쓰세요.", "",
             "## 파일 목록", "", "| 파일 | 대시보드 탭 | 내용 | 표 행 수 | 전체 CSV |", "|---|---|---|---|---|"]
    for stem, tab, desc, n, csvs, size in idx:
        lines.append(f"| `{stem}.md` | {tab} | {desc} | {n:,} | {', '.join(f'`csv/{c}`' for c, _ in csvs) or '-'} |")
    lines += ["", "## 채팅·PPT 활용 요령",
              "- 질문에 탭 이름이나 파일 번호를 넣으면 정확도가 올라갑니다. 예: \"05_경쟁사 기준으로 아이스크림·티처빌 계약 비교표\"",
              "- PPT: \"02·05·07 파일 근거로 B2G 시장 현황 6장 슬라이드, 각 장 출처 파일명 표기\"",
              "- 수치를 인용할 때는 파일 맨 위 기준일을 함께 적습니다.",
              "- 표가 300행에서 잘린 경우 같은 이름의 CSV 에 전체 행이 있습니다(엑셀·차트용)."]
    (out / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return idx


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "_private/data_pack")
    idx = build(out)
    print(f"데이터 팩 {len(idx)}개 파일 → {out} · " + ", ".join(f"{s}({n:,}행)" for s, _, _, n, _, _ in idx))
