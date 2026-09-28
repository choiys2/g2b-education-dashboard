/*
 * 비상 영업용 뉴스 위젯 (v-edu-board 등 외부 앱 삽입용)
 *
 *   <div id="vedu-news"></div>
 *   <script src="https://choiys2.github.io/g2b-education-dashboard/widget/news-widget.js" defer></script>
 *
 * 선택 속성: data-base="https://…/api/news"  (다른 주소·프록시 사용 시. 기본은 GitHub Pages)
 *           data-tags="예산,AI·디지털"      (처음에 켜 둘 담당 분야 태그)
 *
 * 기능: ① 오늘의 토킹포인트(복사) ② 담당 분야 태그 필터 ③ 헤드라인 카드
 *       ④ 경쟁사·자사 동향 강조 ⑤ 지난 호 검색·선택
 * Shadow DOM 안에서 그리므로 앱의 CSS와 서로 간섭하지 않는다. 데이터는 모두 평문(textContent)으로 넣는다.
 */
(function () {
  'use strict';
  var DEFAULT_BASE = 'https://choiys2.github.io/g2b-education-dashboard/api/news';
  var HOT = ['경쟁사', '자사'];

  var CSS = [
    ':host{all:initial;display:block;font-family:Pretendard,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;',
    '--bg:#fff;--bg2:#f5f6f8;--ink:#15171a;--ink2:#4a4f57;--muted:#80868f;--line:#e3e5e9;--accent:#0b63ce;--warn:#b45309;--hot:#c2410c;--hotbg:#fff4ec;--ok:#15803d;}',
    '@media (prefers-color-scheme:dark){:host{--bg:#171b22;--bg2:#1f2530;--ink:#eef1f6;--ink2:#b9c0cc;--muted:#8a93a2;--line:#2c3441;--accent:#5aa6ff;--warn:#f0a44b;--hot:#ff8a4c;--hotbg:#2a1d15;--ok:#4ade80;}}',
    '.w{background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:14px;padding:16px;box-sizing:border-box;max-width:100%;}',
    '.w *{box-sizing:border-box;}',
    '.top{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;}',
    '.brand{font-size:12px;font-weight:800;color:var(--accent);letter-spacing:.02em;}',
    'select,input{font:inherit;font-size:12.5px;color:var(--ink);background:var(--bg2);border:1px solid var(--line);border-radius:8px;padding:5px 8px;}',
    '.stale{font-size:12px;color:var(--warn);background:var(--bg2);border-radius:8px;padding:6px 10px;margin-bottom:10px;}',
    '.kicker{font-size:11.5px;color:var(--muted);font-weight:700;}',
    '.head{display:block;font-size:17px;font-weight:800;line-height:1.35;color:var(--ink);text-decoration:none;margin:3px 0 4px;}',
    '.head:hover{text-decoration:underline;}',
    '.meta{font-size:11.5px;color:var(--muted);}',
    '.facts{margin:8px 0 0;padding-left:16px;font-size:13px;color:var(--ink2);line-height:1.5;}',
    '.facts li{margin:2px 0;}',
    'h4{font-size:13px;margin:16px 0 8px;display:flex;align-items:center;gap:6px;}',
    '.note{font-size:11px;font-weight:600;color:var(--muted);}',
    '.tp{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:8px;background:var(--bg2);}',
    '.tp .n{font-size:12.5px;color:var(--ink2);}',
    '.tp .s{font-size:13.5px;font-weight:700;margin-top:4px;line-height:1.45;}',
    '.tp .row{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;}',
    'button{font:inherit;cursor:pointer;}',
    '.copy{flex:none;font-size:11.5px;border:1px solid var(--line);background:var(--bg);color:var(--ink2);border-radius:6px;padding:3px 8px;}',
    '.copy.done{color:var(--ok);border-color:var(--ok);}',
    '.chips{display:flex;flex-wrap:wrap;gap:6px;}',
    '.chip{font-size:12px;border:1px solid var(--line);background:var(--bg);color:var(--ink2);border-radius:999px;padding:4px 10px;}',
    '.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700;}',
    '.chip.hot[aria-pressed="false"]{border-color:var(--hot);color:var(--hot);}',
    '.items{margin-top:10px;display:flex;flex-direction:column;gap:8px;}',
    '.it{border-left:3px solid var(--line);padding:4px 0 4px 10px;}',
    '.it.hot{border-left-color:var(--hot);background:var(--hotbg);border-radius:0 8px 8px 0;}',
    '.it .t{font-size:13.5px;font-weight:700;line-height:1.4;}',
    '.it .d{font-size:12.5px;color:var(--ink2);line-height:1.5;margin-top:2px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}',
    '.it.open .d{-webkit-line-clamp:unset;}',
    '.it .tg{font-size:11px;color:var(--muted);margin-top:3px;}',
    '.badge{display:inline-block;font-size:10.5px;font-weight:800;color:var(--hot);border:1px solid var(--hot);border-radius:4px;padding:0 4px;margin-right:5px;vertical-align:1px;}',
    '.sec{font-size:11px;color:var(--muted);margin-right:4px;}',
    '.empty{font-size:12.5px;color:var(--muted);padding:6px 0;}',
    '.search{display:flex;gap:6px;flex-wrap:wrap;}',
    '.search input{flex:1;min-width:140px;}',
    '.results{margin-top:8px;max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:8px;}',
    '.res{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);padding:7px 10px;font-size:12.5px;}',
    '.res:last-child{border-bottom:0;}',
    '.res:hover{background:var(--bg2);}',
    '.res b{color:var(--accent);margin-right:6px;}',
    '.res .m{display:block;font-size:11.5px;color:var(--muted);margin-top:2px;}',
    '.err{font-size:13px;color:var(--warn);}'
  ].join('');

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function getJSON(url) {
    return fetch(url, {cache: 'no-cache'}).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }
  function copyText(t, btn) {
    var ok = function () { btn.textContent = '복사됨'; btn.classList.add('done'); setTimeout(function () { btn.textContent = '복사'; btn.classList.remove('done'); }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(ok, function () { fallback(); });
    } else fallback();
    function fallback() {
      var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); ok(); } catch (e) {} document.body.removeChild(ta);
    }
  }

  function mount(host) {
    if (host.__veduNews) return;
    host.__veduNews = true;
    var base = (host.getAttribute('data-base') || DEFAULT_BASE).replace(/\/$/, '');
    var root = host.attachShadow ? host.attachShadow({mode: 'open'}) : host;
    var style = el('style'); style.textContent = CSS; root.appendChild(style);
    var w = el('div', 'w'); root.appendChild(w);
    w.appendChild(el('div', 'empty', '뉴스를 불러오는 중…'));

    var state = {
      tags: (host.getAttribute('data-tags') || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean),
      hotOnly: false, expanded: false, issue: null, meta: null, index: []
    };

    Promise.all([getJSON(base + '/latest.json'), getJSON(base + '/index.json').catch(function () { return {issues: []}; })])
      .then(function (res) {
        state.meta = res[0]; state.issue = res[0].issue; state.index = res[1].issues || [];
        render();
      })
      .catch(function () {
        w.textContent = '';
        w.appendChild(el('div', 'err', '뉴스를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'));
      });

    function loadIssue(date) {
      var hit = state.index.filter(function (x) { return x.date === date; })[0];
      if (!hit) return;
      getJSON(base + '/' + date + '.json').then(function (iss) { state.issue = iss; state.expanded = false; render(); w.scrollIntoView({behavior: 'smooth', block: 'start'}); });
    }

    function render() {
      var iss = state.issue, meta = state.meta;
      w.textContent = '';

      // 상단: 브랜드 + 호 선택
      var top = el('div', 'top');
      top.appendChild(el('span', 'brand', '비상 교육 브리핑 · 영업용'));
      if (state.index.length) {
        var sel = el('select'); sel.setAttribute('aria-label', '호 선택');
        state.index.forEach(function (x) {
          var o = el('option', null, x.date + ' 제' + x.issue_no + '호'); o.value = x.date;
          if (x.date === iss.date) o.selected = true; sel.appendChild(o);
        });
        sel.addEventListener('change', function () { loadIssue(sel.value); });
        top.appendChild(sel);
      }
      w.appendChild(top);

      if (meta && meta.stale && iss.date === meta.latest_date) {
        w.appendChild(el('div', 'stale', '최근 ' + meta.age_days + '일간 새 브리핑이 없습니다. 아래는 ' + meta.latest_date + ' 호입니다.'));
      }

      // ③ 헤드라인 카드
      var lead = iss.lead || {};
      if (lead.kicker) w.appendChild(el('div', 'kicker', lead.kicker));
      var a = el('a', 'head', lead.headline || '(헤드라인 없음)'); a.href = iss.url; a.target = '_blank'; a.rel = 'noopener';
      w.appendChild(a);
      w.appendChild(el('div', 'meta', iss.date + (iss.weekday ? ' (' + iss.weekday + ')' : '') + ' · 제' + iss.issue_no + '호 · 원문 지면 보기 ↗'));
      if ((lead.facts || []).length) {
        var ul = el('ul', 'facts');
        lead.facts.slice(0, 4).forEach(function (f) { ul.appendChild(el('li', null, (f.label ? f.label + ': ' : '') + f.text)); });
        w.appendChild(ul);
      }

      // ① 오늘의 토킹포인트
      var h1 = el('h4', null, '오늘의 토킹포인트'); h1.appendChild(el('span', 'note', '내부 참고용 · 고객 전달 시 표현 다듬기'));
      w.appendChild(h1);
      var imps = (iss.implications || []).slice(0, 3);
      if (!imps.length) w.appendChild(el('div', 'empty', '이 호에는 시사점이 없습니다.'));
      imps.forEach(function (im) {
        var box = el('div', 'tp'), row = el('div', 'row'), txt = el('div');
        txt.appendChild(el('div', 'n', '뉴스 · ' + im.news));
        txt.appendChild(el('div', 's', im.sales_point));
        var b = el('button', 'copy', '복사'); b.type = 'button';
        b.addEventListener('click', function () { copyText('[뉴스] ' + im.news + '\n[영업 포인트] ' + im.sales_point, b); });
        row.appendChild(txt); row.appendChild(b); box.appendChild(row); w.appendChild(box);
      });

      // ② 담당 분야 필터 + ④ 경쟁사·자사 강조
      w.appendChild(el('h4', null, '분야별 기사'));
      var chips = el('div', 'chips');
      var allItems = [];
      (iss.sections || []).forEach(function (s) { (s.items || []).forEach(function (it) { allItems.push({sec: s.name, it: it}); }); });
      var present = {};
      allItems.forEach(function (x) { (x.it.tags || []).forEach(function (t) { present[t] = (present[t] || 0) + 1; }); });
      var hotChip = el('button', 'chip hot', '경쟁사·자사 동향' + ((present['경쟁사'] || 0) + (present['자사'] || 0) ? ' ' + ((present['경쟁사'] || 0) + (present['자사'] || 0)) : ''));
      hotChip.type = 'button'; hotChip.setAttribute('aria-pressed', String(state.hotOnly));
      hotChip.addEventListener('click', function () { state.hotOnly = !state.hotOnly; render(); });
      chips.appendChild(hotChip);
      (meta.tag_list || []).filter(function (t) { return HOT.indexOf(t) < 0; }).forEach(function (t) {
        var c = el('button', 'chip', t + (present[t] ? ' ' + present[t] : '')); c.type = 'button';
        c.setAttribute('aria-pressed', String(state.tags.indexOf(t) >= 0));
        c.addEventListener('click', function () {
          var i = state.tags.indexOf(t); if (i >= 0) state.tags.splice(i, 1); else state.tags.push(t); render();
        });
        chips.appendChild(c);
      });
      w.appendChild(chips);

      var list = el('div', 'items');
      var shown = allItems.filter(function (x) {
        var tg = x.it.tags || [];
        if (state.hotOnly && !tg.some(function (t) { return HOT.indexOf(t) >= 0; })) return false;
        if (state.tags.length && !tg.some(function (t) { return state.tags.indexOf(t) >= 0; })) return false;
        return true;
      });
      // 경쟁사·자사 기사는 위로 올린다
      shown.sort(function (p, q) {
        var hp = (p.it.tags || []).some(function (t) { return HOT.indexOf(t) >= 0; }) ? 0 : 1;
        var hq = (q.it.tags || []).some(function (t) { return HOT.indexOf(t) >= 0; }) ? 0 : 1;
        return hp - hq;
      });
      if (!shown.length) list.appendChild(el('div', 'empty', '선택한 분야의 기사가 이 호에는 없습니다.'));
      var LIMIT = 5, rest = shown.length - LIMIT;
      (state.expanded ? shown : shown.slice(0, LIMIT)).forEach(function (x) {
        var tg = x.it.tags || [];
        var isHot = tg.some(function (t) { return HOT.indexOf(t) >= 0; });
        var d = el('div', 'it' + (isHot ? ' hot' : ''));
        var t = el('div', 't');
        if (tg.indexOf('경쟁사') >= 0) t.appendChild(el('span', 'badge', '경쟁사'));
        if (tg.indexOf('자사') >= 0) t.appendChild(el('span', 'badge', '자사'));
        t.appendChild(el('span', 'sec', '[' + x.sec + ']'));
        t.appendChild(document.createTextNode(x.it.title));
        d.appendChild(t);
        var desc = el('div', 'd', x.it.summary); d.appendChild(desc);
        d.appendChild(el('div', 'tg', tg.map(function (s) { return '#' + s; }).join(' ')));
        d.addEventListener('click', function () { d.classList.toggle('open'); });
        list.appendChild(d);
      });
      w.appendChild(list);
      if (rest > 0) {
        var more = el('button', 'chip', state.expanded ? '접기' : '기사 ' + rest + '건 더 보기'); more.type = 'button';
        more.style.marginTop = '8px';
        more.addEventListener('click', function () { state.expanded = !state.expanded; render(); });
        w.appendChild(more);
      }

      // ⑤ 지난 호 검색
      if (state.index.length) {
        w.appendChild(el('h4', null, '지난 호 검색'));
        var srch = el('div', 'search');
        var q = el('input'); q.type = 'search'; q.placeholder = '키워드 (예: 교부금, AI 디지털교과서, 늘봄)'; q.setAttribute('aria-label', '지난 호 검색');
        var tagSel = el('select'); tagSel.setAttribute('aria-label', '분야');
        tagSel.appendChild(el('option', null, '전체 분야'));
        (meta.tag_list || []).forEach(function (t) { var o = el('option', null, t); o.value = t; tagSel.appendChild(o); });
        tagSel.options[0].value = '';
        srch.appendChild(q); srch.appendChild(tagSel); w.appendChild(srch);
        var box = el('div', 'results'); w.appendChild(box);
        var run = function () {
          var kw = q.value.trim().toLowerCase(), tf = tagSel.value;
          box.textContent = '';
          var hits = state.index.filter(function (x) {
            if (tf && (x.tags || []).indexOf(tf) < 0) return false;
            if (!kw) return true;
            return [x.headline, x.kicker].concat(x.titles || []).join(' ').toLowerCase().indexOf(kw) >= 0;
          });
          if (!hits.length) { box.appendChild(el('div', 'empty', '  일치하는 호가 없습니다.')); return; }
          hits.forEach(function (x) {
            var b = el('button', 'res'); b.type = 'button';
            b.appendChild(el('b', null, x.date));
            b.appendChild(document.createTextNode(x.headline));
            var m = kw ? (x.titles || []).filter(function (s) { return s.toLowerCase().indexOf(kw) >= 0; })[0] : '';
            b.appendChild(el('span', 'm', m ? '… ' + m : (x.tags || []).map(function (s) { return '#' + s; }).join(' ')));
            b.addEventListener('click', function () { loadIssue(x.date); });
            box.appendChild(b);
          });
        };
        var tmr; q.addEventListener('input', function () { clearTimeout(tmr); tmr = setTimeout(run, 150); });
        tagSel.addEventListener('change', run);
        run();
      }
    }
  }

  function init() {
    var hosts = document.querySelectorAll('#vedu-news, [data-vedu-news]');
    for (var i = 0; i < hosts.length; i++) mount(hosts[i]);
  }
  window.VeduNewsWidget = {mount: mount};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
