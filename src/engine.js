/**
 * 跃迁法术收集计算器 —— 核心算法引擎（v0.1.1）
 *
 * 设计原则：
 *   1. 不依赖 DOM，可在 Node 下直接跑自检，也可被 HTML 直接引入。
 *   2. 所有游戏参数集中在 CFG，便于后续按 Wiki 答复调整。
 *   3. 数据（法术权重）由外部注入，不硬编码在引擎里。
 *   4. 求解器输出「分区」（zones），展示与评分都从 zones 派生，避免两套口径。
 *
 * 模块：
 *   DN          一分为多链枚举（位置约束 = 迭代极限）
 *   Weights     生成概率（按等级出现频率归一）
 *   Phase       相位跳跃次数与距离
 *   Score       收集难度（k-范数）
 *   Solve       相位跃迁求解器
 *   Tentacle    速度触手跃迁求解器
 *   BlackFlash  黑洞闪电弹跃迁求解器
 */
(function (global, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else global.LDT = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ---------------------------------------------------------------- 配置
  var CFG = {
    // 世界宽度
    WORLD: { ng: 35840, ngPlus: 32768 },
    // 相位
    PHASE: {
      jumpEvery: 12,      // 每 12 帧跳一次
      jumpDist: 28,       // 每次 28 像素
      speedZeroAt: 90,    // > 90 份时提示「必须配加速」（Wiki 实测约 93）
      maxPhases: 1600     // 搜索上限
    },
    // Dn 链：位置约束 = 迭代极限（D10=2 / D4,D3=3 / D2=4）
    DN_POSITIONS: [[2, 3, 4, 10], [2, 3, 4, 10], [2, 3, 4], [2]],
    DN_MAX_CHAINS: 2,     // 最多两条链相加
    /**
     * 地狱的搜索面积（chunk）。两种模式产出一样（62.5 张/轮），区别只在「要走多少路」：
     *   默认 = 2 chunk 宽 × 43 高，扫整轮循环 = 86 chunk 混合
     *   熟练 = 10 chunk 混合（密集区随机分布在地狱两侧，即使知道大概位置也搜不准）
     *          + 14 chunk 空隙（7000 px，两侧来回穿行）
     * 重刷成本 43 两种模式都不变（用户 2026-10-31：补货难度不变）。
     */
    HELL_CHUNKS: { default: 86, expert: 10 },
    HELL_TRAVERSE: { default: 0, expert: 14 },   // 两侧穿行 7000 px ≈ 14 chunk 空隙
    HELL_CHUNK_COST: 2 * 2.0,     // 搜 1 chunk 法术 = 跑 2 chunk × 混合地形 2.0
    HELL_REFILL: 43,              // 走 22000 px 空隙重刷一轮
    /**
     * 搜索模式（「去哪刷」）：模式内各等级均匀出现，一次抽取只出一个等级。
     * 收集难度按「每个法术先指派到对自己最有利的模式 → 阶段内 3-范数 → 阶段间求和」计算。
     */
    /**
     * 三个刷点（口径 v7.2）：cost = 走一轮的时间；needsWorld = 要跨平行世界才有库存。
     *
     * ⚠️ 主世界 7 座圣山按用户设定「已搜完」，所以**第一轮就要跨平行世界**——
     *    换世界成本不是「第二轮起才付」，而是每次开新世界都付（见 WORLD_RESET）。
     *    一次跨世界会把圣山和繁茂一起补满（同一趟平行世界）。
     */
    ZONES: [
      { key: 'holy',  label: '圣山', cost: 76.7,  needsWorld: true },
      { key: 'fungi', label: '繁茂', cost: 685.7, needsWorld: true },
      { key: 'hell',  label: '地狱', cost: 387.0, needsWorld: false }
    ],
    WORLD_RESET: 113.2,          // 跨平行世界：上升 25.6 空隙 + 64.1 空隙 + 5.86×固体4
    MODE: 'default',             // 'default' 默认 / 'expert' 熟练玩家
    // 繁茂单轮成本 = 42 chunk × 4（搜法杖）× 混合 2.0 × 危险惩罚 + 入场 13.67
    FUNGI_BASE: 42 * 4 * 2.0,
    FUNGI_ENTRY: 4000 / 512 + 1500 / 512 * 2,
    DANGER_FUNGI: { default: 2.0, expert: 1.5 },
    /**
     * 切换玩家水平。只影响繁茂的危险惩罚（默认 2.0 / 熟练 1.5），
     * 因为「地形系数」是客观的，只有「被怪打断的频率」随熟练度变。
     */
    setMode: function (mode) {
      if (!(mode in CFG.DANGER_FUNGI)) mode = 'default';
      CFG.MODE = mode;
      CFG.ZONES.forEach(function (z) {
        if (z.key === 'fungi') {
          z.cost = CFG.FUNGI_BASE * CFG.DANGER_FUNGI[mode] + CFG.FUNGI_ENTRY;
        } else if (z.key === 'hell') {
          z.cost = CFG.HELL_CHUNKS[mode] * CFG.HELL_CHUNK_COST
                 + CFG.HELL_TRAVERSE[mode] * 1.0      // 空隙地形系数 1.0
                 + CFG.HELL_REFILL;
        }
      });
      return CFG.MODE;
    },

    // 法杖倍率 → 容量（迅捷之杖 1.25 固定 19 格，多重之杖 1.5 固定 26 格）
    STAFFS: [
      { key: '1', mult: 1, cap: 26, label: '一般法杖 ×1.0', icon: '' },
      { key: '1.25', mult: 1.25, cap: 19, label: '迅捷之杖 ×1.25', icon: 'STAFF_125' },
      { key: '1.5', mult: 1.5, cap: 26, label: '多重之杖 ×1.5', icon: 'STAFF_15' }
    ],
    STAFF_CAP: { '1': 26, '1.25': 19, '1.5': 26 },
    // 「追加*触发」系列：三者可互换，用于把被复制的多个法术打成一个组
    TRIGGERS: ['ADD_TRIGGER', 'ADD_TIMER', 'ADD_DEATH_TRIGGER'],
    // 载体必须搭配的触发（Wiki：黑洞 / 闪电弹 / 强烈汇聚之光 都要追加失效触发）
    CARRIER_TRIGGER: 'ADD_DEATH_TRIGGER',
    // 交换鹿需要非零伤害，以下修正可互换（红拳 / 蓝拳 / 线性弧 / 水平弧）
    DAMAGE_MODS: ['DAMAGE', 'LIGHT_SHOT', 'LINE_ARC', 'HORIZONTAL_ARC'],
    // 上/下飞对触手完全等价（触手不受方向影响，只把速度转成发射方向上的速度）
    FLY: ['FLY_UPWARDS', 'FLY_DOWNWARDS'],
    // 校准器用的瞄准修正
    ARCS: ['LINE_ARC', 'HORIZONTAL_ARC'],
    // 触手校准器用的失效触发投射物（必须能无视地形 / 从玩家身上发出）
    CALIB_CARRIERS: ['BLACK_HOLE_DEATH_TRIGGER', 'DELAYED_SPELL'],
    // 可选组件（不计入难度时会被忽略）
    OPTIONAL_IDS: { NOLLA: 1 },
    // 载荷预设（三者等价或可选）
    PAYLOADS: {
      none: [],
      grab: ['TELEPORT_PROJECTILE_CLOSER', 'CASTER_CAST'],
      orbit: ['TELEPORT_PROJECTILE_CLOSER', 'TRUE_ORBIT', 'ORBIT_LARPA'],
      swap: ['SWAPPER_PROJECTILE', 'EXPLODING_DEER']
    },
    // 相位载体（帧数来自 Wiki）
    PHASE_CARRIERS: [
      { id: 'SLOW_BULLET_TIMER', name: '定时能量球', kind: 'timer', frames: 100 },
      { id: 'BLACK_HOLE_DEATH_TRIGGER', name: '失效触发黑洞', kind: 'trigger', frames: 0 },
      { id: 'MEGALASER', name: '强烈汇聚之光', kind: 'trigger', frames: 0, needTrigger: true }
    ],
    PHASE_LIMITERS: [
      { id: 'LARPA_CHAOS', name: '混沌拉帕', frames: 300 },
      { id: 'LARPA_CHAOS_2', name: '复制轨迹', frames: 200 }
    ],
    // 黑洞必须飞出加载区（4 个区块 = 2048 px），否则闪电弹会撞墙
    BH_MIN_DIST: 2048,
    // 闪电弹存在时间修正上限：超过 +75f 会因重力严重下垂（+75 = 一个蓝表）
    LT_MAX_TIME_UP: 75,
    /**
     * 显示名覆盖：Wiki 官方名不太常用时改用社区更热门的叫法。
     * 未列出的法术仍用 name_official（缺省退回 Wiki 页面名）。
     */
    NAME_CN: {
      CASTER_CAST: '内在施法',
      TRUE_ORBIT: '行星环绕',
      BLACK_HOLE_DEATH_TRIGGER: '定时黑洞',
      EXPLOSIVE_PROJECTILE: '易爆',
      LIGHT_SHOT: '轻盈一击',
      ACCELERATING_SHOT: '逐渐加速',
      DECELERATING_SHOT: '逐渐减速',
      TENTACLE_TIMER: '定时触手',
      SLOW_BULLET_TIMER: '定时能量球',
      IF_HP: '条件-血量',
      IF_HALF: '条件-间隔',
      IF_END: '条件-结束',
      GAMMA: '伽马'
    },
    // 「我的法术」栏里显示的速度乘数 / 时间修正（其余位置不显示）
    SPEED_MULT: {
      PHASING_ARC: 0.33, ACCELERATING_SHOT: 0.32, HEAVY_SHOT: 0.3,
      EXPLOSIVE_PROJECTILE: 0.75, FIZZLE: 1.2, DECELERATING_SHOT: 1.68,
      LIGHT_SHOT: 7.5, SPEED: 2.5, SINEWAVE: 2, CHAOTIC_ARC: 2,
      SLIMEBALL: 1.1, FLY_UPWARDS: 1.2, FLY_DOWNWARDS: 1.2
    },
    TIME_DELTA: { LIFETIME: 75, ZERO_DAMAGE: 280, LIFETIME_DOWN: -42 },
    // 面板分区
    ROLE_CN: {
      speed: '速度修正', damage: '伤害修正', calibrator: '校准器',
      carrier: '跃迁载体', limit: '存在时间限制器', time: '存在时间修正',
      payload: '载荷与返回', trigger: '追加触发', dn: '一分为多',
      copy: '复制对象（被 Dn 复制）', aux: '其他辅助'
    },
    ROLE_ORDER: ['speed', 'damage', 'calibrator', 'carrier', 'limit', 'time',
                 'payload', 'trigger', 'dn', 'copy', 'aux']
  };
  // 用同一套公式归一化繁茂成本（避免手写常数与公式差最后几位）
  CFG.setMode('default');

  // ---------------------------------------------------------------- Dn 链
  var DN = (function () {
    var _chains = null;      // [{digits:[...], product, len}]
    var _products = null;    // Map product -> 最短链

    /** 枚举所有合法的 Dn 链（长度 1~4，逐位置受 DN_POSITIONS 约束） */
    function chains() {
      if (_chains) return _chains;
      var out = [];
      (function walk(prefix) {
        if (prefix.length) {
          var p = 1;
          for (var i = 0; i < prefix.length; i++) p *= prefix[i];
          out.push({ digits: prefix.slice(), product: p, len: prefix.length });
        }
        if (prefix.length >= CFG.DN_POSITIONS.length) return;
        var allowed = CFG.DN_POSITIONS[prefix.length];
        for (var k = 0; k < allowed.length; k++) {
          prefix.push(allowed[k]);
          walk(prefix);
          prefix.pop();
        }
      })([]);
      _chains = out;
      return out;
    }

    /** product -> 最短（同等长度取字典序最小）的链 */
    function productMap() {
      if (_products) return _products;
      var m = new Map();
      chains().forEach(function (c) {
        var cur = m.get(c.product);
        if (!cur || c.len < cur.len ||
            (c.len === cur.len && c.digits.join(',') < cur.digits.join(','))) {
          m.set(c.product, c);
        }
      });
      _products = m;
      return m;
    }

    function products() {
      return Array.from(productMap().keys()).sort(function (a, b) { return a - b; });
    }

    /**
     * 把「需要的复制份数」拆成 ≤maxChains 条链（可选 +1 本体）。
     * @param {number} n 目标份数（未含回绕）
     * @param {object} opt {allowBody:true, maxChains:2, limit:6}
     * @returns {Array<{chains:Array, body:boolean, total:number}>}
     */
    function decompose(n, opt) {
      opt = opt || {};
      var allowBody = opt.allowBody !== false;
      var maxChains = opt.maxChains || CFG.DN_MAX_CHAINS;
      var limit = opt.limit || 6;
      var ps = products();
      var res = [];
      var seen = new Set();

      function push(chainArr, body) {
        var total = body ? 1 : 0;
        chainArr.forEach(function (p) { total += p; });
        if (total !== n) return;
        var key = chainArr.join('|') + (body ? '+1' : '');
        if (seen.has(key)) return;
        seen.add(key);
        res.push({
          chains: chainArr.map(function (p) { return productMap().get(p); }),
          body: body,
          total: total
        });
      }

      // 0 条链
      if (allowBody && n === 1) push([], true);
      // 1 条链
      if (maxChains >= 1) {
        ps.forEach(function (p) {
          if (p === n) push([p], false);
          if (allowBody && p + 1 === n) push([p], true);
        });
      }
      // 2 条链
      if (maxChains >= 2) {
        for (var i = 0; i < ps.length; i++) {
          for (var j = i; j < ps.length; j++) {
            var sum = ps[i] + ps[j];
            if (sum > n) break;
            if (sum === n) push([ps[i], ps[j]], false);
            if (allowBody && sum + 1 === n) push([ps[i], ps[j]], true);
          }
        }
      }
      res.sort(function (a, b) {
        if (a.chains.length !== b.chains.length) return a.chains.length - b.chains.length;
        return b.chains.reduce(function (s, c) { return s + c.len; }, 0) -
               a.chains.reduce(function (s, c) { return s + c.len; }, 0);
      });
      return res.slice(0, limit);
    }

    /** 可达份数集合（≤max，含可选回绕 ×2） */
    function reachable(max, opt) {
      opt = opt || {};
      var allowBody = opt.allowBody !== false;
      var maxChains = opt.maxChains || CFG.DN_MAX_CHAINS;
      var wrap = opt.wrap !== false;
      var ps = products();
      var set = new Set();
      function add(v) {
        if (v <= 0) return;
        if (v <= max) set.add(v);
        if (wrap && v * 2 <= max) set.add(v * 2);
      }
      add(1); add(0);                                        // 仅本体 / 无
      ps.forEach(function (p) { add(p); if (allowBody) add(p + 1); });
      if (maxChains >= 2) {
        for (var i = 0; i < ps.length; i++) {
          for (var j = i; j < ps.length; j++) {
            var s = ps[i] + ps[j];
            if (s > max) break;
            add(s);
            if (allowBody) add(s + 1);
          }
        }
      }
      return set;
    }

    return { chains: chains, products: products, productMap: productMap,
             decompose: decompose, reachable: reachable };
  })();

  // ---------------------------------------------------------------- 权重
  var Weights = (function () {
    var _cache = null, _tier = null;

    /**
     * @param {Array} spells data/spell_weights.json 的 spells 数组
     * @param {object} opt {scheme:'pct'|'raw'}
     *
     * 注：v0.2.2 起**不再有「等级倍率」**。旧版的「繁茂 2/3/4 级 ×2.0、地狱 10 级 ×3.0」
     * 是 v3 口径的经验补偿，用来把「模式内等级均匀」的偏差拉回来；v7.2 改成按精确等级
     * 算真实命中率之后，这两个倍率既不参与 S 值也不参与策略建议，是死参数，已删除
     * （见 docs/权重口径评估.md §15）。
     */
    function build(spells, opt) {
      opt = opt || {};
      var scheme = opt.scheme || 'pct';

      var map = {}, tierP = {};
      spells.forEach(function (s) {
        if (s.status !== 'ok') { map[s.id] = 0; tierP[s.id] = {}; return; }
        var tiers = scheme === 'raw' ? (s.tiers_raw || {}) : (s.tiers_pct || {});
        var wsum = 0, per = {};
        Object.keys(tiers).forEach(function (t) {
          var v = tiers[t];
          if (!(v > 0)) return;
          // pct 以百分比存储 → 除以 100 得到「该等级内命中该法术的概率」
          per[t] = scheme === 'raw' ? v : v / 100;
          wsum += v;
        });
        map[s.id] = wsum;        // 权重 = Σ 各等级百分比（不再乘倍率）
        tierP[s.id] = per;
      });
      _cache = map;
      _tier = tierP;
      return map;
    }

    function get(id) {
      if (!_cache) throw new Error('Weights.build() 未调用');
      return _cache[id] || 0;
    }

    /** 某法术在某等级「等级内命中概率」（0~1） */
    function tierProb(id, t) {
      if (!_tier) throw new Error('Weights.build() 未调用');
      var m = _tier[id];
      return (m && m[t]) || 0;
    }

    return { build: build, get: get, tierProb: tierProb };
  })();

  // ---------------------------------------------------------------- 相位
  var Phase = (function () {
    /**
     * 通用跳跃次数（含「重叠吞跳」处理）
     *   X = 计时时长；相位第 1 帧不倒计时 → 首次跳跃在第 13 帧
     *   若最后一跳恰好落在失效帧 → 该跳被吞（额外 −1 跳）
     */
    function jumps(x) {
      if (!(x > 1)) return 0;
      var n = Math.floor((x - 1) / CFG.PHASE.jumpEvery);
      if ((x - 1) % CFG.PHASE.jumpEvery === 0) n -= 1;
      return Math.max(0, n);
    }

    /** 定时载体：定时帧释放载荷但本体不失效，不会吞跳 */
    function timerJumps(frames) {
      if (!(frames > 1)) return 0;
      return Math.max(0, Math.floor((frames - 1) / CFG.PHASE.jumpEvery));
    }

    /** 最大存在时间限制：帧数 +1（限制从第 1 帧起算），重叠吞跳 */
    function limitJumps(frames) { return jumps(frames + 1); }

    function distance(phases, jumpCount) {
      return CFG.PHASE.jumpDist * phases * jumpCount;
    }

    /** 枚举「载体 × 限制器」组合 */
    function combos() {
      var out = [];
      CFG.PHASE_CARRIERS.forEach(function (c) {
        if (c.kind === 'timer') {
          out.push({ carrier: c, limiter: null, x: c.frames,
                     jumps: timerJumps(c.frames),
                     label: c.name + '（定时 ' + c.frames + 'f）' });
        } else {
          CFG.PHASE_LIMITERS.forEach(function (l) {
            out.push({ carrier: c, limiter: l, x: l.frames + 1,
                       jumps: limitJumps(l.frames),
                       label: c.name + ' + ' + l.name + '（限制 ' + l.frames + 'f）' });
          });
        }
      });
      return out;
    }

    return { jumps: jumps, timerJumps: timerJumps, limitJumps: limitJumps,
             distance: distance, combos: combos };
  })();

  // ---------------------------------------------------------------- 评分
  /* ==========================================================================
   * Score —— 收集难度（口径 v7.2，docs/权重口径评估.md §11~§12）
   *
   * 单位：1 = 直线穿过 1 个 chunk（512 px）空隙地形的时间。
   *
   *   1) 每个缺失法术在三个区域各有「走一轮能拿到几份」Y_z(s)（见 Plan.yields）
   *   2) 单份成本 = 缺口 / Y_z(s)，单位「轮」
   *   3) 指派：让总耗时最小（初值各自最有利 + 最速下降）
   *   4) 区域聚合：k_z = ( Σ cost³ )^(1/3) 轮（同一区域是「一起刷」的，由最难凑的项主导）
   *      time_z = k_z × 单轮耗时 + max(0, k_z − 1) × 换世界成本
   *   5) 总难度 S = Σ_z time_z
   *
   * 为什么换世界要单独加：圣山/繁茂 刷完一轮库存就空了，第二轮起要跨平行世界（113.2）；
   * 地狱可以原地重刷（重刷成本已摊进单轮），所以没有这一项。
   * ========================================================================== */
  var Score = (function () {
    var NO_DATA = 1e6;
    var NORM_K = 3;

    function cube(x) { return x * x * x; }
    function cbrt(x) { return Math.pow(x, 1 / NORM_K); }

    /**
     * 各区域走 ks[g] 轮的总时间。
     *
     * ⚠️ 换世界成本是**共享**的：主世界 7 座圣山已搜完，所以第一次进圣山/繁茂就要跨一次
     * 平行世界；一趟平行世界同时补满圣山（6 座）和繁茂（53 chunk），
     * 所以「开世界次数 = 需要跨世界的区域里轮数最多的那个」，不是各区相加。
     */
    function zoneTimes(ks) {
      var Z = CFG.ZONES, total = 0, hops = 0, worldK = 0;
      for (var g = 0; g < Z.length; g++) {
        var k = ks[g] || 0;
        total += k * Z[g].cost;
        if (Z[g].needsWorld) {
          if (k > hops) hops = k;
          worldK += k;
        }
      }
      return { total: total + hops * CFG.WORLD_RESET, hops: hops, worldK: worldK };
    }

    /** 单个区域的时间份额（换世界成本按轮数比例摊给需要跨世界的区域） */
    function stageSplit(ks) {
      var Z = CFG.ZONES;
      var info = zoneTimes(ks);
      var hopCost = info.hops * CFG.WORLD_RESET;
      return Z.map(function (z, g) {
        var k = ks[g] || 0;
        var share = (z.needsWorld && info.worldK > 0) ? hopCost * k / info.worldK : 0;
        return { rounds: k, time: k * z.cost + share };
      });
    }

    /** 该区域「第一轮」的有效成本：需要跨世界的刷点要连换世界一起付（主世界圣山已搜完） */
    function firstRoundCost(z) {
      return z.cost + (z.needsWorld ? CFG.WORLD_RESET : 0);
    }

    /** 单份该法术的耗时（在最优区域） */
    function unitCost(id) {
      var y = Plan.yields(id), best = NO_DATA;
      CFG.ZONES.forEach(function (z) {
        if (y[z.key] > 0) best = Math.min(best, firstRoundCost(z) / y[z.key]);
      });
      return best;
    }

    /** 某个法术最有利的区域 */
    function bestZone(id) {
      var y = Plan.yields(id), best = null, bestRate = -1;
      CFG.ZONES.forEach(function (z) {
        var rate = y[z.key] > 0 ? y[z.key] / firstRoundCost(z) : 0;
        if (rate > bestRate) { bestRate = rate; best = z; }
      });
      return { zone: best, rate: bestRate };
    }

    /**
     * 指派：把每个缺失法术分到某个区域，使「区域时间求和」最小。
     * 初值取各自最有利，再做最速下降（单步只接受最优的那一次移动）。
     */
    function assignZones(items) {
      var Z = CFG.ZONES, G = Z.length, n = items.length;
      if (!n) return { assign: [], cost: [], stages: [], total: 0 };

      var cost = [], acc = [], assign = [];
      for (var g = 0; g < G; g++) acc[g] = 0;

      for (var i = 0; i < n; i++) {
        var y = Plan.yields(items[i].id);
        cost[i] = [];
        var b = 0;
        for (g = 0; g < G; g++) {
          var yz = y[Z[g].key];
          cost[i][g] = yz > 0 ? items[i].lack / yz : NO_DATA * items[i].lack;
          if (cost[i][g] < cost[i][b]) b = g;
        }
        assign[i] = b;
        acc[b] += cube(cost[i][b]);
      }

      function ksOf(a) {
        var ks = [];
        for (var g2 = 0; g2 < G; g2++) ks[g2] = cbrt(a[g2]);
        return ks;
      }
      var cur = zoneTimes(ksOf(acc));

      for (var iter = 0; iter < 24; iter++) {
        var bestDelta = -1e-9, bi = -1, bg = -1, bestKs = null, bestTotal = cur.total;
        for (i = 0; i < n; i++) {
          var from = assign[i];
          for (g = 0; g < G; g++) {
            if (g === from) continue;
            var a1 = acc[from] - cube(cost[i][from]); if (a1 < 0) a1 = 0;
            var a2 = acc[g] + cube(cost[i][g]);
            var save1 = acc[from], save2 = acc[g];
            acc[from] = a1; acc[g] = a2;
            var ks2 = ksOf(acc), ev = zoneTimes(ks2);
            acc[from] = save1; acc[g] = save2;
            if (ev.total - cur.total < bestDelta) {
              bestDelta = ev.total - cur.total; bi = i; bg = g;
              bestKs = ks2; bestTotal = ev.total;
            }
          }
        }
        if (bi < 0) break;
        acc[assign[bi]] -= cube(cost[bi][assign[bi]]);
        assign[bi] = bg;
        acc[bg] += cube(cost[bi][bg]);
        cur = { total: bestTotal, ks: bestKs };
      }

      var ks = ksOf(acc);
      var split = stageSplit(ks);
      var stages = split.map(function (x) { return x.time; });
      var rounds = split.map(function (x) { return x.rounds; });
      return { assign: assign, cost: cost, stages: stages, rounds: rounds,
               total: zoneTimes(ks).total, hops: zoneTimes(ks).hops };
    }

    /**
     * 相对难度（S 值，单位「走过 1 个区块的时间」，越小越容易凑）
     */
    function missingCost(need, owned, guar, opt) {
      opt = opt || {};
      var skipOptional = !!opt.ignoreOptional;
      var Z = CFG.ZONES;

      // ---- 1) 收集缺口
      var items = [], missingKinds = 0, missingPieces = 0;
      Object.keys(need).forEach(function (id) {
        if (skipOptional && CFG.OPTIONAL_IDS[id]) return;
        var n = need[id];
        var o = (guar && guar[id]) ? n : (owned[id] || 0);
        var lack = Math.max(0, n - o);
        if (lack <= 0) return;
        items.push({ id: id, lack: lack, need: n, owned: o });
        missingKinds += 1;
        missingPieces += lack;
      });

      var plan = assignZones(items);
      var detail = [], groups = [], acc = {};
      items.forEach(function (it, i) {
        var g = plan.assign[i];
        var z = Z[g];
        var c = plan.cost[i][g];
        detail.push({ id: it.id, need: it.need, owned: it.owned, lack: it.lack,
                      cost: c, zone: z.key, zoneLabel: z.label });
        (acc[z.key] = acc[z.key] || []).push(c);
      });

      Z.forEach(function (z, g) {
        var cs = acc[z.key];
        if (!cs) return;
        var cubeSum = 0;
        cs.forEach(function (c) { cubeSum += cube(c); });
        groups.push({ key: z.key, label: z.label, cost: plan.stages[g],
                      rounds: plan.rounds[g], pieces: cs.length });
      });
      groups.sort(function (a, b) { return b.cost - a.cost; });
      detail.sort(function (a, b) { return b.cost - a.cost; });

      return { sum: plan.total, kinds: missingKinds, pieces: missingPieces,
               detail: detail, groups: groups };
    }

    /** 并列时的次级排序：误差 → 缺失种类数 → 总份数 */
    function tieBreak(a, b) {
      if (a.error !== b.error) return a.error - b.error;
      if (a.score.kinds !== b.score.kinds) return a.score.kinds - b.score.kinds;
      return a.score.pieces - b.score.pieces;
    }

    /** 默认排序：相对难度升序，并列时按 tieBreak */
    function byWeight(a, b) {
      if (a.score.sum !== b.score.sum) return a.score.sum - b.score.sum;
      return tieBreak(a, b);
    }

    /** 备选排序：误差优先 */
    function byError(a, b) { return tieBreak(a, b); }

    return { missingCost: missingCost, missingWeight: missingCost, unitCost: unitCost,
             assignZones: assignZones,
             bestZone: bestZone, zoneTimes: zoneTimes, stageSplit: stageSplit,
             firstRoundCost: firstRoundCost,
             tieBreak: tieBreak, byWeight: byWeight, byError: byError };
  })();

  // ---------------------------------------------------------------- 分区工具
  var Zone = (function () {
    function make(key, label, items, opt) {
      opt = opt || {};
      return {
        key: key, label: label, items: items || {},
        optional: !!opt.optional,
        note: opt.note || '',
        hint: opt.hint || '',
        staff: opt.staff || null
      };
    }

    function add(items, id, n) {
      items[id] = (items[id] || 0) + (n == null ? 1 : n);
      return items;
    }

    /** 合并所有分区的法术需求 */
    function flatten(zones) {
      var need = {};
      zones.forEach(function (z) {
        Object.keys(z.items).forEach(function (id) {
          need[id] = (need[id] || 0) + z.items[id];
        });
      });
      return need;
    }

    /** 槽位总数（含可选组件，因为物理上都要占格） */
    function slots(need) {
      var n = 0;
      Object.keys(need).forEach(function (k) { n += need[k]; });
      return n;
    }

    /** 从等价候选中挑一个：优先已拥有，其次最容易获取 */
    function pickAlt(ids, owned, guar) {
      var best = ids[0], bestOwn = -1, bestCost = Infinity;
      ids.forEach(function (id) {
        var o = (guar && guar[id]) ? 99 : (owned[id] || 0);
        var c = Score.unitCost(id);
        if (o > bestOwn || (o === bestOwn && c < bestCost)) {
          best = id; bestOwn = o; bestCost = c;
        }
      });
      return best;
    }

    /**
     * 在若干「整组方案」中挑最省的一组。每个方案是 {spellId: 份数}。
     * 用于「失效触发黑洞 ≡ 追加失效触发 + 普通黑洞」这类多卡对单卡的等价关系。
     */
    function pickCheapest(options, owned, guar) {
      var best = options[0], bestCost = Infinity, bestSlots = Infinity;
      options.forEach(function (opt) {
        var c = 0, n = 0;
        Object.keys(opt).forEach(function (id) {
          var need = opt[id];
          n += need;
          if (guar && guar[id]) return;
          var lack = Math.max(0, need - (owned[id] || 0));
          if (lack > 0) c += Score.unitCost(id) * lack;
        });
        if (c < bestCost - 1e-9 || (Math.abs(c - bestCost) < 1e-9 && n < bestSlots)) {
          best = opt; bestCost = c; bestSlots = n;
        }
      });
      return best;
    }

    /**
     * 加「一个失效触发的黑洞」。
     * Wiki：失效触发黑洞在效果上完全等同于「追加失效触发 + 普通黑洞」，两者按获取难度择优。
     */
    function addDeathTrigger(items, owned, guar) {
      var opt = pickCheapest([
        { BLACK_HOLE_DEATH_TRIGGER: 1 },
        { ADD_DEATH_TRIGGER: 1, BLACK_HOLE: 1 }
      ], owned, guar);
      Object.keys(opt).forEach(function (id) { add(items, id, opt[id]); });
      return opt;
    }

    /** 加「一个可作为校准器的失效触发投射物」 */
    function addCalibCarrier(items, owned, guar) {
      var opt = pickCheapest([
        { BLACK_HOLE_DEATH_TRIGGER: 1 },
        { ADD_DEATH_TRIGGER: 1, BLACK_HOLE: 1 },
        { DELAYED_SPELL: 1 }
      ], owned, guar);
      Object.keys(opt).forEach(function (id) { add(items, id, opt[id]); });
      return opt;
    }

    return { make: make, add: add, flatten: flatten, slots: slots, pickAlt: pickAlt,
             pickCheapest: pickCheapest, addDeathTrigger: addDeathTrigger,
             addCalibCarrier: addCalibCarrier };
  })();

  // ---------------------------------------------------------------- 复制链
  var Chain = (function () {
    /**
     * 复制链的辅助法术需求
     *   「追加*触发」的作用：把被复制的多个法术打成一个组（Dn 只复制紧跟其后的一个法术）。
     *   - 单链 + 只复制 1 个法术 → Dn 直接复制该法术，不需要追加触发
     *   - 单链 + 复制多个法术   → 需要 1 个追加触发把它们归组
     *   - 两条链               → 每条链各需要 1 个追加触发
     *   刷新环：需要两条链时必须；需要回绕时必须。
     */
    function extras(chains, copiedSpells, wrap) {
      var n = chains.length;
      var triggers = 0;
      if (n >= 2) triggers = 2;
      else if (n === 1 && copiedSpells >= 2) triggers = 1;
      return {
        triggers: triggers,
        reset: (n >= 2) || !!wrap,
        resetReason: (n >= 2 && wrap) ? '两条链 + 回绕'
                   : (n >= 2 ? '需要两条复制链' : (wrap ? '需要回绕' : ''))
      };
    }

    /**
     * 复制链行的提示语
     *   禁抽：Dn 复制修正时会过量抽取（从第 2 份复制起每份抽一次），靠 Dn 的摆放顺序实现禁抽。
     *   刷新环：两条链 或 回绕时必须；在法杖末端放刷新环配合条件法术也能规避多数过量抽取。
     */
    function hint(dec, ex) {
      var parts = [];
      if (dec && dec.chains.length) parts.push('Dn 链需禁抽（靠 Dn 的摆放顺序实现）');
      if (ex && ex.reset) parts.push('含刷新环：' + ex.resetReason);
      return parts.join('；');
    }

    /** Dn 链文本：D3 → D3 → D2 ⇒ 共 18 份 */
    function note(dec, unit) {
      if (!dec) return '';
      var chains = dec.chains.map(function (c) { return 'D' + c.digits.join('→D'); });
      var body = dec.body ? ' + 本体' : '';
      var txt = (chains.length ? chains.join(' ＋ ') : '无链') + body +
                ' ⇒ 共 ' + dec.total + ' ' + unit;
      if (dec.chains.length && !dec.body) txt += '（不含本体）';
      return txt;
    }

    return { extras: extras, note: note, hint: hint };
  })();

  // ---------------------------------------------------------------- 求解器
  var Solve = (function () {
    var _decCache = new Map();

    function decomposeCached(n, opt) {
      var key = n + '|' + (opt.allowBody !== false ? 1 : 0) + '|' + (opt.maxChains || 2);
      if (!_decCache.has(key)) {
        _decCache.set(key, DN.decompose(n, {
          allowBody: opt.allowBody !== false,
          maxChains: opt.maxChains || 2,
          limit: 4
        }));
      }
      return _decCache.get(key);
    }

    /** 一条或多条链实际要占用的 Dn 法术（同种可重复，如两条链各要一个 D4） */
    function dnNeed(chains) {
      var need = {};
      chains.forEach(function (c) {
        c.digits.forEach(function (d) {
          var id = 'DIVIDE_' + d;
          need[id] = (need[id] || 0) + 1;
        });
      });
      return need;
    }

    /**
     * 相位页求解
     * 注意：Dn 链复制的是「效果」，不是实体。
     *   需要的相位弧度实体恒为 1 个（本体），DN 法术按链上位置各 1 个。
     * @param {object} opt {distance, tolerance, wrap, multiChain, allowBody, maxPhases,
     *                      owned, guaranteed, payload, calibrator, ignoreOptional}
     */
    function phase(opt) {
      opt = opt || {};
      var D = opt.distance;
      var tol = opt.tolerance || 0;
      var wrap = !!opt.wrap;
      var allowBody = opt.allowBody !== false;
      var maxChains = opt.multiChain ? 2 : 1;
      var maxP = opt.maxPhases || CFG.PHASE.maxPhases;
      var owned = opt.owned || {};
      var guar = opt.guaranteed || {};
      var payload = opt.payload || [];
      var swap = payload.indexOf('SWAPPER_PROJECTILE') >= 0;
      var out = [];

      var combos = Phase.combos();
      var reach = Array.from(DN.reachable(maxP, { allowBody: allowBody, maxChains: maxChains, wrap: false }))
        .sort(function (a, b) { return a - b; });

      // 交换鹿只能配「追加失效触发」类载体（定时载体是追加定时触发，不行）
      var usable = combos.filter(function (cb) {
        if (!swap) return true;
        return cb.carrier.kind === 'trigger';
      });

      usable.forEach(function (cb) {
        reach.forEach(function (pPhys) {
          var pEff = wrap ? pPhys * 2 : pPhys;
          var dist = Phase.distance(pEff, cb.jumps);
          var err = Math.abs(dist - D);
          if (err > tol) return;
          var decs = decomposeCached(pPhys, { allowBody: allowBody, maxChains: maxChains });
          if (!decs.length) return;

          decs.forEach(function (dec) {
            var zones = [];
            var ex = Chain.extras(dec.chains, 1, wrap);

            // ---- 复制链
            var copyItems = {};
            var dn = dnNeed(dec.chains);
            Object.keys(dn).forEach(function (k) { Zone.add(copyItems, k, dn[k]); });
            Zone.add(copyItems, 'PHASING_ARC', 1);
            for (var ti = 0; ti < ex.triggers; ti++) {
              Zone.add(copyItems, Zone.pickAlt(CFG.TRIGGERS, owned, guar), 1);
            }
            if (ex.reset) Zone.add(copyItems, 'RESET', 1);
            zones.push(Zone.make('copy', '复制链', copyItems, {
              note: Chain.note(dec, '份相位') +
                    (dec.chains.length && !dec.body ? '；本体需用条件法术弃掉' : ''),
              hint: Chain.hint(dec, ex),
              wrap: wrap
            }));

            // ---- 额外速度乘数（相位堆太多会把速度乘数压到 0）
            var speedItems = {};
            if (pEff > CFG.PHASE.speedZeroAt) Zone.add(speedItems, 'SPEED', 1);
            if (Object.keys(speedItems).length) {
              zones.push(Zone.make('speed', '额外速度乘数', speedItems, {
                note: pEff > CFG.PHASE.speedZeroAt
                  ? '相位 ' + pEff + ' 份会把速度乘数压到接近 0，必须配加速平衡' : ''
              }));
            }

            // ---- 必需组件（载体 + 限制器）
            var reqItems = {};
            if (cb.carrier.id === 'BLACK_HOLE_DEATH_TRIGGER') {
              Zone.addDeathTrigger(reqItems, owned, guar);
            } else {
              Zone.add(reqItems, cb.carrier.id, 1);
              if (cb.carrier.needTrigger) Zone.add(reqItems, CFG.CARRIER_TRIGGER, 1);
            }
            if (cb.limiter) Zone.add(reqItems, cb.limiter.id, 1);
            if (dec.chains.length && !dec.body) Zone.add(reqItems, 'IF_HP', 1);
            zones.push(Zone.make('req', '必需组件', reqItems, {
              note: (dec.chains.length && !dec.body) ? '条件-血量用来弃掉修正本体' : ''
            }));

            // ---- 载荷（必需：用户可选类型，但选哪种都必需）
            if (payload.length) {
              var payItems = {};
              payload.forEach(function (id) { Zone.add(payItems, id, 1); });
              zones.push(Zone.make('payload', '载荷', payItems));
            }

            // ---- 可选组件（校准器 + 零时）
            var optItems = {};
            if (opt.calibrator) {
              Zone.add(optItems, Zone.pickAlt(CFG.ARCS, owned, guar), 1);
              Zone.add(optItems, 'NOLLA', 1);
            }
            if (Object.keys(optItems).length) {
              zones.push(Zone.make('optional', '可选组件', optItems, {
                optional: true, note: '校准器（瞄准用，可手动瞄准省掉）'
              }));
            }

            pushSolution(out, {
              page: 'phase', combo: cb, pPhys: pPhys, pEff: pEff,
              dist: dist, error: err, dec: dec, zones: zones,
              wrap: wrap, opt: opt, owned: owned, guar: guar
            });
          });
        });
      });

      // 去重（同一 combo + 同一份数 + 同一链结构）
      var seen = new Set(), uniq = [];
      out.forEach(function (s) {
        var key = s.combo.label + '|' + s.pPhys + '|' +
                  s.dec.chains.map(function (c) { return c.digits.join(''); }).join('+') +
                  (s.dec.body ? '+1' : '');
        if (seen.has(key)) return;
        seen.add(key); uniq.push(s);
      });
      uniq.sort(opt.sortMode === 'error' ? Score.byError : Score.byWeight);
      return uniq;
    }

    return { phase: phase, dnNeed: dnNeed, decomposeCached: decomposeCached };
  })();

  /** 统一收尾：合并 need、评分、槽位、超容 */
  function pushSolution(out, s) {
    var need = Zone.flatten(s.zones);
    if (overMaxPerSpell(need, s.opt.maxPerSpell)) return;
    var score = Score.missingCost(need, s.owned, s.guar, s.opt);
    var slots = Zone.slots(need);
    var cap = s.staff ? s.staff.cap : 26;
    s.need = need;
    s.score = score;
    s.slots = slots;
    s.staffCap = cap;
    s.overCapacity = slots > cap;
    out.push(s);
  }

  // ---------------------------------------------------------------- 触手页
  var Tentacle = (function () {
    var V1 = 7.92;
    var FLY_V = 1.2;
    // 顺序与 v0.7 一致（clamp 链依赖顺序）
    var SPEED = [
      { id: 'PHASING_ARC', v: 0.33, name: '相位弧度' },
      { id: 'ACCELERATING_SHOT', v: 0.32, name: '逐渐加速' },
      { id: 'HEAVY_SHOT', v: 0.3, name: '沉重一击' },
      { id: 'EXPLOSIVE_PROJECTILE', v: 0.75, name: '易爆的投射物' },
      { id: 'FIZZLE', v: 1.2, name: '闪灭' },
      { id: 'DECELERATING_SHOT', v: 1.68, name: '逐渐减速' },
      { id: 'LIGHT_SHOT', v: 7.5, name: '轻盈一击' },
      { id: 'SPEED', v: 2.5, name: '加速' },
      { id: 'SINEWAVE', v: 2, name: '蛇行' },
      { id: 'CHAOTIC_ARC', v: 2, name: '混乱之路' }
    ];
    var _poolCache = {};

    function clampStep(x, f) {
      var v = x * f;
      if (v < 0) return 0;
      if (v > 20) return 20;
      return v;
    }

    /**
     * α 链
     * @param {number} staffMult 法杖速度倍率；用校准器时传 1（校准器会规避法杖的隐藏倍率）
     */
    function alphaChain(staffMult, slime, cnt) {
      var x = 1;
      if (staffMult && staffMult !== 1) x = clampStep(x, staffMult);
      if (slime) x = clampStep(x, 1.1);
      for (var i = 0; i < SPEED.length; i++) {
        for (var r = 0; r < (cnt[i] || 0); r++) x = clampStep(x, SPEED[i].v);
      }
      return x;
    }

    /**
     * 预计算所有速度修正组合（总个数 ≤ maxMods），按 α 升序
     * @param {number} maxMods
     * @param {boolean} calibrator 用校准器时法杖倍率不参与（两者至多一个）
     * @param {Array<number>} staffMults 允许的法杖倍率
     */
    function pool(maxMods, calibrator, staffMults) {
      var mults = calibrator ? [1] : (staffMults || [1, 1.25, 1.5]);
      var ck = maxMods + '|' + calibrator + '|' + mults.join(',');
      if (_poolCache[ck]) return _poolCache[ck];
      var list = [];
      var cnt = new Array(SPEED.length).fill(0);
      (function walk(idx, left) {
        if (idx === SPEED.length) {
          mults.forEach(function (st) {
            [false, true].forEach(function (sl) {
              if (st === 1 && !sl && cnt.every(function (c) { return c === 0; })) {
                list.push({ alpha: 1, cnt: cnt.slice(), staff: 1, slime: false, mods: 0 });
                return;
              }
              var used = cnt.reduce(function (s, c) { return s + c; }, 0);
              list.push({ alpha: alphaChain(st, sl, cnt), cnt: cnt.slice(),
                          staff: st, slime: sl, mods: used });
            });
          });
          return;
        }
        for (var c = 0; c <= left; c++) {
          cnt[idx] = c;
          walk(idx + 1, left - c);
        }
        cnt[idx] = 0;
      })(0, maxMods);
      list.sort(function (a, b) { return a.alpha - b.alpha; });
      _poolCache[ck] = list;
      return list;
    }

    function staffOf(mult) {
      for (var i = 0; i < CFG.STAFFS.length; i++) {
        if (CFG.STAFFS[i].mult === mult) return CFG.STAFFS[i];
      }
      return CFG.STAFFS[0];
    }

    /**
     * 触手页求解
     *   d = 7.92 × 1.2^n × α
     *   上/下飞对触手完全等价（触手不受方向影响）
     */
    function solve(opt) {
      opt = opt || {};
      var D = opt.distance;
      var tol = opt.tolerance || 0;
      var Nmax = opt.maxUpDown != null ? opt.maxUpDown : 100;
      var maxMods = opt.maxSpeedMods != null ? opt.maxSpeedMods : 5;
      var wrap = !!opt.wrap;
      var calibrator = !!opt.calibrator;
      var owned = opt.owned || {};
      var guar = opt.guaranteed || {};
      var payload = opt.payload || [];
      var maxChains = opt.multiChain ? 2 : 1;
      var flyId = Zone.pickAlt(CFG.FLY, owned, guar);
      var out = [];

      var list = pool(maxMods, calibrator, opt.staffMults);
      var LN12 = Math.log(FLY_V);

      // 以 α 为主轴：对每个 α 反解 n，避免「n 取整数导致 α 无解」
      for (var pi = 0; pi < list.length; pi++) {
        var p = list[pi];
        var ideal = Math.log(D / (V1 * p.alpha)) / LN12;
        if (!isFinite(ideal) || ideal < -0.5) continue;

        var cands;
        if (wrap) {
          var half = ideal / 2;
          cands = [Math.floor(half), Math.ceil(half)];
        } else {
          cands = [Math.floor(ideal), Math.ceil(ideal)];
        }
        var seenN = {};
        for (var ci = 0; ci < cands.length; ci++) {
          var nPhys = cands[ci];
          if (nPhys < 0 || nPhys > Nmax) continue;
          var nEff = wrap ? nPhys * 2 : nPhys;
          if (nEff > 1601) continue;
          if (seenN[nPhys]) continue;
          seenN[nPhys] = 1;

          var base = V1 * Math.pow(FLY_V, nEff);
          var d = base * p.alpha;
          var err = Math.abs(d - D);
          if (err > tol) continue;

          var decs = (nPhys > 0)
            ? Solve.decomposeCached(nPhys, { allowBody: opt.allowBody !== false, maxChains: maxChains })
            : [{ chains: [], body: false, total: 0 }];
          if (!decs.length) continue;

          for (var di = 0; di < decs.length; di++) {
            var dec = decs[di];
            var zones = [];
            var ex = Chain.extras(dec.chains, 1, wrap);

            // ---- 复制链
            var copyItems = {};
            var dn = Solve.dnNeed(dec.chains);
            Object.keys(dn).forEach(function (k2) { Zone.add(copyItems, k2, dn[k2]); });
            if (nPhys > 0) Zone.add(copyItems, flyId, 1);
            for (var ti = 0; ti < ex.triggers; ti++) {
              Zone.add(copyItems, Zone.pickAlt(CFG.TRIGGERS, owned, guar), 1);
            }
            if (ex.reset) Zone.add(copyItems, 'RESET', 1);
            zones.push(Zone.make('copy', '复制链', copyItems, {
              note: Chain.note(dec, '份上/下飞') +
                    (dec.chains.length && !dec.body ? '；本体需用条件法术弃掉' : ''),
              hint: Chain.hint(dec, ex)
            }));

            // ---- 额外速度乘数
            var speedItems = {};
            for (var si = 0; si < SPEED.length; si++) {
              if (p.cnt[si]) Zone.add(speedItems, SPEED[si].id, p.cnt[si]);
            }
            if (p.slime) Zone.add(speedItems, 'SLIMEBALL', 1);
            if (Object.keys(speedItems).length) {
              zones.push(Zone.make('speed', '额外速度乘数', speedItems));
            }

            // ---- 必需组件（载体 + 回绕用的条件法术）
            var reqItems = {};
            Zone.add(reqItems, 'TENTACLE_TIMER', 1);
            if (dec.chains.length && !dec.body) Zone.add(reqItems, 'IF_HP', 1);
            if (wrap) {
              Zone.add(reqItems, 'IF_HALF', 1);
              Zone.add(reqItems, 'IF_END', 1);
            }
            var reqNote = [];
            if (dec.chains.length && !dec.body) reqNote.push('条件-血量用来弃掉修正本体');
            if (wrap) reqNote.push('条件-间隔 / 条件-结束让校准器与速度修正只释放一次');
            zones.push(Zone.make('req', '必需组件', reqItems, {
              note: reqNote.join('；')
            }));

            // ---- 载荷（必需：用户可选类型，但选哪种都必需）
            if (payload.length) {
              var payItems = {};
              payload.forEach(function (id) { Zone.add(payItems, id, 1); });
              zones.push(Zone.make('payload', '载荷', payItems));
            }

            // ---- 可选组件（校准器 + 零时）
            var optItems = {};
            if (calibrator) {
              Zone.addCalibCarrier(optItems, owned, guar);
              Zone.add(optItems, Zone.pickAlt(CFG.ARCS, owned, guar), 1);
              Zone.add(optItems, 'NOLLA', 1);
            }
            if (Object.keys(optItems).length) {
              zones.push(Zone.make('optional', '可选组件', optItems, {
                optional: true,
                note: '校准器：失效触发投射物 + 瞄准修正（让触手继承方向，并规避法杖隐藏倍率）'
              }));
            }

            var sol = {
              page: 'tentacle', nPhys: nPhys, nEff: nEff, alpha: p.alpha,
              staffMult: p.staff, staff: calibrator ? null : staffOf(p.staff),
              slime: p.slime, cnt: p.cnt.slice(),
              dist: d, error: err, dec: dec, zones: zones,
              calibrator: calibrator, wrap: wrap, opt: opt,
              owned: owned, guar: guar
            };
            pushSolution(out, sol);
          }
        }
      }

      var uniq = dedupe(out);
      uniq.sort(opt.sortMode === 'error' ? Score.byError : Score.byWeight);
      return uniq.slice(0, opt.limit || 2000);
    }

    return { solve: solve, pool: pool, alphaChain: alphaChain,
             SPEED: SPEED, V1: V1, staffOf: staffOf };
  })();

  // ---------------------------------------------------------------- 黑闪页
  var BlackFlash = (function () {
    var SPEED = [
      { id: 'HEAVY_SHOT', v: 0.3, name: '沉重一击' },
      { id: 'ACCELERATING_SHOT', v: 0.32, name: '逐渐加速', grad: true },
      { id: 'EXPLOSIVE_PROJECTILE', v: 0.75, name: '易爆的投射物' },
      { id: 'SPEED', v: 2.5, name: '加速' },
      { id: 'LIGHT_SHOT', v: 7.5, name: '轻盈一击' }
    ];
    var TIME = [
      { id: 'LIFETIME', delta: 75, name: '延长存在时间' },
      { id: 'ZERO_DAMAGE', delta: 280, name: '无害化' },
      { id: 'LIFETIME_DOWN', delta: -42, name: '缩减存在时间' }
    ];
    var CARRIERS = {
      bh: { key: 'bh', id: 'BLACK_HOLE', name: '黑洞', v0: 2 / 3, xi: -0.2,
            baseT: 120, tvar: 7, vmax: 1000 / 60 },
      lt: { key: 'lt', id: 'LIGHTNING', name: '闪电弹', v0: 90, xi: 0.55,
            baseT: 1, tvar: 0, vmax: 1024 }
    };

    function clampStep(x, f) {
      var v = x * f;
      if (v < 0) return 0;
      if (v > 20) return 20;
      return v;
    }

    function alphaChain(staff, slime, cnt) {
      var x = 1;
      if (staff && staff !== 1) x = clampStep(x, staff);
      if (slime) x = clampStep(x, 1.1);
      for (var i = 0; i < SPEED.length; i++) {
        for (var r = 0; r < (cnt[i] || 0); r++) x = clampStep(x, SPEED[i].v);
      }
      return x;
    }

    /** v0.7 bfDist 的闭式距离（含 q>1 满速分段） */
    function dist(car, v0eff, nGrad, T) {
      if (T <= 0) return 0;
      var q0 = 1 - car.xi / 60;
      var v1 = Math.min(v0eff * q0, car.vmax);
      if (T === 1) return v1;
      var q = 1 - (car.xi - 3 * nGrad) / 60;
      if (q === 1) return v1 * T;
      if (q < 1) return v1 + v1 * q * (1 - Math.pow(q, T - 1)) / (1 - q);
      if (v1 >= car.vmax) return v1 + (T - 1) * car.vmax;
      var A = Math.ceil(Math.log(car.vmax / v1) / Math.log(q));
      if (A <= 1) return v1 + (T - 1) * car.vmax;
      if (T >= A + 1) {
        return v1 + v1 * q * (1 - Math.pow(q, A - 1)) / (1 - q) + (T - A) * car.vmax;
      }
      return v1 + v1 * q * (1 - Math.pow(q, T - 1)) / (1 - q);
    }

    /** 枚举单个载体的修正组合 */
    function enumCarrier(car, opt) {
      var plans = [];
      var cnt = new Array(SPEED.length + TIME.length).fill(0);
      var maxSpeed = opt.maxSpeedMods != null ? opt.maxSpeedMods : 5;
      var maxTotal = opt.maxCorrections != null ? opt.maxCorrections : 8;
      var staffs = opt.staffs || [1, 1.25, 1.5];
      var slimes = [false, true];

      (function walk(idx, left, usedSpeed) {
        if (idx === SPEED.length + TIME.length) {
          staffs.forEach(function (st) {
            slimes.forEach(function (sl) {
              var harmIdx = SPEED.length + 1;
              var T = car.baseT + 75 * cnt[SPEED.length] +
                      (car.key === 'lt' ? 281 : 280) * cnt[harmIdx] - 42 * cnt[SPEED.length + 2];
              if (T < 1) return;
              // 闪电弹飞行时间过长会因重力严重下垂 → 只保留时间修正 ≤ +75f（最多一个蓝表）
              if (car.key === 'lt' && opt.limitLtSag !== false &&
                  (T - car.baseT) > CFG.LT_MAX_TIME_UP) return;
              var alpha = alphaChain(st, sl, cnt);
              var v0eff = car.v0 * alpha;
              var nGrad = cnt[1];
              var d = dist(car, v0eff, nGrad, T);
              var corr = cnt.reduce(function (s, c) { return s + c; }, 0);
              var p = { carrier: car, cnt: cnt.slice(), staff: st, slime: sl,
                        T: T, alpha: alpha, v0eff: v0eff, d: d, corr: corr,
                        nGrad: nGrad, tvar: car.tvar };
              if (car.tvar > 0) {
                p.dLo = dist(car, v0eff, nGrad, T - car.tvar);
                p.dHi = dist(car, v0eff, nGrad, T + car.tvar);
              }
              plans.push(p);
            });
          });
          return;
        }
        var isSpeed = idx < SPEED.length;
        for (var c = 0; c <= left; c++) {
          if (isSpeed && usedSpeed + c > maxSpeed) break;
          cnt[idx] = c;
          walk(idx + 1, left - c, usedSpeed + (isSpeed ? c : 0));
        }
        cnt[idx] = 0;
      })(0, maxTotal, 0);
      plans.sort(function (a, b) { return a.d - b.d; });
      return plans;
    }

    /**
     * 黑闪页求解：黑洞 + 闪电弹 双载体，距离之和逼近目标
     *   两者都必须搭配「追加失效触发」才能作为载体 / 释放载荷。
     */
    function solve(opt) {
      opt = opt || {};
      var D = opt.distance;
      var tol = opt.tolerance || 0;
      var owned = opt.owned || {};
      var guar = opt.guaranteed || {};
      var payload = opt.payload || [];
      var bhMin = opt.bhMinDist != null ? opt.bhMinDist : CFG.BH_MIN_DIST;
      var out = [];

      var bh = enumCarrier(CARRIERS.bh, opt);
      var lt = enumCarrier(CARRIERS.lt, opt);
      var ltD = lt.map(function (p) { return p.d; });

      var cap = opt.limit || 3000;
      for (var i = 0; i < bh.length; i++) {
        var a = bh[i];
        if (bhMin && a.d < bhMin) continue;          // 黑洞必须飞出加载区
        var need = D - a.d;
        if (need < 0) break;
        var lo = lowerBound(ltD, need - tol);
        for (var j = lo; j < lt.length && ltD[j] <= need + tol; j++) {
          var b = lt[j];
          var total = a.d + b.d;
          var err = Math.abs(total - D);
          if (err > tol) continue;

          // ---- 黑洞部分
          var bhItems = {};
          Zone.add(bhItems, CARRIERS.bh.id, 1);
          Zone.add(bhItems, CFG.CARRIER_TRIGGER, 1);
          SPEED.forEach(function (f, k) { if (a.cnt[k]) Zone.add(bhItems, f.id, a.cnt[k]); });
          TIME.forEach(function (f, k) { if (a.cnt[SPEED.length + k]) Zone.add(bhItems, f.id, a.cnt[SPEED.length + k]); });
          if (a.slime) Zone.add(bhItems, 'SLIMEBALL', 1);

          // ---- 闪电弹部分
          var ltItems = {};
          Zone.add(ltItems, CARRIERS.lt.id, 1);
          Zone.add(ltItems, CFG.CARRIER_TRIGGER, 1);
          SPEED.forEach(function (f, k) { if (b.cnt[k]) Zone.add(ltItems, f.id, b.cnt[k]); });
          TIME.forEach(function (f, k) { if (b.cnt[SPEED.length + k]) Zone.add(ltItems, f.id, b.cnt[SPEED.length + k]); });
          if (b.slime) Zone.add(ltItems, 'SLIMEBALL', 1);

          var zones = [
            Zone.make('bh', '必需 · 黑洞修正', bhItems,
              { note: '黑洞先把载荷送出加载区（≥ ' + CFG.BH_MIN_DIST + ' px）' }),
            Zone.make('lt', '必需 · 闪电弹修正', ltItems,
              { note: '闪电弹接力飞完剩下的距离并释放载荷' })
          ];

          // ---- 载荷（必需：用户可选类型，但选哪种都必需）
          if (payload.length) {
            var pItems = {};
            payload.forEach(function (id) { Zone.add(pItems, id, 1); });
            zones.push(Zone.make('payload', '载荷', pItems));
          }

          // 黑洞存在时间随机（±tvar 帧）导致的距离区间
          var rLo = total, rHi = total;
          if (a.dLo != null) { rLo = a.dLo + b.d; rHi = a.dHi + b.d; }
          var sol = {
            page: 'blackflash', bh: a, lt: b, dist: total, error: err,
            rangeLo: rLo, rangeHi: rHi,
            staffMult: a.staff, staff: Tentacle.staffOf(a.staff),
            zones: zones, opt: opt, owned: owned, guar: guar
          };
          pushSolution(out, sol);
          if (out.length >= cap * 4) break;
        }
      }

      var uniq = dedupe(out, function (s) {
        return s.bh.cnt.join(',') + '|' + s.bh.staff + s.bh.slime + '|' +
               s.lt.cnt.join(',') + '|' + s.lt.staff + s.lt.slime;
      });
      uniq.sort(opt.sortMode === 'error' ? Score.byError : Score.byWeight);
      return uniq.slice(0, cap);
    }

    return { solve: solve, dist: dist, alphaChain: alphaChain,
             enumCarrier: enumCarrier, SPEED: SPEED, TIME: TIME, CARRIERS: CARRIERS };
  })();

  // ---------------------------------------------------------------- 结果格式化
  var Format = (function () {
    function isDn(id) { return /^DIVIDE_\d+$/.test(id); }

    /** 分区 → 带缺口信息的条目 */
    function blocks(sol, owned, guar) {
      owned = owned || {}; guar = guar || {};
      return (sol.zones || []).map(function (z) {
        var items = Object.keys(z.items).map(function (id) {
          var n = z.items[id];
          var o = guar[id] ? n : (owned[id] || 0);
          var lack = Math.max(0, n - o);
          return {
            id: id, need: n, owned: o, lack: lack, noName: true,
            optional: !!z.optional || !!CFG.OPTIONAL_IDS[id],
            label: lack > 0 ? ('缺 ' + lack + '（有 ' + o + ' / 需 ' + n + '）')
                            : ('有 ' + o + ' / ' + n)
          };
        });
        // 只把 Dn 提到最前，其余保持求解器给的顺序（载体 → 触发 → 限制器 → 修正）
        items.sort(function (a, b) {
          if (isDn(a.id) !== isDn(b.id)) return isDn(a.id) ? -1 : 1;
          return 0;
        });
        return { key: z.key, label: z.label, items: items,
                 note: z.note, hint: z.hint, optional: z.optional,
                 staff: z.staff };
      });
    }

    return { blocks: blocks, isDn: isDn };
  })();

  // ---------------------------------------------------------------- 工具
  function lowerBound(arr, x) {
    var lo = 0, hi = arr.length;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (arr[mid] < x) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  /** 单个法术的所需数量是否超过上限 */
  function overMaxPerSpell(need, maxPerSpell) {
    if (!maxPerSpell) return false;
    for (var k in need) {
      if (Object.prototype.hasOwnProperty.call(need, k) && need[k] > maxPerSpell) return true;
    }
    return false;
  }


  /* ==========================================================================
   * Plan —— 搜索策略建议（口径 v7.2，docs/权重口径评估.md §12）
   *
   * 单位：1 = 直线穿过 1 个 chunk（512 px）空隙地形的时间。
   * 每个「session」= 把一处地点走一遍：
   *   圣山一轮  = 6 座（层 0/1/2/2/3/4，每座 50.5% 法术店 / 49.5% 法杖店）+ 1 眼睛房间
   *   繁茂一轮  = 只搜上块 42 chunk
   *   地狱一轮  = 86 chunk（2 chunk 宽 × 43 高）
   *
   * ⚠️ 主世界 7 座圣山已搜完 → 第一次进圣山/繁茂就要跨一次平行世界（113.2）。
   *    一趟平行世界同时补满圣山与繁茂，所以「开世界次数」按两者轮数的较大者算（Score.zoneTimes）。
   *
   * 四种策略：
   *   greedy      —— **按法术分配**：每个缺失法术派到「每单位时间出得最多」的刷点，
   *                  同一刷点内用 3-范数聚合轮数。这是可行方案里的最优解（与 S 值同一套算式）。
   *   holy_first  —— 硬性优先：圣山能出的一律先在圣山刷，剩下的才轮到繁茂、地狱。
   *   fungi_first —— 硬性优先：2/3/4 级先交给繁茂，剩下的给圣山、地狱。
   *   hell_first  —— 硬性优先：10 级先交给地狱，剩下的给圣山、繁茂。
   * 三种固定顺序都只在「该区域根本出不了这个法术」时才往下传，所以通常劣于 greedy——
   * 它们的用处是当对照基线，说明「为什么值得按法术分开刷」。
   * ========================================================================== */
  var Plan = (function () {
    var ZONES = ['holy', 'fungi', 'hell'];
    var ZONE_CN = { holy: '圣山', fungi: '繁茂', hell: '地狱' };
    var ZONE_EN = { holy: 'holy', fungi: 'fungi', hell: 'hell' };

    // 单轮耗时直接从 CFG.ZONES 取（随玩家模式变化）
    function sess(z) {
      var found = null;
      CFG.ZONES.forEach(function (x) { if (x.key === z) found = x; });
      return found;
    }

    // 每轮抽取数
    var HOLY_SPELL_LEVELS = [0, 1, 2, 2, 3, 4];   // 法术店 max_level
    var HOLY_WAND_LEVELS  = [0, 0, 1, 1, 2, 3];   // 法杖店 max_level
    var P_SPELL_SHOP = 51 / 101;
    var HOLY_CARDS = 10;                          // 法术店 5 摊 × 2 排
    var HOLY_WAND_CARDS = 5 * 4.5;                // 法杖店 5 根 × 4.5 张
    var EYE_CARDS = 8, EYE_POOL = 465;
    var FUNGI_DRAWS = 324;                        // 42 chunk × 7.71 张/chunk
    var HELL_DRAWS = 62;                          // 86 chunk × 0.73 张/chunk

    // 等级 × 类型的权重和（来自 gun_actions.lua，见 data/parsed/actions_full.json）
    var TIER_W_ALL = { 0: 44.6, 1: 84.0, 2: 138.8, 3: 131.9, 4: 145.0, 5: 127.9, 6: 84.9, 7: 0.7, 10: 61.2 };
    var TIER_W_TYPE = {
      0: { 0: 27.4, 1: 40.7, 2: 66.0, 3: 55.8, 4: 59.8, 5: 48.5, 6: 33.8, 10: 6.9 },
      1: { 0: 5.6, 1: 9.3, 2: 13.9, 3: 12.2, 4: 12.8, 5: 14.0, 6: 10.1, 10: 7.3 },
      2: { 0: 3.1, 1: 20.4, 2: 40.7, 3: 46.9, 4: 53.6, 5: 42.7, 6: 24.4, 10: 6.8 },
      3: { 0: 3.0, 1: 5.3, 2: 6.3, 3: 5.4, 4: 4.2, 5: 3.8, 6: 3.5, 10: 1.0 }
    };
    // 51 个法术的类型索引（0 投射物 / 1 静态 / 2 修正 / 3 多重施法 / 4 材料 / 5 其他 / 6 功能 / 7 被动）
    var TYPE_OF = {
      LIGHT_SHOT: 2, SPEED: 2, ACCELERATING_SHOT: 2, DECELERATING_SHOT: 2, EXPLOSIVE_PROJECTILE: 2, HEAVY_SHOT: 2,
      FIZZLE: 2, PHASING_ARC: 2, SINEWAVE: 2, CHAOTIC_ARC: 2, LIFETIME: 2, LIFETIME_DOWN: 2,
      ZERO_DAMAGE: 2, FLY_UPWARDS: 2, FLY_DOWNWARDS: 2, TENTACLE_TIMER: 0, BLACK_HOLE: 0, BLACK_HOLE_DEATH_TRIGGER: 0,
      LIGHTNING: 0, SLOW_BULLET_TIMER: 0, LARPA_CHAOS: 2, LARPA_CHAOS_2: 2, ENERGY_SHIELD_SHOT: 2, TELEPORT_PROJECTILE_CLOSER: 0,
      CASTER_CAST: 6, SWAPPER_PROJECTILE: 0, EXPLODING_DEER: 0, DAMAGE: 2, LINE_ARC: 2, NOLLA: 2,
      RESET: 6, ADD_TRIGGER: 5, ADD_TIMER: 5, ADD_DEATH_TRIGGER: 5, DELAYED_SPELL: 1, IF_HP: 5,
      TAU: 5, DIVIDE_2: 5, DIVIDE_3: 5, DIVIDE_4: 5, DIVIDE_10: 5, SLIMEBALL: 0,
      GAMMA: 5, MEGALASER: 0, QUANTUM_SPLIT: 2, X_RAY: 6, IF_HALF: 5, IF_END: 5,
      TRUE_ORBIT: 2, ORBIT_LARPA: 2, HORIZONTAL_ARC: 2
    };

    /** 商店渠道：精确等级 m 的单次命中率（Wiki pct 就是等级内条件概率） */
    function pShop(id, m) { return Weights.tierProb(id, m); }

    /** 法杖渠道：先按类型过滤，再按等级权重 */
    function pWand(id, m) {
      var ty = TYPE_OF[id];
      if (ty === undefined || ty > 3) return 0;
      var den = TIER_W_TYPE[ty] && TIER_W_TYPE[ty][m];
      if (!den) return 0;
      return pShop(id, m) * TIER_W_ALL[m] / den;
    }

    var cache = {};
    /** 每个 session 的期望获得份数 */
    function yields(id) {
      if (cache[id]) return cache[id];
      var holy = 0;
      for (var i = 0; i < 6; i++) {
        holy += P_SPELL_SHOP * HOLY_CARDS * pShop(id, HOLY_SPELL_LEVELS[i]);
        holy += (1 - P_SPELL_SHOP) * HOLY_WAND_CARDS * pWand(id, HOLY_WAND_LEVELS[i]);
      }
      holy += EYE_CARDS / EYE_POOL;
      var fungi = FUNGI_DRAWS * (pWand(id, 2) + pWand(id, 3) + pWand(id, 4)) / 3;
      var hell = HELL_DRAWS * pShop(id, 10);
      return (cache[id] = { holy: holy, fungi: fungi, hell: hell });
    }

    /**
     * 固定优先顺序：每个法术交给「顺序里第一个能出它」的刷点。
     * 这是玩家「这次只去 X」的极端版本，用来当对照基线。
     */
    function planByOrder(items, order) {
      var n = items.length;
      var rem = items.map(function (x) { return x.lack; });
      var acc = { holy: 0, fungi: 0, hell: 0 };
      order.forEach(function (z) {
        for (var i = 0; i < n; i++) {
          if (rem[i] <= 0) continue;
          var y = yields(items[i].id)[z];
          if (y > 0) { acc[z] += Math.pow(rem[i] / y, 3); rem[i] = 0; }
        }
      });
      var ks = CFG.ZONES.map(function (z) { return Math.cbrt(acc[z.key]); });
      var done = rem.every(function (r) { return r <= 0; });
      return { total: Score.zoneTimes(ks).total, done: done, ks: ks };
    }

    var ORDERS = {
      holy_first:  ['holy', 'fungi', 'hell'],
      fungi_first: ['fungi', 'holy', 'hell'],
      hell_first:  ['hell', 'holy', 'fungi']
    };

    /**
     * 给一组缺口，返回最佳策略。
     * label 形如 `hell_first` 或 `greedy:fungi`
     *   —— greedy 时冒号后是**耗时占比最大的刷点**（不是第一步），它才回答「这个配方主要耗在哪」。
     */
    function best(items) {
      if (!items || !items.length) return null;
      var cand = [];
      Object.keys(ORDERS).forEach(function (k) {
        var r = planByOrder(items, ORDERS[k]);
        cand.push({ key: k, label: k, total: r.total, done: r.done });
      });

      // greedy = 按法术分配（与 S 值同一套算式：3-范数 + 共享换世界成本）
      var g = Score.assignZones(items);
      var dom = null, domT = -1, first = null;
      CFG.ZONES.forEach(function (z, gi) {
        if (g.stages[gi] > domT) { domT = g.stages[gi]; dom = z.key; }
        if (first === null && g.rounds[gi] > 1e-9) first = z.key;
      });
      cand.push({ key: 'greedy', label: 'greedy' + (dom ? ':' + ZONE_EN[dom] : ''),
                  total: g.total, done: true, zone: dom, first: first,
                  stages: g.stages, rounds: g.rounds, hops: g.hops });

      // 平手时优先 greedy（它带区域明细，信息更多；固定顺序在这种退化为同一分配时会打平）
      cand.sort(function (a, b) {
        var d = a.total - b.total;
        if (Math.abs(d) > 1e-9) return d;
        if (a.key === 'greedy') return -1;
        if (b.key === 'greedy') return 1;
        return 0;
      });
      var top = cand[0];
      top.all = cand;
      top.zoneCN = top.zone ? ZONE_CN[top.zone] : null;
      top.firstCN = top.first ? ZONE_CN[top.first] : null;
      // 区域明细（弹窗用）：按耗时降序
      if (top.stages) {
        top.zoneDetail = CFG.ZONES.map(function (z, gi) {
          return { key: z.key, label: z.label, time: top.stages[gi], rounds: top.rounds[gi] };
        }).filter(function (x) { return x.time > 1e-9; })
          .sort(function (a, b) { return b.time - a.time; });
      }
      return top;
    }

    return { best: best, yields: yields, sess: sess, ZONE_CN: ZONE_CN };
  })();

  function dedupe(list, keyFn) {
    var seen = new Set(), out = [];
    list.forEach(function (s) {
      var key = keyFn ? keyFn(s) : JSON.stringify(s.need) + '|' + s.error;
      if (seen.has(key)) return;
      seen.add(key); out.push(s);
    });
    return out;
  }

  return { CFG: CFG, DN: DN, Weights: Weights, Phase: Phase, Score: Score, Plan: Plan,
           Zone: Zone, Chain: Chain, Solve: Solve, Tentacle: Tentacle,
           BlackFlash: BlackFlash, Format: Format };
});
