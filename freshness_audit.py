#!/usr/bin/env python3
"""
주간 데이터 신선도 재검토(사용자 지시 2026-11-22 "상위 내용은 일주일에 한 번 재검토") - 대화·점검용, 배포에는 쓰지 않는다.
1) freshness.tabs(): 탭별 자료 기준일·상태(지연·중단·오래됨·새 자료 없음·없음)
2) git 이력: 날짜만 바뀌고 '내용'은 그대로인 자료(시각 키를 빼고 비교) - 깊은 이력이 필요하다(git fetch --deepen=1500)
사용: python3 freshness_audit.py [--md out.md]   (출력은 한국어 마크다운)
"""
import glob
import hashlib
import json
import re
import subprocess
import sys
from datetime import date

import freshness

TS = re.compile(r"(generated|updated|date|collected_at|captured|checked|_at$|^at$|asof|as_of|time|run|last|stamp|ts$)", re.I)


def _norm(o):
    if isinstance(o, dict):
        return {k: _norm(v) for k, v in sorted(o.items()) if not TS.search(k)}
    if isinstance(o, list):
        return [_norm(x) for x in o]
    return o


def _hash(txt, jsonl):
    try:
        o = [json.loads(x) for x in txt.splitlines() if x.strip()] if jsonl else json.loads(txt)
        return hashlib.md5(json.dumps(_norm(o), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    except ValueError:
        return hashlib.md5(txt.encode()).hexdigest()


def unchanged(min_days=14):
    """마지막 커밋은 최근인데 내용은 min_days 이상 그대로인 파일."""
    out, today = [], date.today()
    for f in sorted(glob.glob("history/*.json") + glob.glob("history/*.jsonl")):
        if f.endswith(".enc.json") or "snapshots" in f:
            continue
        cs = [c.split() for c in subprocess.run(["git", "log", "--format=%H %cs", "-n", "40", "--", f], capture_output=True, text=True).stdout.splitlines() if c.strip()]
        if len(cs) < 2:
            continue
        head = _hash(subprocess.run(["git", "show", f"{cs[0][0]}:{f}"], capture_output=True, text=True).stdout, f.endswith(".jsonl"))
        since = cs[0][1]
        for sha, d in cs[1:]:
            if _hash(subprocess.run(["git", "show", f"{sha}:{f}"], capture_output=True, text=True).stdout, f.endswith(".jsonl")) != head:
                break
            since = d
        last = cs[0][1]
        if (today - date.fromisoformat(since)).days >= min_days and (today - date.fromisoformat(last)).days <= 8:
            out.append((f, since, last))
    return out


def main():
    T = freshness.tabs()
    bad = [(k, x) for k, it in T["tabs"].items() for x in it if x["state"] != "정상"]
    order = ["중단", "오래됨", "지연", "대체본", "없음", "새 자료 없음"]
    bad.sort(key=lambda kx: order.index(kx[1]["state"]) if kx[1]["state"] in order else 9)
    L = [f"# 데이터 신선도 주간 재검토 ({T['built']} 기준)", "", "## 1. 탭별 확인 필요 자료", "",
         "| 상태 | 탭 | 자료 | 기준일 | 경과 | 주기 |", "|---|---|---|---|---|---|"]
    L += [f"| {x['state']} | {k} | {x['l']} | {x.get('at') or '-'} | {x.get('age', '-')}일 | {x['cad']} |" for k, x in bad] or ["| - | 전부 정상 | | | | |"]
    old = [x for _, x in bad if x["state"] == "오래됨"]
    L += ["", f"90일 지난 수동 자료: **{len(old)}건** " + (", ".join(f"{x['l']}({x['age']}일)" for x in old) if old else "")]
    sh = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], capture_output=True, text=True).stdout.strip() == "true"
    U = unchanged()
    L += ["", "## 2. 날짜만 바뀌고 내용은 그대로인 자료(14일 이상)", ""]
    L += [f"- {f}: 내용은 {s} 이후 그대로(마지막 커밋 {l})" for f, s, l in U] or ["- 없음"]
    if sh:
        L += ["", "※ 얕은 저장소라 2번 결과가 불완전할 수 있음(git fetch --deepen=1500 후 다시 실행)."]
    txt = "\n".join(L)
    if "--md" in sys.argv:
        open(sys.argv[sys.argv.index("--md") + 1], "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
