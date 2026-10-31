/* 跃迁法术收集计算器 —— 界面逻辑（依赖 window.SPELL_DATA / ICON_DATA / LDT） */
(function () {
  'use strict';

  var SPELLS = (window.SPELL_DATA || {}).spells || [];
  var byId = {};
  var guar = {};
  SPELLS.forEach(function (s) {
    byId[s.id] = s;
    if (s.guaranteed) guar[s.id] = 1;
  });

  var ROLE_CN = LDT.CFG.ROLE_CN;
  var ROLE_ORDER = LDT.CFG.ROLE_ORDER;

  // 页面专属致谢（HTML）
  var PAGE_CREDIT = {
    tentacle: '项目思路对本工具帮助显著：<b>机・丹尼尔・奥利瓦</b>',
    blackflash: '黑洞闪电弹跃迁的技术支持：<b>UBK</b>'
  };

  var owned = {};
  var state = { page: 'tentacle', sols: [], pageIdx: 0, pageSize: 50 };

  /* ------------------------------------------------------------ 工具 */
  function $(sel) { return document.querySelector(sel); }
  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }
  function iconUrl(id) { return (window.ICON_DATA || {})[id] || ''; }

  /** 显示名：常用名覆盖表 → Wiki 官方中文名 → Wiki 页面名 → ID */
  function dispName(id) {
    var over = LDT.CFG.NAME_CN[id];
    if (over) return over;
    var s = byId[id];
    if (!s) return id;
    return (s.name_official || '').trim() || s.wiki_page || id;
  }

  /** 交换鹿需要非零伤害：优先用已有的，否则用最容易获取的 */
  function pickDamageMod() {
    var mods = LDT.CFG.DAMAGE_MODS;
    for (var i = 0; i < mods.length; i++) {
      if (owned[mods[i]]) return mods[i];
    }
    var best = mods[0], bc = Infinity;
    mods.forEach(function (id) {
      var c = LDT.Score.unitCost(id);
      if (c < bc) { bc = c; best = id; }
    });
    return best;
  }

  function targetDistance() {
    var v = $('#targetDist').value;
    return v === 'custom' ? Math.max(1, +$('#customDist').value || 35840) : +v;
  }

  function payloadOf(sel) {
    var mode = $(sel).value;
    if (mode === 'none') return [];
    var set = LDT.CFG.PAYLOADS[mode] || [];
    return mode === 'swap' ? set.concat([pickDamageMod()]) : set.slice();
  }

  function staffMultsOf(sel) {
    var v = $(sel).value;
    return v === 'any' ? [1, 1.25, 1.5] : [parseFloat(v)];
  }

  /* ------------------------------------------------------------ 法术面板 */
  var rowsById = {};       // id -> [row, ...]（同一法术可出现在多个分区）

  function rolesOf(s) {
    return (s.roles && s.roles.length) ? s.roles : [s.role || 'aux'];
  }

  function buildPanel() {
    var wrap = $('#spellGroups');
    wrap.innerHTML = '';
    rowsById = {};

    var groups = {};
    SPELLS.forEach(function (s) {
      rolesOf(s).forEach(function (role) {
        (groups[role] = groups[role] || []).push(s);
      });
    });

    ROLE_ORDER.forEach(function (role) {
      var list = groups[role];
      if (!list || !list.length) return;
      var g = el('div', 'sgroup');
      g.dataset.role = role;
      g.appendChild(el('h3', null, ROLE_CN[role] || role));
      list.forEach(function (s) { g.appendChild(spellRow(s, role)); });
      wrap.appendChild(g);
    });
  }

  function spellRow(s, role) {
    var row = el('label', 'sitem');
    row.dataset.id = s.id;
    row.dataset.role = role;
    row.dataset.search = (dispName(s.id) + ' ' + s.id + ' ' + (s.wiki_page || '')).toLowerCase();

    var img = el('img');
    img.src = iconUrl(s.id);
    img.alt = '';
    row.appendChild(img);

    row.appendChild(el('span', 'nm', dispName(s.id)));
    // 只在「我的法术」栏显示速度乘数 / 时间修正
    var mult = LDT.CFG.SPEED_MULT[s.id];
    var delta = LDT.CFG.TIME_DELTA[s.id];
    if (mult != null) {
      row.appendChild(el('span', 'mul', '×' + mult));
    } else if (delta != null) {
      row.appendChild(el('span', 'mul', (delta > 0 ? '+' : '') + delta + 'f'));
    }
    if (s.guaranteed) row.appendChild(el('span', 'tag', '常备'));

    var num = el('input');
    num.type = 'number';
    num.min = '1';
    num.placeholder = '1';
    num.title = '已有数量（留空按 1）';
    num.addEventListener('click', function (e) { e.stopPropagation(); });
    num.addEventListener('input', function () {
      if (owned[s.id]) owned[s.id] = Math.max(1, +num.value || 1);
      refreshAll(s.id);
    });

    var chk = el('input');
    chk.type = 'checkbox';
    chk.addEventListener('change', function () {
      if (chk.checked) owned[s.id] = Math.max(1, +num.value || 1);
      else delete owned[s.id];
      refreshAll(s.id);
    });

    row.appendChild(num);
    row.appendChild(chk);
    row._chk = chk; row._num = num;
    (rowsById[s.id] = rowsById[s.id] || []).push(row);
    return row;
  }

  /** 同一法术的所有分区行保持同步 */
  function refreshAll(id) {
    (rowsById[id] || []).forEach(refreshRow);
  }

  function refreshRow(row) {
    var id = row.dataset.id;
    var on = !!owned[id];
    row.classList.toggle('on', on);
    if (row._chk) row._chk.checked = on;
    if (row._num) row._num.value = on ? owned[id] : '';
  }

  /* ------------------------------------------------------------ 参数 */
  function readOpts() {
    LDT.Weights.build(SPELLS, { scheme: 'pct' });

    var D = targetDistance();
    var tolRaw = Math.max(0, +$('#tolerance').value || 0);
    var tolAbs = $('#tolMode').value === 'rel'
      ? Math.min(0.5, tolRaw / 100) * D
      : tolRaw;

    var common = {
      distance: D,
      tolerance: tolAbs,
      maxPerSpell: Math.max(1, +$('#maxPerSpell').value || 3),
      owned: owned,
      guaranteed: guar,
      sortMode: $('#sortMode').value,
      ignoreOptional: !$('#countOptional').checked
    };

    if (state.page === 'tentacle') {
      common.maxUpDown = Math.max(0, +$('#ttMaxUpDown').value || 0);
      common.maxSpeedMods = Math.max(0, +$('#ttMaxMods').value || 0);
      common.calibrator = $('#ttCalibrator').checked;
      common.multiChain = $('#ttMultiChain').checked;
      common.wrap = $('#ttWrap').checked;
      common.payload = payloadOf('#ttPayload');
      common.staffMults = common.calibrator ? [1] : staffMultsOf('#ttStaff');
      common.limit = 3000;
    } else if (state.page === 'blackflash') {
      common.maxCorrections = Math.max(0, +$('#bfMaxCorr').value || 0);
      common.maxSpeedMods = Math.max(0, +$('#bfMaxSpeed').value || 0);
      common.staffs = staffMultsOf('#bfStaff');
      common.payload = payloadOf('#bfPayload');
      common.bhMinDist = $('#bfBhFar').checked ? LDT.CFG.BH_MIN_DIST : 0;
      common.limitLtSag = $('#bfLimitSag').checked;
      common.limit = 1000;
    } else {
      common.maxPhases = Math.max(1, +$('#phMaxPhases').value || 1600);
      common.calibrator = $('#phCalibrator').checked;
      common.multiChain = $('#phMultiChain').checked;
      common.wrap = $('#phWrap').checked;
      common.payload = payloadOf('#phPayload');
    }
    return common;
  }

  /* ------------------------------------------------------------ 计算 */
  function solve() {
    var opts = readOpts();
    var t0 = performance.now();
    var sols;
    if (state.page === 'tentacle') sols = LDT.Tentacle.solve(opts);
    else if (state.page === 'blackflash') sols = LDT.BlackFlash.solve(opts);
    else sols = LDT.Solve.phase(opts);
    var ms = Math.round(performance.now() - t0);

    state.sols = sols;
    state.pageIdx = 0;
    $('#resultStat').textContent = sols.length
      ? ('共 ' + sols.length + ' 个可行方案 · 用时 ' + ms + ' ms · 按' +
         ($('#sortMode').value === 'error' ? '误差' : '相对难度（S值，越小越易凑）') + '排序')
      : ('没有可行方案（用时 ' + ms + ' ms）· 可尝试放宽误差容限或调整上限');
    renderResults();
  }

  /* ------------------------------------------------------------ 渲染 */
  function renderResults() {
    var box = $('#results');
    box.innerHTML = '';
    var sols = state.sols;
    if (!sols.length) {
      box.appendChild(el('div', 'empty', '还没有结果。勾选已拥有的法术，然后点「开始计算」。'));
      $('#pager').innerHTML = '';
      return;
    }
    var start = state.pageIdx * state.pageSize;
    sols.slice(start, start + state.pageSize).forEach(function (sol, i) {
      box.appendChild(solutionCard(sol, start + i + 1));
    });
    renderPager();
  }

  function solutionCard(sol, idx) {
    var card = el('div', 'sol' + (sol.overCapacity ? ' over' : ''));

    var head = el('div', 'sol-head');
    head.appendChild(el('div', 'sol-idx', String(idx)));

    // 误差配色与旧版一致：≤5 绿、≤100 黄、其余红
    var e = sol.error;
    var errCls = e <= 5 ? ' good' : (e <= 100 ? ' warn' : ' bad');
    var rel = sol.dist > 0 ? (e / sol.dist * 100) : 0;
    head.appendChild(metric('误差', e.toFixed(0) + ' px (' + rel.toFixed(3) + '%)', errCls));

    if (sol.page === 'blackflash' && sol.rangeLo != null) {
      var lo = Math.round(sol.rangeLo - sol.dist);
      var hi = Math.round(sol.rangeHi - sol.dist);
      head.appendChild(metric('存在时间区间',
        (lo >= 0 ? '+' : '−') + Math.abs(lo) + ' ~ ' + (hi >= 0 ? '+' : '−') + Math.abs(hi) + ' px', ''));
    }

    var stageTip = (sol.score.groups || []).map(function (g) {
      return g.label + ' ' + g.cost.toFixed(1);
    }).join(' + ');
    head.appendChild(metric('相对难度', fmtFixed(sol.score.sum, 1) + '（S值）', '',
      'S值 = 预计耗时（单位：走过 1 个区块的时间，越小越容易凑齐）。\n' +
      '算法：① 每个缺失法术算出「三个刷点各走一轮能拿到几份」；② 指派到最划算的刷点；\n' +
      '③ 同一刷点内用 3-范数聚合出「要走几轮」（由最难凑的那项主导）；\n' +
      '④ 换成时间：轮数 × 单轮耗时 + 开世界次数 × 跨平行世界 113.2。\n' +
      '主世界 7 座圣山视为已搜完，所以第一轮就要跨平行世界；一趟平行世界同时补满圣山与繁茂。\n' +
      '单轮耗时（' + (LDT.CFG.MODE === 'expert' ? '熟练' : '默认') + '）：' +
      LDT.CFG.ZONES.map(function (z) { return z.label + ' ' + z.cost.toFixed(1); }).join(' / ') + '。\n' +
      (stageTip ? '本例：' + stageTip + '。' : '')));
    try {
      var planItems = (sol.score.detail || []).map(function (d) { return { id: d.id, lack: d.lack }; });
      var plan = LDT.Plan.best(planItems);
      if (plan) head.appendChild(planChip(plan));
    } catch (e) { /* 策略建议是附加信息，算不出来不影响主流程 */ }
    head.appendChild(metric('缺失', sol.score.kinds + ' 种 / ' + sol.score.pieces + ' 个', ''));
    head.appendChild(metric('槽位', sol.slots + ' / ' + (sol.staffCap || 26) + ' 格', ''));

    // ---- 页签专属徽章
    if (sol.page === 'phase') {
      head.appendChild(badge(sol.combo.label, ''));
      head.appendChild(badge('相位 ' + sol.pEff + ' 份' +
        (sol.pEff !== sol.pPhys ? '（实体 ' + sol.pPhys + '）' : ''), 'gold'));
      if (sol.pEff > LDT.CFG.PHASE.speedZeroAt) {
        head.appendChild(badge('必须配加速', 'red'));
      }
      if (sol.wrap) head.appendChild(badge('回绕', 'warn'));
    } else if (sol.page === 'tentacle') {
      head.appendChild(badge('上/下飞 ' + sol.nEff +
        (sol.nEff !== sol.nPhys ? '（实体 ' + sol.nPhys + '）' : ''), 'gold'));
      head.appendChild(badge('α = ' + sol.alpha.toFixed(4), ''));
      if (sol.wrap) head.appendChild(badge('回绕', 'warn'));
    } else {
      head.appendChild(badge('黑洞 ' + sol.bh.d.toFixed(0) + ' + 闪电弹 ' + sol.lt.d.toFixed(0), ''));
    }

    // ---- 法杖徽章（带图标）
    head.appendChild(staffBadge(sol));

    if (sol.overCapacity) head.appendChild(badge('超容量', 'red'));
    card.appendChild(head);

    var firstMissing = true;
    LDT.Format.blocks(sol, owned, guar).forEach(function (b) {
      var row = el('div', 'row' + (b.optional ? ' opt' : ''));
      row.appendChild(el('div', 'row-label', b.label));
      var body = el('div', 'row-body');
      b.items.forEach(function (it) {
        body.appendChild(chip(it, firstMissing));
        if (it.lack > 0) firstMissing = false;
      });
      if (b.note) body.appendChild(el('span', 'chain-note', b.note));
      if (b.hint) body.appendChild(el('span', 'chain-note warn-note', '⚠ ' + b.hint));
      row.appendChild(body);
      card.appendChild(row);
    });
    return card;
  }

  function staffBadge(sol) {
    // 相位跃迁的距离只由「跳跃次数 × 相位个数」决定，与法杖倍率无关
    if (sol.page === 'phase') return el('span', 'badge', '法杖容量 ' + (sol.staffCap || 26) + ' 格');
    var s = sol.staff;
    var b = el('span', 'badge staff');
    if (s && s.icon) {
      var img = el('img');
      img.src = iconUrl(s.icon);
      img.alt = '';
      b.appendChild(img);
      b.appendChild(el('span', null, s.label + '（' + s.cap + ' 格）'));
    } else if (sol.page === 'tentacle' && sol.calibrator) {
      b.appendChild(el('span', null, '校准器已规避法杖倍率'));
    } else {
      b.appendChild(el('span', null, '普通法杖 ×1.0（26 格）'));
    }
    return b;
  }

  function fmtInt(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /** 保留 digits 位小数，并给整数部分加千分位（如 1,234.5） */
  function fmtFixed(n, digits) {
    var parts = (Number(n) || 0).toFixed(digits == null ? 1 : digits).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.join('.');
  }


  // ---------- 最佳策略徽章 + 说明弹窗 ----------
  var PLAN_HELP = [
    ['greedy', '按法术分配：每个缺的法术各自派到「每单位时间出得最多」的刷点，同一刷点内按最难凑的那项定轮数。这是可行方案里的最优解，所以基本总是它胜出。'],
    ['冒号后的 holy / fungi / hell', '这个配方**耗时最多**的刷点（不是第一步）：holy = 圣山，fungi = 繁茂，hell = 地狱。'],
    ['holy_first / fungi_first / hell_first', '硬性顺序对照：只在一个刷点根本出不了该法术时才往下传。数字通常大一个量级，用来说明「为什么值得按法术分开刷」。'],
    ['单位', '1 = 直线穿过 1 个区块（512 px）空隙地形的时间。']
  ];

  function showPlanHelp(plan) {
    var mask = el('div', 'modal-mask');
    var box = el('div', 'modal-box');
    box.appendChild(el('div', 'modal-title', '最佳策略：' + plan.label));

    // 1) 区域明细（最有用的一块，放最前）
    if (plan.zoneDetail && plan.zoneDetail.length) {
      var zd = el('div', 'modal-body');
      zd.appendChild(el('div', 'modal-sub', '时间花在哪（本例估计）'));
      var tot = plan.zoneDetail.reduce(function (a, x) { return a + x.time; }, 0) || 1;
      plan.zoneDetail.forEach(function (x) {
        zd.appendChild(el('div', 'modal-row' + (x.key === plan.zone ? ' best' : ''),
          x.label + '：' + Math.round(x.time) + '（' + Math.round(100 * x.time / tot) + '%，约 '
          + x.rounds.toFixed(1) + ' 轮）' + (x.key === plan.zone ? '　← 主要耗时' : '')));
      });
      box.appendChild(zd);
    }

    // 2) 名词解释
    var body = el('div', 'modal-body');
    body.appendChild(el('div', 'modal-sub', '缩写含义'));
    PLAN_HELP.forEach(function (r) {
      var line = el('div', 'modal-row');
      line.appendChild(el('b', null, r[0]));
      line.appendChild(document.createTextNode(' —— ' + r[1]));
      body.appendChild(line);
    });
    box.appendChild(body);

    // 3) 四种策略对照
    var cand = el('div', 'modal-body');
    cand.appendChild(el('div', 'modal-sub', '四种策略的估计耗时（越小越快）'));
    (plan.all || []).forEach(function (c) {
      cand.appendChild(el('div', 'modal-row' + (c.key === plan.key ? ' best' : ''),
        c.label + '：' + Math.round(c.total) + (c.key === plan.key ? '　← 最快' : '')));
    });
    box.appendChild(cand);

    var btn = el('button', 'modal-close', '知道了');
    btn.type = 'button';
    btn.onclick = function () { document.body.removeChild(mask); };
    box.appendChild(btn);
    mask.appendChild(box);
    mask.onclick = function (ev) { if (ev.target === mask) document.body.removeChild(mask); };
    document.body.appendChild(mask);
  }

  function planChip(plan) {
    var b = el('button', 'plan-chip');
    b.type = 'button';
    b.title = '点开看各缩写的含义';
    b.appendChild(document.createTextNode('最佳策略 '));
    b.appendChild(el('b', null, plan.label));
    b.appendChild(el('span', 'plan-q', '?'));
    b.onclick = function (ev) { ev.stopPropagation(); showPlanHelp(plan); };
    return b;
  }

  function metric(label, val, cls, tip) {
    var d = el('div', 'metric' + (cls || ''));
    d.appendChild(document.createTextNode(label + ' '));
    var b = el('b', null, val);
    d.appendChild(b);
    if (tip) d.title = tip;
    return d;
  }

  function badge(text, cls) {
    return el('span', 'badge' + (cls ? ' ' + cls : ''), text);
  }

  function chip(it, full) {
    var c = el('span', 'chip' + (it.lack > 0 ? ' miss' : ' have'));
    var img = el('img');
    img.src = iconUrl(it.id);
    img.alt = '';
    c.appendChild(img);
    // 卡片内一律不写名字，只留图标（名字见 tooltip），避免臃肿
    var txt;
    if (it.lack > 0) {
      txt = (full ? '缺 ' + it.lack + '（' : '') +
            (full ? '有 ' + it.owned + ' / 需 ' + it.need + '）'
                  : it.lack + '（' + it.owned + '/' + it.need + '）');
    } else {
      txt = '×' + it.need;
    }
    c.appendChild(el('span', 'cnt', txt));
    c.title = dispName(it.id) + ' · ' + it.id +
              '｜需 ' + it.need + ' / 有 ' + it.owned;
    return c;
  }

  function renderPager() {
    var pager = $('#pager');
    pager.innerHTML = '';
    var pages = Math.ceil(state.sols.length / state.pageSize);
    if (pages <= 1) return;
    var cur = state.pageIdx;
    var from = Math.max(0, cur - 4), to = Math.min(pages, from + 10);
    if (to - from < 10) from = Math.max(0, to - 10);

    function btn(label, idx, on) {
      var b = el('button', on ? 'on' : '', label);
      b.addEventListener('click', function () {
        state.pageIdx = idx;
        renderResults();
        $('#results').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      return b;
    }
    if (cur > 0) pager.appendChild(btn('‹ 上一页', cur - 1));
    for (var i = from; i < to; i++) pager.appendChild(btn(String(i + 1), i, i === cur));
    if (cur < pages - 1) pager.appendChild(btn('下一页 ›', cur + 1));
  }

  /* ------------------------------------------------------------ 自检 */
  function runSelftest() {
    var out = [];
    var pass = 0, fail = 0;
    function ok(name, cond, extra) {
      if (cond) { pass++; out.push('  ✓ ' + name + (extra ? '  ' + extra : '')); }
      else { fail++; out.push('  ✗ ' + name + (extra ? '  ' + extra : '')); }
    }

    out.push('=== 1. 相位跳跃次数 ===');
    ok('定时 100f → 8 次', LDT.Phase.timerJumps(100) === 8);
    ok('限制 200f → 16 次', LDT.Phase.limitJumps(200) === 16);
    ok('限制 300f → 24 次', LDT.Phase.limitJumps(300) === 24);

    out.push('=== 2. Dn 链 ===');
    ok('合法链 116 条', LDT.DN.chains().length === 116, '实际 ' + LDT.DN.chains().length);
    var d80 = LDT.DN.decompose(80, { allowBody: false });
    ok('80 = D10·D4·D2', d80.length > 0,
      d80.length ? d80[0].chains.map(function (c) { return 'D' + c.digits.join(''); }).join('') : '');

    out.push('=== 3. 复制链辅助法术 ===');
    var e1 = LDT.Chain.extras([{ digits: [2], product: 2 }], 1, false);
    ok('单链 + 只复制 1 个法术 → 不需追加触发', e1.triggers === 0);
    var e2 = LDT.Chain.extras([{ digits: [2], product: 2 }], 2, false);
    ok('单链 + 复制多个法术 → 1 个追加触发', e2.triggers === 1);
    var e3 = LDT.Chain.extras([{ digits: [2], product: 2 }, { digits: [4], product: 4 }], 1, false);
    ok('两条链 → 2 个追加触发', e3.triggers === 2);
    ok('两条链 → 必须带刷新环', e3.reset === true);
    ok('回绕 → 必须带刷新环', LDT.Chain.extras([], 1, true).reset === true);
    ok('单链无回绕 → 不要刷新环', LDT.Chain.extras([{ digits: [2], product: 2 }], 1, false).reset === false);

    out.push('=== 4. 经典配置 ===');
    var c200 = LDT.Phase.combos().filter(function (c) { return c.limiter && c.limiter.frames === 200; })[0];
    ok('200f + 80 相位 = 35840', LDT.Phase.distance(80, c200.jumps) === 35840);
    var ct = LDT.Phase.combos().filter(function (c) { return c.carrier.kind === 'timer'; })[0];
    ok('定时能量球 + 160 相位 = 35840', LDT.Phase.distance(160, ct.jumps) === 35840);

    out.push('=== 5. 本页求解器（' + ({ tentacle: '速度触手', blackflash: '黑洞闪电弹', phase: '相位跃迁' }[state.page]) + '） ===');
    var opts = readOpts();
    opts.owned = {}; opts.guaranteed = guar;
    var s;
    if (state.page === 'tentacle') s = LDT.Tentacle.solve(opts);
    else if (state.page === 'blackflash') s = LDT.BlackFlash.solve(opts);
    else s = LDT.Solve.phase(opts);
    ok('有可行方案', s.length > 0, s.length + ' 个');
    if (s.length) {
      ok('误差均在容限内', s.every(function (x) { return x.error <= opts.tolerance + 1e-9; }));
      ok('同种法术不超上限', s.every(function (x) {
        return Object.keys(x.need).every(function (k) { return x.need[k] <= opts.maxPerSpell; });
      }));

      var blocks = LDT.Format.blocks(s[0], owned, guar);
      var copyBlk = blocks.filter(function (b) { return b.key === 'copy'; })[0];
      if (copyBlk) {
        var idxDn = copyBlk.items.findIndex(function (i) { return LDT.Format.isDn(i.id); });
        ok('复制链行 Dn 在前', idxDn <= 0, 'Dn@' + idxDn);
        ok('刷新环在复制链行末尾', copyBlk.items.every(function (i, idx, arr) {
          return i.id !== 'RESET' || idx === arr.length - 1;
        }));
      }
      // 相位只在相位页属于复制链；触手页必须归入速度修正
      var inCopy = blocks.some(function (b) {
        return b.key === 'copy' && b.items.some(function (i) { return i.id === 'PHASING_ARC'; });
      });
      var inSpeed = blocks.some(function (b) {
        return b.key === 'speed' && b.items.some(function (i) { return i.id === 'PHASING_ARC'; });
      });
      if (state.page === 'phase') ok('相位页：相位在复制链里', inCopy || !inSpeed);
      if (state.page === 'tentacle') ok('触手页：相位在速度修正里（不在复制链）', !inCopy);

      if (state.page === 'blackflash') {
        ok('黑洞与闪电弹各带一个追加失效触发',
          blocks.filter(function (b) { return b.key === 'bh' || b.key === 'lt'; })
            .every(function (b) {
              return b.items.some(function (i) { return i.id === LDT.CFG.CARRIER_TRIGGER; });
            }));
        ok('黑洞飞离加载区 ≥ 2048 px', s.every(function (x) {
          return !opts.bhMinDist || x.bh.d >= opts.bhMinDist;
        }));
      }
      if (state.page === 'tentacle') {
        ok('校准器时法杖倍率不参与', !opts.calibrator ||
          s.every(function (x) { return !x.staff; }));
        ok('上下飞只算 1 个本体', s.every(function (x) {
          var n = 0;
          LDT.CFG.FLY.forEach(function (id) { n += x.need[id] || 0; });
          return n <= 1;
        }));
      }
    }

    $('#selftestOut').textContent = out.join('\n') + '\n\n=== ' + pass + ' 通过 / ' + fail + ' 失败 ===';
  }

  /** 页面专属致谢（没有就隐藏） */
  function updateCredit(page) {
    var credit = $('#pageCredit');
    if (!credit) return;
    var txt = PAGE_CREDIT[page];
    credit.hidden = !txt;
    credit.innerHTML = txt || '';
  }

  /* ------------------------------------------------------------ 侧栏 */
  function setPanel(open) {
    document.body.classList.toggle('panel-collapsed', !open);
    // 遮罩只在「窄屏 + 面板展开」时出现
    $('#scrim').hidden = !(open && isNarrow());
  }
  function isNarrow() { return window.matchMedia('(max-width: 860px)').matches; }

  /* ------------------------------------------------------------ 事件绑定 */
  function switchPage(page) {
    state.page = page;
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (t) {
      t.classList.toggle('active', t.dataset.page === page);
    });
    ['tentacle', 'blackflash', 'phase'].forEach(function (p) {
      var layer = document.getElementById('deco-' + p);
      if (layer) layer.classList.toggle('active', p === page);
      $('#pp-' + p).hidden = (p !== page);
    });
    updateCredit(page);
    state.sols = [];
    state.pageIdx = 0;
    $('#resultStat').textContent = '尚未计算';
    $('#selftestOut').textContent = '';   // 切页重置自检输出
    renderResults();
  }

  function init() {
    // 装饰层图标（base64 内嵌，透明底像素图）
    Array.prototype.forEach.call(document.querySelectorAll('.deco[data-icon]'), function (img) {
      var src = iconUrl(img.dataset.icon);
      if (src) img.src = src;
    });

    buildPanel();

    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (t) {
      t.addEventListener('click', function () { switchPage(t.dataset.page); });
    });

    $('#targetDist').addEventListener('change', function () {
      $('#customDistWrap').hidden = this.value !== 'custom';
    });

    // 误差容限：px 与 % 各自记住自己的值，避免「200% 误差」这种荒谬默认值
    var tolMode = 'abs';
    var tolStore = { abs: 200, rel: 1 };
    $('#tolMode').addEventListener('change', function () {
      tolStore[tolMode] = Math.max(0, +$('#tolerance').value || 0);
      tolMode = this.value;
      $('#tolerance').value = tolStore[tolMode];
    });

    $('#spellSearch').addEventListener('input', function () {
      var q = this.value.trim().toLowerCase();
      Array.prototype.forEach.call(document.querySelectorAll('.sitem'), function (r) {
        r.style.display = (!q || r.dataset.search.indexOf(q) >= 0) ? '' : 'none';
      });
      // 搜索后隐藏空分区
      Array.prototype.forEach.call(document.querySelectorAll('.sgroup'), function (g) {
        var any = Array.prototype.some.call(g.querySelectorAll('.sitem'), function (r) {
          return r.style.display !== 'none';
        });
        g.style.display = any ? '' : 'none';
      });
    });

    $('#clearOwned').addEventListener('click', function () {
      owned = {};
      Object.keys(rowsById).forEach(refreshAll);
      // 已有结果时立刻重算，否则用户会以为「清空」没生效
      if (state.sols.length) solve();
      else renderResults();
    });

    // 侧栏
    $('#panelToggle').addEventListener('click', function () {
      setPanel(document.body.classList.contains('panel-collapsed'));
    });
    $('#panelClose').addEventListener('click', function () { setPanel(false); });
    $('#scrim').addEventListener('click', function () { setPanel(false); });
    if (isNarrow()) setPanel(false);

    $('#solveBtn').addEventListener('click', solve);
    $('#pageSize').addEventListener('change', function () {
      state.pageSize = +this.value;
      state.pageIdx = 0;
      renderResults();
    });
    $('#sortMode').addEventListener('change', function () { if (state.sols.length) solve(); });
    $('#playerMode').addEventListener('change', function () {
      LDT.CFG.setMode(this.value);
      if (state.sols.length) solve();
    });
    $('#runSelftest').addEventListener('click', runSelftest);
    LDT.CFG.setMode($('#playerMode').value);

    // 校准器开启时法杖倍率不参与计算，但控件保持可选（只做标注，不禁用）
    function syncCalib() {
      var on = $('#ttCalibrator').checked;
      $('#ttStaffLabel').textContent = on
        ? '法杖速度倍率（校准器已规避，不参与）'
        : '法杖速度倍率';
      $('#ttStaffField').classList.toggle('ignored', on);
    }
    $('#ttCalibrator').addEventListener('change', syncCalib);
    syncCalib();

    updateCredit(state.page);
    renderResults();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
