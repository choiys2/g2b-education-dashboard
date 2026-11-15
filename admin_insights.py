#!/usr/bin/env python3
"""
관리 탭 추가 칸(관리 비밀번호 암호문 안에만 실린다 - admin_structure.build_html 에서 호출)

  - build_edu(sec): '교육청 인사이트' 칸 = A5 교육청 2027 정책 신호(시도×주제) + A4 지역별 유입×수주(GA4 연결 전 안내)
  - build_ops(sec): '시스템 구조' 칸 맨 위 = B1 수집 장애 감시 이력 + B4 대시보드 사용 분석
모든 외부 텍스트는 html.escape, 링크는 https 만, 새 창은 noopener noreferrer.
"""
import html
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
E = html.escape
SIDO = ["서울", "부산", "대구", "인천", "전남광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
NOTE = "color:var(--muted);font-size:12.5px;"


def _jsonl(p):
    f = HERE / p
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def _link(u, t):
    if u.startswith("https://") or u.startswith("http://"):
        return f'<a href="{E(u)}" target="_blank" rel="noopener noreferrer">{E(t)}</a>'
    return E(t)


def build_edu(sec, days=60):
    try:
        import training_topics as tt
        names = {tid: nm for tid, nm, *_ in tt.TOPICS}
    except Exception:  # noqa: BLE001
        names = {}
    rows = [r for r in _jsonl("history/edu_office_signals.jsonl") if (r.get("d") or "") >= (date.today() - timedelta(days=days)).isoformat()]
    if not rows:
        a5 = sec("교육청 2027 정책 신호", "에듀테크 레이더의 교육청 기사를 시도 × 연수 주제로 쌓습니다. 첫 누적 전입니다.", f'<p style="{NOTE}">다음 배포부터 매일 쌓입니다.</p>')
    else:
        cnt = Counter((r["s"], tp) for r in rows for tp in (r.get("tp") or ["-"]))
        tops = [t for t, _ in Counter(tp for r in rows for tp in (r.get("tp") or [])).most_common(10)]
        per = Counter(r["s"] for r in rows)
        plan = Counter(r["s"] for r in rows if r.get("plan"))
        mx = max(cnt.values()) if cnt else 1
        cell = lambda n: (f'<td class="num" style="background:color-mix(in srgb, var(--accent) {min(70, 12 + 58 * n // mx)}%, transparent);">{n}</td>'
                          if n else '<td class="num" style="color:var(--muted);">·</td>')
        head = "".join(f"<th class='num'>{E(names.get(t, t))}</th>" for t in tops)
        body = "".join(f"<tr><td><b>{E(s)}</b></td><td class='num'>{per[s]}</td><td class='num'>{plan[s] or '·'}</td>" + "".join(cell(cnt[(s, t)]) for t in tops) + "</tr>"
                       for s in sorted(SIDO, key=lambda x: -per[x]) if per[s])
        recent = defaultdict(list)
        for r in sorted(rows, key=lambda r: r.get("d") or "", reverse=True):
            if r.get("plan") and len(recent[r["s"]]) < 3:
                recent[r["s"]].append(r)
        lst = "".join(f"<tr><td style='white-space:nowrap;'><b>{E(s)}</b></td><td>" + "<br>".join(f"<span style='{NOTE}'>{E(x['d'])}</span> {_link(x.get('u', ''), x['t'])}" for x in recent[s]) + "</td></tr>"
                      for s in sorted(recent, key=lambda x: -plan[x]))
        quiet = [s for s in SIDO if not per[s]]
        a5 = sec("교육청 2027 정책 신호 (시도 × 연수 주제)",
                 f"최근 {days}일 교육청 기사 {len(rows)}건을 시도·연수 주제로 분류했습니다. '계획 신호' = 2027·내년·시행계획·정책연구·예산이 들어간 기사(다음 해 발주의 선행 신호). 해석: 진한 칸일수록 그 교육청이 해당 주제를 자주 내세우는 중 → 제안 주제 우선순위로 쓰세요. 각 교육청 '2027 주요업무계획' 원문은 보통 1~2월 공개 - 공개되면 이 표에 원문 기준 주제를 덧붙입니다.",
                 f"<div class='tbl-wrap'><table><thead><tr><th>시도</th><th class='num'>기사</th><th class='num'>계획 신호</th>{head}</tr></thead><tbody>{body}</tbody></table></div>"
                 + (f"<p style='{NOTE}margin-top:6px;'>최근 {days}일 기사 없음: {E(' · '.join(quiet))} — 레이더 수집 범위 밖일 수 있어 '관심 없음'으로 단정하지 마세요.</p>" if quiet else "")
                 + (f"<h4>시도별 최근 계획 신호(최대 3건)</h4><div class='tbl-wrap'><table><tbody>{lst}</tbody></table></div>" if lst else ""))
    a4 = sec("지역별 비바샘 관심도 × 나라장터 수주 (준비 중)",
             "시도별 비바샘 유입(GA4·검색)과 교육청 수주를 나란히 놓아 '관심은 높은데 수주가 없는 지역'을 찾는 칸입니다.",
             f'<p style="{NOTE}">비바샘 GA4·검색 콘솔이 아직 연결되지 않았습니다(Windsor.ai 에는 인스타그램만 연결). 회사 마케팅·IT팀에서 GA4 보기 권한을 받아 Windsor.ai 에 연결하면 이 칸이 채워집니다.</p>')
    return a5 + a4


def build_ops(sec):
    w = _jsonl("history/pipeline_watch.jsonl")
    full = [r for r in w if not r.get("quick")][-14:]
    if full:
        last = full[-1]
        badge = "✅ 정상" if last["status"] == "ok" else "❌ 장애: " + ", ".join(last.get("fail") or [])
        rows = "".join(f"<tr><td style='white-space:nowrap;'>{E(r['at'])}</td><td>{'✅' if r['status'] == 'ok' else '❌'}</td><td>{E(', '.join(r.get('fail') or []) or '-')}</td>"
                       f"<td>{E(next((c['m'] for c in r.get('checks', []) if c['n'] == '나라장터 건전성'), '-'))}</td><td>{E(r.get('sentry', '-'))}</td></tr>" for r in reversed(full))
        b1 = sec("수집 장애 감시 (매일)", f"마지막 수집 실행 {E(last['at'])} · {E(badge)}. 나라장터 건전성·입찰공고/낙찰 0건·대시보드 조합·Cloudflare 배포 중 하나라도 실패하면 Sentry 가 메일로 알립니다(무료 감시 1개).",
                 f"<div class='tbl-wrap'><table><thead><tr><th>실행</th><th>상태</th><th>실패 항목</th><th>나라장터 건수</th><th>알림</th></tr></thead><tbody>{rows}</tbody></table></div>")
    else:
        b1 = sec("수집 장애 감시 (매일)", "다음 전체 수집부터 기록됩니다.", "")
    try:
        u = __import__("dashboard_usage").load()
    except Exception:  # noqa: BLE001
        u = None
    if u is None:
        b4 = sec("대시보드 사용 분석", "탭별 조회 수(개인정보 없이 탭 이름만).", f'<p style="{NOTE}">조회 키(POSTHOG_PERSONAL_API_KEY·POSTHOG_PROJECT_ID) 등록 전입니다. 수집은 POSTHOG_KEY 등록 후 시작됩니다.</p>')
    elif not u.get("rows"):
        b4 = sec("대시보드 사용 분석", f"최근 {u['days']}일", f'<p style="{NOTE}">아직 쌓인 조회가 없습니다{(" (조회 오류: " + E(u["error"]) + ")") if u.get("error") else ""}.</p>')
    else:
        tot = sum(r["views"] for r in u["rows"]) or 1
        rows = "".join(f"<tr><td>{E(r['tab'])}</td><td class='num'>{r['views']:,}</td><td class='num'>{r['views'] * 100 // tot}%</td><td class='num'>{r['sessions']:,}</td><td>{E(r['last'])}</td></tr>" for r in u["rows"])
        b4 = sec("대시보드 사용 분석", f"최근 {u['days']}일 탭별 조회(개인정보 없이 탭 이름·임시 세션 번호만). 해석: 하위 탭은 통합·정리 후보, 상위 탭은 첫 화면 배치 후보.",
                 f"<div class='tbl-wrap'><table><thead><tr><th>탭</th><th class='num'>조회</th><th class='num'>비중</th><th class='num'>세션</th><th>마지막</th></tr></thead><tbody>{rows}</tbody></table></div>")
    return b1 + b4
