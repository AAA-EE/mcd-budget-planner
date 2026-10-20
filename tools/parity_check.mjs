/**
 * 前后端对拍校验
 *
 * 页面里的求解算法是 Python 实现的 JavaScript 移植版。两份代码独立存在，
 * 难免出现漂移——改了 Python 忘了改 JS，页面就会给出错误结果。
 *
 * 本脚本从 docs/index.html 中提取 JS 算法，在最小 DOM 桩下执行，
 * 用与 Python 相同的输入跑一遍，比对帕累托前沿是否一致。
 *
 * 用法：
 *     node tools/parity_check.mjs
 *
 * 退出码：0 = 全部一致，1 = 存在差异
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

// --------------------------------------------------------------------------- //
// 最小 DOM 桩：只提供脚本实际用到的接口
// --------------------------------------------------------------------------- //

function makeStub() {
  const stub = {
    value: '0',
    textContent: '',
    innerHTML: '',
    dataset: {},
    viewBox: null,
    classList: { add() {}, remove() {}, contains() { return false; } },
    addEventListener() {},
    querySelector() { return makeStub(); },
    querySelectorAll() { return []; },
    appendChild() {},
  };
  return stub;
}

function installDomStubs() {
  const cache = new Map();
  globalThis.document = {
    getElementById(id) {
      if (!cache.has(id)) cache.set(id, makeStub());
      return cache.get(id);
    },
    querySelector() { return makeStub(); },
    querySelectorAll() { return []; },
    createElement() { return makeStub(); },
  };
  globalThis.window = globalThis;
}

// --------------------------------------------------------------------------- //
// 提取并执行页面脚本
// --------------------------------------------------------------------------- //

function loadPageEngine() {
  const html = readFileSync(join(ROOT, 'docs', 'index.html'), 'utf8');

  // 取最后一个 <script> 块（前一个是外链时也能正确跳过）
  const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)];
  if (!blocks.length) {
    throw new Error('未在 index.html 中找到内联脚本');
  }
  const source = blocks[blocks.length - 1][1];

  installDomStubs();
  // 用间接 eval 让脚本在全局作用域执行，从而挂上 globalThis.MCD
  const runner = new Function(source);
  runner();

  if (!globalThis.MCD) {
    throw new Error('页面脚本未导出 MCD 接口');
  }
  return globalThis.MCD;
}

// --------------------------------------------------------------------------- //
// 对拍
// --------------------------------------------------------------------------- //

function compare() {
  const api = loadPageEngine();
  const expected = JSON.parse(
    readFileSync(join(ROOT, 'docs', 'parity_expected.json'), 'utf8')
  );

  const [y, mo, d, hh, mm] = expected.now
    .split(/[- :]/)
    .map(Number);
  const now = new Date(y, mo - 1, d, hh, mm);

  let pass = 0;
  const failures = [];

  for (const c of expected.cases) {
    const { budget, sodium, size } = c.input;
    const res = api.solve(budget, sodium, size, now);

    const got = res.front
      .map(p => ({
        names: p.items.map(x => x.n).sort(),
        price: Math.round(p.price * 100) / 100,
        sodium: Math.round(p.s * 10) / 10,
      }))
      .sort((a, b) => a.price - b.price || a.sodium - b.sodium);

    const want = c.frontier
      .map(p => ({
        names: [...p.names].sort(),
        price: Math.round(p.price * 100) / 100,
        sodium: Math.round(p.sodium * 10) / 10,
      }))
      .sort((a, b) => a.price - b.price || a.sodium - b.sodium);

    const gotJson = JSON.stringify(got);
    const wantJson = JSON.stringify(want);

    if (gotJson === wantJson) {
      pass += 1;
      console.log(
        `  PASS  预算${budget || '不限'} 钠${sodium || '不限'} ${size}件` +
        ` → 前沿 ${got.length} 点`
      );
    } else {
      failures.push({ input: c.input, got, want });
      console.log(
        `  FAIL  预算${budget || '不限'} 钠${sodium || '不限'} ${size}件`
      );
      console.log(`        JS  : ${gotJson}`);
      console.log(`        Py  : ${wantJson}`);
    }
  }

  const total = expected.cases.length;
  console.log(`\n共 ${total} 个用例，一致 ${pass}，不一致 ${failures.length}`);
  return failures.length === 0;
}

let ok = false;
try {
  ok = compare();
} catch (e) {
  console.error(`对拍执行失败：${e.message}`);
  console.error(e.stack);
}
process.exit(ok ? 0 : 1);