#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
静态站点生成器

从 data/ 下的真实数据生成 docs/index.html，把菜单、营养、券规则与求解算法
一并内嵌进单页，使页面无需后端、无需构建即可运行。

设计考虑
--------
页面里的 JS 复刻了 Python 侧的定价与帕累托逻辑。两份实现难免漂移，
因此配套 scripts/parity_check.mjs 做前后端对拍：对同一组输入分别调用
Python 与 JS，比对输出的方案集合是否一致。

用法：
    python tools/build_site.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcd_planner.optimizer import build_joint_catalog  # noqa: E402
from mcd_planner.pricing import load_coupons, load_menu  # noqa: E402


def build_payload():
    """装配页面所需的数据包。"""
    catalog = build_joint_catalog()
    coupons = load_coupons()
    menu = load_menu()

    items = [{
        "c": it.code,
        "n": it.name,
        "p": it.price,
        "o": it.original_price,
        "cat": it.category,
        "k": it.kcal,
        "s": it.sodium_mg,
        "pr": it.protein_g,
        "f": it.fat_g,
        "cb": it.carb_g,
        "ca": it.calcium_mg,
    } for it in catalog]

    cps = []
    for cp in coupons:
        cps.append({
            "id": cp.coupon_id,
            "t": cp.title,
            "kind": cp.kind,
            "codes": sorted(cp.product_codes),
            "price": cp.coupon_price,
            "from": cp.valid_from.strftime("%Y-%m-%d %H:%M") if cp.valid_from else None,
            "to": cp.valid_to.strftime("%Y-%m-%d %H:%M") if cp.valid_to else None,
            "wd": sorted(cp.weekdays) if cp.weekdays else None,
            "tw": ([cp.time_window[0].strftime("%H:%M"),
                    cp.time_window[1].strftime("%H:%M")]
                   if cp.time_window else None),
            "scopes": sorted(cp.scopes),
        })

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items": items,
        "coupons": cps,
        "stats": {
            "menu_all": len(menu),
            "nutrition_all": 158,
            "joint": len(items),
        },
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>麦麦省钱营养师 · 在线试算</title>
<meta name="description" content="基于麦当劳 MCP 的预算与钠含量双约束套餐优选。拖动滑块，实时算出实付最省且钠含量可控的组合。">
<style>
:root{
  --bg:#fafaf8; --card:#fff; --line:#e6e4df; --ink:#1f1f1d;
  --muted:#6b6a65; --hint:#96948d;
  --blue:#2f5496; --blue-bg:#eef3fb;
  --red:#c0392b; --red-bg:#fdeeec;
  --green:#2e7d4f; --green-bg:#eaf5ee;
  --amber:#a86a00; --amber-bg:#fdf4e3;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
    "Hiragino Sans GB","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.65;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:980px;margin:0 auto;padding:0 20px}

header{padding:52px 0 36px;border-bottom:1px solid var(--line)}
.eyebrow{font-size:13px;color:var(--hint);letter-spacing:.06em;margin-bottom:12px}
h1{font-size:32px;font-weight:600;letter-spacing:-.01em;line-height:1.3}
h1 em{font-style:normal;color:var(--blue)}
.sub{margin-top:14px;font-size:15px;color:var(--muted);max-width:640px}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:12px;margin:28px 0 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:14px 16px}
.stat .k{font-size:12px;color:var(--hint);margin-bottom:4px}
.stat .v{font-size:22px;font-weight:600;letter-spacing:-.02em}
.stat .v small{font-size:12px;font-weight:400;color:var(--hint);margin-left:3px}

section{padding:44px 0}
h2{font-size:19px;font-weight:600;margin-bottom:6px}
.lead{font-size:14px;color:var(--muted);margin-bottom:22px}

.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:22px}
.ctrl{margin-bottom:22px}
.ctrl:last-child{margin-bottom:0}
.ctrl-hd{display:flex;justify-content:space-between;align-items:baseline;
  margin-bottom:10px}
.ctrl-hd label{font-size:14px;font-weight:500}
.ctrl-hd .val{font-size:14px;font-weight:600;color:var(--blue);
  font-variant-numeric:tabular-nums}
input[type=range]{width:100%;height:4px;-webkit-appearance:none;appearance:none;
  background:var(--line);border-radius:2px;outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:18px;
  height:18px;border-radius:50%;background:var(--blue);cursor:pointer;
  border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.18)}
input[type=range]::-moz-range-thumb{width:18px;height:18px;border-radius:50%;
  background:var(--blue);cursor:pointer;border:2px solid #fff}
.seg{display:flex;gap:8px;flex-wrap:wrap}
.seg button{flex:1;min-width:90px;padding:9px 12px;font-size:13px;
  background:var(--card);border:1px solid var(--line);border-radius:8px;
  cursor:pointer;color:var(--muted);font-family:inherit;transition:.15s}
.seg button:hover{border-color:#c9c7c0}
.seg button.on{background:var(--blue);border-color:var(--blue);color:#fff;
  font-weight:500}

.hero{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:24px;margin-bottom:16px}
.hero .tag{display:inline-block;font-size:12px;padding:3px 9px;border-radius:5px;
  background:var(--green-bg);color:var(--green);margin-bottom:12px;font-weight:500}
.hero .combo{font-size:19px;font-weight:600;line-height:1.45;margin-bottom:14px}
.hero .money{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
  margin-bottom:14px}
.hero .now{font-size:34px;font-weight:600;color:var(--blue);
  font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.hero .was{font-size:15px;color:var(--hint);text-decoration:line-through}
.hero .save{font-size:14px;color:var(--red);font-weight:500}
.hero .meta{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;
  color:var(--muted);padding-top:14px;border-top:1px solid var(--line)}
.hero .meta b{color:var(--ink);font-weight:600}
.hero .coupon{font-size:13px;color:var(--amber);background:var(--amber-bg);
  padding:8px 12px;border-radius:8px;margin-top:12px}

table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-weight:500;color:var(--hint);font-size:12px;
  padding:0 10px 8px;border-bottom:1px solid var(--line)}
td{padding:10px;border-bottom:1px solid #f2f0eb;
  font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
td.name{font-variant-numeric:normal;font-weight:500}
td.price{color:var(--blue);font-weight:600}
.badge{display:inline-block;font-size:11px;padding:2px 7px;border-radius:4px;
  background:var(--green-bg);color:var(--green);margin-left:6px}
.badge.warn{background:var(--amber-bg);color:var(--amber)}

.alt-list{display:flex;flex-direction:column;gap:10px}
.alt{display:flex;justify-content:space-between;align-items:center;gap:14px;
  padding:12px 14px;background:var(--card);border:1px solid var(--line);
  border-radius:10px;font-size:13px}
.alt .l{font-weight:500}
.alt .r{color:var(--green);font-weight:500;white-space:nowrap}

#chart{width:100%;height:300px}
.empty{text-align:center;padding:40px 20px;color:var(--hint);font-size:14px}

footer{padding:36px 0 56px;border-top:1px solid var(--line);margin-top:20px}
footer p{font-size:12px;color:var(--hint);line-height:1.8}
footer a{color:var(--muted)}

@media(max-width:640px){
  h1{font-size:25px}
  .hero .now{font-size:28px}
  header{padding:36px 0 28px}
}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="eyebrow">麦当劳程序员节创意开发大赛 · 参赛作品</div>
  <h1>麦麦省钱<em>营养师</em></h1>
  <p class="sub">
    基于麦当劳 MCP。不做「券列表查询」，做<b>点餐决策</b>：
    在预算和钠摄入的双重约束下，算出实付最省、且吃得下去的组合。
  </p>
  <div class="stats">
    <div class="stat"><div class="k">门店在售餐品</div>
      <div class="v">__MENU_ALL__<small>项</small></div></div>
    <div class="stat"><div class="k">营养数据</div>
      <div class="v">__NUT_ALL__<small>项</small></div></div>
    <div class="stat"><div class="k">可参与双维求解</div>
      <div class="v">__JOINT__<small>项</small></div></div>
    <div class="stat"><div class="k">单元测试</div>
      <div class="v">49<small>项全通过</small></div></div>
  </div>
</header>

<section>
  <h2>在线试算</h2>
  <p class="lead">拖动滑块，实时求解。数据为门店真实标价与官方营养表。</p>

  <div class="panel">
    <div class="ctrl">
      <div class="ctrl-hd">
        <label>预算上限</label>
        <span class="val" id="budgetVal">不限</span>
      </div>
      <input type="range" id="budget" min="0" max="80" step="1" value="0">
    </div>

    <div class="ctrl">
      <div class="ctrl-hd">
        <label>钠摄入上限</label>
        <span class="val" id="sodiumVal">不限</span>
      </div>
      <input type="range" id="sodium" min="0" max="3000" step="50" value="0">
    </div>

    <div class="ctrl">
      <div class="ctrl-hd"><label>组合件数上限</label></div>
      <div class="seg" id="sizeSeg">
        <button data-v="1">1 件</button>
        <button data-v="2">2 件</button>
        <button data-v="3" class="on">3 件</button>
      </div>
    </div>
  </div>
</section>

<section style="padding-top:0">
  <h2>最优方案</h2>
  <p class="lead" id="bestLead"></p>
  <div id="best"></div>
</section>

<section style="padding-top:0">
  <h2>价格 × 钠 帕累托前沿</h2>
  <p class="lead">
    前沿上的每个点都「不可支配」——想再便宜就得接受更高钠，想再低钠就得多花钱。
    不在前沿上的方案，总能被某个更便宜或更健康的选项替代。
  </p>
  <div class="panel" style="padding:18px 14px">
    <svg id="chart" viewBox="0 0 900 300" preserveAspectRatio="xMidYMid meet"
         role="img" aria-label="价格与钠含量的帕累托前沿散点图"></svg>
  </div>
  <div style="margin-top:18px" class="panel">
    <table id="frontierTable">
      <thead><tr><th>方案</th><th>实付</th><th>钠</th><th>热量</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</section>

<section style="padding-top:0">
  <h2>如果你已经有想吃的</h2>
  <p class="lead">
    选一个你本来想点的，看看有没有「更便宜又更低钠」的同类替代。
    只在同类商品间比较——不会拿冰淇淋来替汉堡。
  </p>
  <div class="panel" style="margin-bottom:16px">
    <select id="targetSel" style="width:100%;padding:11px 12px;font-size:14px;
      border:1px solid var(--line);border-radius:8px;font-family:inherit;
      background:var(--card);color:var(--ink)"></select>
  </div>
  <div class="alt-list" id="alts"></div>
</section>

<footer>
  <p>
    <b>免责声明</b>：本项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，
    非麦当劳官方产品。输出仅供参考，不构成医疗、营养或其他专业建议；
    餐品信息、价格及供应状态以麦当劳官方渠道实时结果为准。<br>
    数据快照：__GENERATED_AT__ · 本页算法与仓库内 Python 实现通过前后端对拍校验。
  </p>
</footer>

</div>

<script>
const DATA = __PAYLOAD__;

const STAPLE = new Set(['burger','set']);

/* ---------- 券有效性 ---------- */
function parseDT(s){
  if(!s) return null;
  const [d,t] = s.split(' ');
  const [y,mo,da] = d.split('-').map(Number);
  const [hh,mm] = (t||'00:00').split(':').map(Number);
  return new Date(y, mo-1, da, hh, mm);
}
function couponValid(cp, now){
  const f = parseDT(cp.from), t = parseDT(cp.to);
  if(f && now < f) return false;
  if(t && now > t) return false;
  if(cp.wd && !cp.wd.includes((now.getDay()+6)%7)) return false;
  if(cp.tw){
    const cur = now.getHours()*60 + now.getMinutes();
    const [sh,sm] = cp.tw[0].split(':').map(Number);
    const [eh,em] = cp.tw[1].split(':').map(Number);
    if(cur < sh*60+sm || cur > eh*60+em) return false;
  }
  return true;
}
function couponFor(item, now){
  let best = null;
  for(const cp of DATA.coupons){
    if(cp.kind !== 'special') continue;
    if(!cp.codes.includes(item.c)) continue;
    if(cp.price == null || cp.price > item.p) continue;
    if(!couponValid(cp, now)) continue;
    if(!cp.scopes.includes('dine_in')) continue;
    if(best === null || cp.price < best.price) best = cp;
  }
  return best;
}

/* ---------- 计价 ---------- */
/* 一单一张券：与 Python 侧 STACK_SINGLE 默认策略保持一致 */
function quoteOf(items, now){
  let listTotal = 0;
  for(const it of items) listTotal += it.o > 0 ? it.o : it.p;

  let bestCp = null, bestSave = 0, bestCode = null;
  for(const it of items){
    const cp = couponFor(it, now);
    if(!cp) continue;
    const save = it.p - cp.price;
    if(save > bestSave + 1e-9){ bestSave = save; bestCp = cp; bestCode = it.c; }
  }

  let paid = 0;
  const used = [];
  for(const it of items){
    if(bestCp && it.c === bestCode){ paid += bestCp.price; used.push(bestCp.t); }
    else paid += it.p;
  }
  return {listTotal, paid: Math.round(paid*100)/100, used};
}

/* ---------- 枚举 ---------- */
function enumerate(maxSize, maxSodium){
  const pool = DATA.items.filter(it =>
    maxSodium ? it.s <= maxSodium : true);
  const out = [];
  const n = pool.length;
  function walk(start, chosen){
    if(chosen.length >= 1){
      const cats = new Set(chosen.map(x=>x.cat));
      let staple = false;
      for(const c of cats) if(STAPLE.has(c)) staple = true;
      if(staple){
        let s=0,k=0,pr=0,f=0,cb=0,ca=0;
        for(const x of chosen){s+=x.s;k+=x.k;pr+=x.pr;f+=x.f;cb+=x.cb;ca+=x.ca;}
        if(!maxSodium || s<=maxSodium){
          out.push({items:chosen.slice(), s, k, pr, f, cb, ca});
        }
      }
    }
    if(chosen.length >= maxSize) return;
    for(let i=start;i<n;i++){
      chosen.push(pool[i]);
      walk(i+1, chosen);
      chosen.pop();
    }
  }
  walk(0, []);
  return out;
}

/* ---------- 求解 ---------- */
function solve(budget, maxSodium, maxSize, nowOverride){
  const now = nowOverride || new Date();
  const raw = enumerate(maxSize, maxSodium);
  const plans = [];
  for(const r of raw){
    const q = quoteOf(r.items, now);
    if(budget && q.paid > budget) continue;
    plans.push({...r, price:q.paid, list:q.listTotal, used:q.used});
  }
  plans.sort((a,b)=> a.price-b.price || a.s-b.s);

  const front = [];
  let bestS = Infinity;
  for(const p of plans){
    if(p.s < bestS - 1e-9){ front.push(p); bestS = p.s; }
  }
  return {plans, front};
}

/* 对外暴露纯函数，供前后端对拍脚本调用 */
globalThis.MCD = { solve, enumerate, quoteOf, couponFor, couponValid, DATA };

/* ---------- 渲染 ---------- */
const fmt = n => '¥' + n.toFixed(2);
const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function renderBest(res){
  const box = document.getElementById('best');
  const lead = document.getElementById('bestLead');
  if(!res.front.length){
    lead.textContent = '';
    box.innerHTML = '<div class="panel empty">当前约束下无可行解，试着放宽预算或钠上限。</div>';
    return;
  }
  const p = res.front[0];
  const lowest = res.front.reduce((a,b)=> a.s<b.s?a:b);
  lead.textContent = res.plans.length + ' 个可行组合，其中 ' +
    res.front.length + ' 个位于帕累托前沿。';

  const names = p.items.map(x=>esc(x.n)).join(' + ');
  const save = p.list - p.price;
  const couponLine = p.used.length
    ? '<div class="coupon">已用券：' + esc([...new Set(p.used)].join('、')) + '</div>'
    : '';

  let tradeoff = '';
  if(lowest !== p && lowest.s < p.s){
    const dp = lowest.price - p.price;
    const ds = p.s - lowest.s;
    tradeoff = '<div class="meta" style="border-top:none;padding-top:0;margin-top:-4px">' +
      '<span>同预算下最低钠方案：<b>' + esc(lowest.items.map(x=>x.n).join(' + ')) +
      '</b>（' + lowest.s.toFixed(0) + 'mg，' + fmt(lowest.price) + '）' +
      '，多花 ' + fmt(dp) + ' 可减钠 ' + ds.toFixed(0) + 'mg</span></div>';
  }

  box.innerHTML = '<div class="hero">' +
    '<div class="tag">实付最省</div>' +
    '<div class="combo">' + names + '</div>' +
    '<div class="money"><span class="now">' + fmt(p.price) + '</span>' +
      (save > 0.005 ? '<span class="was">' + fmt(p.list) + '</span>' +
        '<span class="save">省 ' + fmt(save) + '</span>' : '') +
    '</div>' +
    '<div class="meta">' +
      '<span>钠 <b>' + p.s.toFixed(0) + 'mg</b></span>' +
      '<span>热量 <b>' + p.k.toFixed(0) + 'kcal</b></span>' +
      '<span>蛋白 <b>' + p.pr.toFixed(0) + 'g</b></span>' +
    '</div>' + couponLine + tradeoff + '</div>';
}

function renderTable(front){
  const tb = document.querySelector('#frontierTable tbody');
  tb.innerHTML = front.map(p =>
    '<tr><td class="name">' + esc(p.items.map(x=>x.n).join(' + ')) + '</td>' +
    '<td class="price">' + fmt(p.price) + '</td>' +
    '<td>' + p.s.toFixed(0) + 'mg</td>' +
    '<td>' + p.k.toFixed(0) + '</td></tr>'
  ).join('') || '<tr><td colspan="4" class="empty">无</td></tr>';
}

function renderChart(front, all){
  const svg = document.getElementById('chart');
  const W=900,H=300, pad={l:54,r:16,t:16,b:38};
  const iw=W-pad.l-pad.r, ih=H-pad.t-pad.b;

  const pts = all.length ? all : front;
  if(!pts.length){ svg.innerHTML=''; return; }

  const maxP = Math.max(...pts.map(p=>p.price)) * 1.05 || 1;
  const maxS = Math.max(...pts.map(p=>p.s)) * 1.05 || 1;
  const X = v => pad.l + (v/maxP)*iw;
  const Y = v => pad.t + ih - (v/maxS)*ih;

  let g = '';
  for(let i=0;i<=4;i++){
    const y = pad.t + ih*i/4;
    g += '<line x1="'+pad.l+'" y1="'+y+'" x2="'+(W-pad.r)+'" y2="'+y+
         '" stroke="#eeece7" stroke-width="1"/>';
    const val = maxS*(1-i/4);
    g += '<text x="'+(pad.l-10)+'" y="'+(y+4)+'" text-anchor="end" ' +
         'font-size="11" fill="#96948d">'+val.toFixed(0)+'</text>';
  }
  for(let i=0;i<=4;i++){
    const x = pad.l + iw*i/4;
    const val = maxP*i/4;
    g += '<line x1="'+x+'" y1="'+pad.t+'" x2="'+x+'" y2="'+(pad.t+ih)+
         '" stroke="#f6f4ef" stroke-width="1"/>';
    g += '<text x="'+x+'" y="'+(H-pad.b+18)+'" text-anchor="middle" ' +
         'font-size="11" fill="#96948d">¥'+val.toFixed(0)+'</text>';
  }
  g += '<text x="'+(W/2)+'" y="'+(H-4)+'" text-anchor="middle" ' +
       'font-size="11" fill="#6b6a65">实付金额</text>';
  g += '<text transform="translate(14,'+(pad.t+ih/2)+') rotate(-90)" ' +
       'text-anchor="middle" font-size="11" fill="#6b6a65">钠 (mg)</text>';

  const frontSet = new Set(front.map(p=>p.items.map(x=>x.c).sort().join('|')));

  /* 背景点采样：方案数可能上千，全画会让 SVG 膨胀到数百 KB、
     拖动滑块时明显卡顿。按步长抽样，最多约 220 个点，
     既保留分布形状，又控制渲染开销。前沿点始终全画。 */
  const bg = all.filter(p => {
    const key = p.items.map(x=>x.c).sort().join('|');
    return !frontSet.has(key);
  });
  const stride = Math.max(1, Math.ceil(bg.length / 220));
  for(let i=0;i<bg.length;i+=stride){
    const p = bg[i];
    g += '<circle cx="'+X(p.price)+'" cy="'+Y(p.s)+'" r="2.5" ' +
         'fill="#d8d5cd"/>';
  }
  if(front.length > 1){
    const d = front.map((p,i)=>(i?'L':'M')+X(p.price)+' '+Y(p.s)).join(' ');
    g += '<path d="'+d+'" fill="none" stroke="#2f5496" stroke-width="2" ' +
         'stroke-linejoin="round" opacity="0.35"/>';
  }
  for(const p of front){
    g += '<circle cx="'+X(p.price)+'" cy="'+Y(p.s)+'" r="5" ' +
         'fill="#2f5496" stroke="#fff" stroke-width="2"><title>' +
         esc(p.items.map(x=>x.n).join(' + ')) + ' · ' + fmt(p.price) +
         ' · ' + p.s.toFixed(0) + 'mg</title></circle>';
  }
  svg.innerHTML = g;
}

function renderAlts(){
  const sel = document.getElementById('targetSel');
  const box = document.getElementById('alts');
  const code = sel.value;
  const target = DATA.items.find(x=>x.c===code);
  if(!target){ box.innerHTML=''; return; }

  const isStaple = STAPLE.has(target.cat);
  const same = DATA.items.filter(x =>
    x.c !== code && (STAPLE.has(x.cat) === isStaple));

  const alts = same.filter(x =>
    x.p <= target.p && x.s <= target.s &&
    (x.p < target.p || x.s < target.s));

  // 同类组合替代
  if(isStaple){
    const fillers = DATA.items.filter(x => !STAPLE.has(x.cat) && x.p <= 12)
      .sort((a,b)=>a.p-b.p || a.s-b.s).slice(0,4);
    for(const st of same.slice(0,8)){
      for(const fl of fillers){
        const price = st.p + fl.p, sod = st.s + fl.s;
        if(price > target.p || sod > target.s) continue;
        alts.push({c:'__combo__', n: st.n+' + '+fl.n, p:price, s:sod, cat:'combo'});
      }
    }
  }

  alts.sort((a,b)=> a.p-b.p || a.s-b.s);
  const seen = new Set();
  const uniq = alts.filter(a=>{
    const k = a.n;
    if(seen.has(k)) return false;
    seen.add(k); return true;
  }).slice(0,6);

  if(!uniq.length){
    box.innerHTML = '<div class="panel empty">这个选择已经不错了' +
      '——同类里没有既能更便宜又能更低钠的替代。</div>';
    return;
  }

  box.innerHTML = uniq.map(a=>{
    const dp = target.p - a.p, ds = target.s - a.s;
    const bits = [];
    if(dp > 0.005) bits.push('便宜 ' + fmt(dp));
    if(ds > 0.5) bits.push('少钠 ' + ds.toFixed(0) + 'mg');
    return '<div class="alt"><span class="l">' + esc(a.n) + '</span>' +
      '<span class="r">' + bits.join('、') + '</span></div>';
  }).join('');
}

/* ---------- 交互绑定 ---------- */
let maxSize = 3;

function update(){
  const b = +document.getElementById('budget').value;
  const s = +document.getElementById('sodium').value;
  document.getElementById('budgetVal').textContent = b ? fmt(b) : '不限';
  document.getElementById('sodiumVal').textContent = s ? s + 'mg' : '不限';

  const res = solve(b, s, maxSize);
  renderBest(res);
  renderTable(res.front);
  renderChart(res.front, res.plans);
}

document.getElementById('budget').addEventListener('input', update);
document.getElementById('sodium').addEventListener('input', update);
document.querySelectorAll('#sizeSeg button').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('#sizeSeg button').forEach(b=>b.classList.remove('on'));
    btn.classList.add('on');
    maxSize = +btn.dataset.v;
    update();
  });
});

(function init(){
  const sel = document.getElementById('targetSel');
  const staples = DATA.items.filter(x=>STAPLE.has(x.cat))
    .sort((a,b)=> b.s - a.s);
  sel.innerHTML = staples.map(x =>
    '<option value="'+x.c+'">'+esc(x.n)+' · ¥'+x.p.toFixed(2)+
    ' · 钠 '+x.s.toFixed(0)+'mg</option>').join('');
  sel.addEventListener('change', renderAlts);

  document.getElementById('sodium').value = 1500;
  update();
  renderAlts();
})();
</script>
</body>
</html>
"""


def build_parity_expected():
    """
    用 Python 侧算法生成对拍基准。

    对同一组 (预算, 钠上限, 件数) 输入，Python 与页面 JS 应给出相同的
    帕累托前沿。若两者不一致，说明某一侧有 bug。
    """
    from mcd_planner.optimizer import optimize

    grid = [
        {"budget": 30, "sodium": 1500, "size": 2},
        {"budget": 30, "sodium": 0, "size": 3},
        {"budget": 40, "sodium": 800, "size": 2},
        {"budget": 50, "sodium": 2000, "size": 3},
        {"budget": 25, "sodium": 1200, "size": 1},
        {"budget": 60, "sodium": 600, "size": 3},
        {"budget": 0, "sodium": 1000, "size": 2},
    ]
    # 固定时间，保证两次运行可比
    now = datetime(2026, 10, 13, 14, 30)

    cases = []
    for g in grid:
        r = optimize(
            budget=g["budget"] or None,
            max_sodium_mg=g["sodium"] or None,
            max_items=g["size"],
            now=now,
        )
        cases.append({
            "input": g,
            "frontier": [
                {
                    "names": sorted(p.names),
                    "price": round(p.price, 2),
                    "sodium": round(p.sodium_mg, 1),
                }
                for p in r.frontier
            ],
            "plan_count": len(r.plans),
        })
    return {"now": now.strftime("%Y-%m-%d %H:%M"), "cases": cases}


def main():
    payload = build_payload()
    stats = payload["stats"]

    html = (HTML_TEMPLATE
            .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
            .replace("__MENU_ALL__", str(stats["menu_all"]))
            .replace("__NUT_ALL__", str(stats["nutrition_all"]))
            .replace("__JOINT__", str(stats["joint"]))
            .replace("__GENERATED_AT__", payload["generated_at"]))

    out_dir = ROOT / "docs"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "index.html"
    out.write_text(html, encoding="utf-8")

    expected = build_parity_expected()
    exp_path = out_dir / "parity_expected.json"
    exp_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    print(f"已生成 {out}")
    print(f"  联合目录 {stats['joint']} 项 / 菜单 {stats['menu_all']} 项")
    print(f"  文件大小 {out.stat().st_size / 1024:.1f} KB")
    print(f"已生成 {exp_path}（{len(expected['cases'])} 个对拍用例）")


if __name__ == "__main__":
    main()