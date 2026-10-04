#!/usr/bin/env python3
"""
제안요청서(과업지시서) AI 분석 - 최근 교원 연수 입찰공고의 첨부문서를 Gemini로 구조화한다.

- 대상: history/training_bids.jsonl 중 최근 60일, 교원 대상, 첨부(f)가 있는 공고. 예산 큰 순.
- 첨부 중 제안요청서·과업지시서·규격서를 우선 고르고(PDF는 파일 그대로, HWP/HWPX는 본문 텍스트)
  과정명·대상·인원·운영형태·차시·평가기준·필수요건·제안 포인트를 뽑는다.
- 결과는 history/rfp_analysis.jsonl 에 누적(git 추적) - 한 번 분석한 공고는 다시 호출하지 않는다.
- 무료 등급을 고려해 1회 실행당 MAX_PER_RUN 건만 새로 분석한다.
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import doc_text
import gemini_client as gc
import training_topics as tt

HERE = Path(__file__).parent
CACHE = HERE / "history" / "rfp_analysis.jsonl"
MAX_PER_RUN = 5
DOC_PRIORITY = re.compile(r"제안\s?요청|과업|규격|사양|지시서|공고문")

PROMPT = """다음은 교육청·교육기관의 교원 연수 용역 입찰 첨부문서(제안요청서·과업지시서 등)다.
문서에 적힌 내용만 근거로 아래 JSON을 한국어로 채워라. 문서에 없으면 빈 문자열이나 빈 배열로 둔다. 추측하지 마라.
{"course": "연수(사업)명", "target": "대상(학교급·교원 유형)", "headcount": "인원", "format": "운영형태(원격/집합/혼합, 출강 등)",
 "period": "운영 기간", "hours": "시간·차시·학점", "budget": "사업 예산(문서 표기 그대로)",
 "requirements": ["핵심 과업 요구사항(최대 6개, 각 40자 이내)"], "qualifications": ["참가자격·실적 요건(최대 4개)"],
 "evaluation": "평가 방식(예: 협상에 의한 계약, 기술 90:가격 10)", "deliverables": ["산출물(최대 4개)"],
 "pitch": ["원격교육연수원이 제안할 때 강조할 포인트(문서 요구사항 기반, 최대 3개, 각 50자 이내)"]}
공고명: """


def load_cache():
    out = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    out[r["k"]] = r
                except (json.JSONDecodeError, KeyError):
                    pass
    return out


def download(url, timeout=40):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 g2b-education-dashboard"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(25_000_000)


def norm_title(t):
    """재공고·긴급 표기를 지워 같은 사업을 한 번만 분석한다."""
    return re.sub(r"\[[^\]]*\]|\([^)]*공고[^)]*\)|재공고|긴급|\s|[「」『』\"'.·,]", "", t or "")


def relevant(r):
    return tt.is_training_bid(r["t"], r.get("o", "")) and tt.classify_audience(r["t"]) != "학생"


def candidates(cache, days=60):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    seen = {norm_title(v["t"]) for v in cache.values()}
    rows = sorted([r for r in tt.load_history().values()
                   if r.get("f") and (r.get("d") or "") >= cutoff and r["k"] not in cache and relevant(r)],
                  key=lambda r: (-(r.get("a") or 0), r["d"]))
    out = []
    for r in rows:
        nt = norm_title(r["t"])
        if nt not in seen:
            seen.add(nt)
            out.append(r)
    return out


def analyze(row):
    docs = sorted(row["f"], key=lambda d: (0 if DOC_PRIORITY.search(d[0] or "") else 1))
    tried = []
    for name, url in docs[:3]:
        try:
            data = download(url)
        except Exception as e:
            tried.append(f"{name}: 다운로드 실패 {str(e)[:60]}")
            continue
        kind, mime, payload = doc_text.to_gemini_input(data, name)
        if not kind:
            tried.append(f"{name}: {payload}")
            continue
        prompt = PROMPT + row["t"] + "\n기관: " + row.get("o", "")
        if kind == "file":
            res = gc.generate_json(prompt, files=[(mime, payload)])
        else:
            res = gc.generate_json(prompt + "\n\n문서 본문:\n" + payload[:40000])
        return res, name, tried
    return None, None, tried


def main():
    if not gc.key():
        print("[경고] GEMINI_API_KEY 없음 - 제안요청서 분석 건너뜀", file=sys.stderr)
        return
    cache = {k: v for k, v in load_cache().items() if relevant(v)}  # 판정 규칙이 바뀌면(예: 국제교류 제외) 기존 결과도 정리
    todo = candidates(cache)[:MAX_PER_RUN]
    done = 0
    for row in todo:
        try:
            res, doc, tried = analyze(row)
        except Exception as e:
            res, doc, tried = None, None, [gc.mask(e)[:160]]
        rec = {"k": row["k"], "t": row["t"], "o": row.get("o", ""), "r": row.get("r", ""), "d": row["d"],
               "a": row.get("a") or 0, "u": row.get("u", ""), "doc": doc, "at": date.today().isoformat()}
        if res:
            rec["ai"] = res
            done += 1
        else:
            rec["skip"] = "; ".join(tried)[:300]
            # 분석 실패도 기록해 매일 같은 문서를 다시 시도하지 않게 한다(429 같은 일시 오류는 제외)
            if any("HTTP 429" in t or "HTTP 5" in t for t in tried):
                continue
        cache[row["k"]] = rec
    CACHE.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n"
                             for v in sorted(cache.values(), key=lambda v: (v["d"], v["k"]))), encoding="utf-8")
    print(f"제안요청서 분석: 이번 {len(todo)}건 시도, 성공 {done}건, 누적 {len(cache)}건")


if __name__ == "__main__":
    main()
