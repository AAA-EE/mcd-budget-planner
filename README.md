# 麦麦省钱营养师 · MCD Budget Planner

**「我想吃麦当劳，但想控钠 / 想花 30 块以内 / 别浪费我的券」——说人话，它算出实付最省的组合。**

基于麦当劳 MCP Server 的「预算 + 营养」双约束套餐优选 Skill。
不是券列表查询器，是**点餐决策器**：把「省钱的券」和「健康的餐」放在一起求解。

[![CI](https://github.com/AAA-EE/mcd-budget-planner/actions/workflows/ci.yml/badge.svg)](https://github.com/AAA-EE/mcd-budget-planner/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-mcd--mcp-orange.svg)](MCP_INTEGRATION.md)
[![Tests](https://img.shields.io/badge/tests-49%20passed-brightgreen.svg)](tests/)
[![Parity](https://img.shields.io/badge/parity-7%2F7%20matched-blueviolet.svg)](tools/parity_check.mjs)

### 🎮 [**在线试算 → 打开即玩，无需安装**](https://aaa-ee.github.io/mcd-budget-planner/)

拖动「预算」和「钠上限」两个滑块，实时算出实付最省且钠可控的组合，
下方同步显示**价格 × 钠的帕累托前沿**。页面算法与仓库内 Python 实现通过
前后端对拍校验，两边结果必须完全一致，否则 CI 会失败。

---

## 30 秒看懂

```
你：30块以内怎么点？还想控钠

它：卡包 14 张券 → 此刻该门店真实可用 1 张
    营养数据 → 158 项餐品，钠从 0mg 到 1373mg
    约束求解 →

    最省方案：薯薯任选 ×1
    实付 ¥9.90（原价 ¥16.00，省 ¥6.10）
    门店：成都南站站前广场（步行 273m）

    ─── 其他可选 ───
    · 火腿扒麦满分 单点 约 ¥11.00　无券可用，钠 608mg
    · 巨无霸 + 中杯可乐 约 ¥24.00　钠 961mg（若不控钠）

    ⚠ 你卡包里还有 10 张早餐券，但有效期是每天 05:00–10:29，
      下午用不了，明天早点去
```

**这条回复背后是 6 次 MCP 调用**，包括门店定位、券可用性二次核验、
带券价格试算（拿到真实 `couponId` 而不是估算），再叠加 158 项营养数据的约束求解。

---

## 为什么需要它：两个反直觉的实测发现

### 发现一：卡包里有券 ≠ 此刻能用

联调时实测某用户卡包有 **14 张券**，但在同一时刻、同一门店，
`query-store-coupons` 只认得出 **1 张**：

| 数据源 | 返回 |
|---|---|
| `query-my-coupons`（卡包资产） | 14 张「可用」券 |
| `query-store-coupons`（同门店同场景） | **1 张** |

差的 10 张是早餐券，有效期限定每日 `05:00–10:29`，而查询时刻是 18:23。

**MCP 文档明确声明 `query-my-coupons` 不做门店、渠道、场景校验**——
返回的是「我拥有的」，不是「我能用的」。

> 由此得出本项目最关键的一条约束：**券可用性必须以门店维度二次确认为准，
> 不得用卡包数据直接推导。** 顺序反了，整个逻辑就是错的。

### 发现二：营养差异有三个数量级

MCP 营养接口返回 158 项餐品，钠含量跨度极大：

| 餐品 | 钠含量 |
|---|---|
| 纯悦 / 可乐 | **0 mg** |
| 火腿扒麦满分 | 608 mg |
| 巨无霸 | 961 mg |
| 麦辣鸡腿汉堡 | 1208 mg |
| 芝士双层安格斯厚牛堡 | **1373 mg** |

一份巨无霸的钠含量是中杯可乐的上千倍。但这些数据以紧凑字符串形式返回，
用户既看不懂，也没法用来做选择。

**本项目做的事**，是把这两类数据交叉起来 —— 让省钱和健康能同时被满足，
而不是二选一。

---

## 核心能力

| 能力 | 说明 |
|---|---|
| 🎫 真实可用券核验 | 不轻信卡包数据，以门店维度二次确认券是否真的能用 |
| 💰 本地定价引擎 | 菜单标价 + 券规则 + 叠加冲突判定，算价不依赖远程接口 |
| 🥗 营养约束求解 | 支持控钠 / 控热量 / 高蛋白 / 高钙多维约束组合枚举 |
| 📉 价格 × 钠 帕累托前沿 | 回答「想再便宜就得吃多少钠」这条边界的形状 |
| 🔄 同类替代建议 | 「我就想吃巨无霸」→ 同类里有没有更便宜又更少钠的 |
| 🏪 四种场景适配 | 到店自取、得来速、麦乐送、企业团餐 |
| 🔒 安全边界 | 止步于试算，不自动下单；积分抽奖只算不动 |

### 为什么是「价格 × 钠」，不是「价格 × 热量」

热量是常见维度，但钠更值得关注：中国居民钠摄入普遍超标，
而一份巨无霸的钠含量（961mg）已接近每日建议上限（约 2000mg）的一半。

这个维度上的差异是**数量级**的，不是边际的：

| 餐品 | 价格 | 钠 | 热量 |
|---|---|---|---|
| 纯悦 | ¥7.50 | **0mg** | 0kcal |
| 麦香鱼 | ¥22.50 | 556mg | 325kcal |
| 麦辣鸡腿汉堡 | **¥22.50** | **1208mg** | 485kcal |
| 巨无霸 | ¥25.50 | 961mg | 513kcal |
| 双层吉士汉堡 | ¥23.00 | 1017mg | 429kcal |
| 芝士安格斯厚牛堡 | ¥31.50 | **1373mg** | 1003kcal |

注意第二行和第三行：**同为 ¥22.50，钠含量差 2.2 倍**。
同样的钱，选哪个更值得，这就是本项目要回答的问题。

---

## 在线页面

`docs/index.html` 是单文件应用，无后端、无构建、无依赖，
直接部署到 GitHub Pages 即可访问。

页面内嵌：
- 41 项「同时具备价格与营养」的餐品数据
- 券的有效期 / 适用星期 / 时段判定逻辑
- 与 Python 完全一致的组合枚举与帕累托求解

**前后端一致性怎么保证**：两份实现独立存在，难免漂移。
`tools/parity_check.mjs` 从 `index.html` 中抽取 JS 算法，
在最小 DOM 桩下执行，用与 Python 相同的 7 组输入跑一遍，
比对帕累托前沿是否逐点一致。CI 中这一步失败即构建失败。

```bash
# 本地重新生成页面（数据变动后需要）
python tools/build_site.py

# 对拍校验
node tools/parity_check.mjs
# → 共 7 个用例，一致 7，不一致 0
```

### 部署到 GitHub Pages

1. 仓库 **Settings → Pages**
2. Source 选 `Deploy from a branch`
3. Branch 选 `main`，目录选 `/docs`
4. 保存后约 1 分钟可访问 `https://<用户名>.github.io/mcd-budget-planner/`

CI 中有一项检查：若 `docs/` 与 `python tools/build_site.py` 的生成结果不一致，
构建会失败并提示重新生成。这样可以避免改了数据却忘记重建页面。

---

## 快速开始

### 方式一：离线体验（无需 MCP、无需网络）

```bash
git clone https://github.com/AAA-EE/mcd-budget-planner.git
cd mcd-budget-planner

# 营养约束求解演示：5 个场景
python examples/demo_offline.py

# 价格 × 钠 帕累托前沿演示：5 个场景
python examples/demo_optimize.py

# 全部单元测试：49 项
python tests/test_solver.py
python tests/test_pricing.py
python tests/test_optimizer.py

# 前后端对拍：7 个用例
node tools/parity_check.mjs
```

`examples/demo_optimize.py` 的核心输出：

```
场景三｜同价不同钠：这是本项目的核心发现
  麦辣鸡腿汉堡   ¥22.50  钠 1208mg  热量 485kcal
  麦香鱼        ¥22.50  钠  556mg  热量 325kcal

  两者同为 ¥22.50，但后者钠少 652mg（54%）。
  同样的钱，选哪个更值得，一目了然。

场景四｜「我就想吃巨无霸」—— 有更好的同类替代吗
目标：巨无霸　¥25.50　钠 961mg
  → ¥17.00 钠 731mg  麦香鸡             便宜 ¥8.50、少钠 230mg
  → ¥22.50 钠 556mg  麦香鱼             便宜 ¥3.00、少钠 405mg
  → ¥24.00 钠 917mg  双层深海鳕鱼堡       便宜 ¥1.50、少钠 44mg
```

### 方式二：作为 WorkBuddy Skill 使用（完整体验）

将`skills/mcd-deal-gen/` 目录复制到 `~/.workbuddy/skills/` 后：

```bash
cp -r skills/mcd-deal-gen ~/.workbuddy/skills/
```

重启会话后，用自然语言触发：

```
帮我配个30块以内的麦当劳
我要吃麦当劳，但想控钠
明天早餐有什么券能用
用券点单，最便宜的要多少
低钠的麦当劳套餐推荐一下
```

Skill 会自动完成：场景确认 → 门店定位 → 券可用性核验 → 餐品与营养匹配 → 带券试算 →排序输出。

### 方式三：调用试算任务生成器

```bash
# 生成一个带券试算的 MCP 调用任务
python skills/mcd-deal-gen/scripts/price_planner.py \
  --store 3450312 \
  --be-type 1 \
  --item 9900016370:1 \
  --coupon "E86377A0349D730EF7C27EBBE7B4C0FE:MCD60Z01Y0V19V9B24804" \
  --tableware
```

输出（已实测与真实成功调用的参数完全一致）：

```json
{
  "tool": "mcp__mcd-mcp__calculate-price",
  "params": {
    "storeCode": "3450312",
    "orderType": 1,
    "beType": 1,
    "items": [{
      "productCode": "9900016370",
      "quantity": 1,
      "couponId": "E86377A0349D730EF7C27EBBE7B4C0FE",
      "couponCode": "MCD60Z01Y0V19V9B24804"
    }],
    "needTableware": true
  }
}
```

---

## 项目结构

```
mcd-budget-planner/
├── README.md                    # 本文件
├── CONTEST_DECLARATION.md       # 参赛声明（官方原文，未改动）
├── MCP_INTEGRATION.md           # MCP Server / Tool / 调用流程说明
├── workbuddy.md                 # WorkBuddy 开发对话上下文
├── LICENSE
├── data/
│   └── nutrition_mcd.json       # 158 项营养数据集（去重后）
├── src/
│   └── mcd_planner/
│       ├── solver.py            # 营养约束求解 + 帕累托前沿
│       ├── pricing.py           # 本地定价引擎 + 券叠加冲突判定
│       └── optimizer.py         # 价格×钠 联合求解与同类替代
├── examples/
│   ├── demo_offline.py          # 营养维度演示：5 个场景
│   └── demo_optimize.py         # 帕累托与券效果演示：5 个场景
├── tests/
│   ├── test_solver.py           # 12 项
│   ├── test_pricing.py          # 22 项
│   └── test_optimizer.py        # 15 项
├── tools/
│   ├── build_site.py            # 从数据生成 docs/index.html
│   └── parity_check.mjs         # 前后端对拍校验
├── skills/
│   └── mcd-deal-gen/            # 可安装的 WorkBuddy Skill
│       ├── SKILL.md
│       └── scripts/price_planner.py
├── .github/workflows/ci.yml     # CI：49 项测试 + 对拍 + 构建一致性
└── docs/
    ├── index.html               # 在线试算页（单文件，可直接部署）
    └── ALGORITHM.md             # 算法说明
```

---

## 算法说明

### 三个模块的分工

```
pricing.py      「这一篮多少钱」
                菜单标价 → 券适用性判定 → 叠加冲突裁决 → 实付
                        ↓
solver.py       「这一篮有多少钠」
                营养合计 → 硬约束过滤 → 组合枚举 → 帕累托前沿
                        ↓
optimizer.py    「两者一起看」
                价格 × 钠 联合前沿 + 同类替代建议
```

拆开的理由是：定价逻辑需要密集测试（券时段、星期、叠加规则都是易错点），
营养逻辑则是纯数学。混在一起既难测也难改。

### 券叠加：一个显式假设

MCP 的 `query-store-coupons` **只返回券的适用商品与券后价，不返回 stacking 字段**。
也就是说，麦当劳没有公开「哪些券能同时用」。

本项目的处理是：**默认一单一张券**（`STACK_SINGLE`），并在输出中标注该假设。
宁可给出保守的价格，也不猜一个更乐观的数字。

需要时可通过 `stack_policy=STACK_GREEDY` 切换为多券叠加，
此时会先做两两冲突检测：

```python
conflict_reason(a, b)  # 返回 None 表示可叠加，否则返回冲突原因
# 规则：同商品被两张券覆盖 → 冲突
#       全场券 vs 单品券   → 冲突（已被全场券覆盖）
#       两张全场券         → 冲突
```

### 约束求解

支持同时施加多维约束，求解满足全部硬约束的组合：

```python
Constraints(
    max_sodium_mg=600,     # 钠上限
    max_kcal=500,          # 热量上限
    min_protein_g=15,      # 蛋白下限
    budget=30,             # 预算上限（元）
    exclude=frozenset({"巨无霸"}),  # 排除项
    categories=frozenset({"burger", "side", "drink"}),  # 类别限定
)
```

### 帕累托前沿

`price × sodium` 双目标最小化。判定逻辑很直接：

```python
# 按价格升序遍历，只要钠严格低于此前所有点，就是前沿点
for p in sorted(plans, key=lambda x: (x.price, x.sodium_mg)):
    if p.sodium_mg < best_sodium:
        frontier.append(p)
        best_sodium = p.sodium_mg
```

**一个反直觉的结果**：在 41 项可参与求解的餐品中，
即使枚举近 4000 个组合，帕累托前沿也只有 **2 个点**。

这说明绝大多数组合都能被某个更便宜或更低钠的选项替代。
前沿越短，说明市场供给越「有效率」——这个观察本身就是有价值的。

### 排序评分

在满足硬约束的候选中，按综合评分升序：

```
score = 3.0 × (钠/100) + 1.0 × (热量/100) - 0.15 × 蛋白 - 饱腹惩罚
```

- **钠权重最高（3.0）**：实测数据中钠含量差异达三个数量级，是首要筛选维度
- **饱腹惩罚**：热量低于 200kcal 的组合会被惩罚，避免出现「控钠午餐 = 三杯咖啡」这类不合理结果
- **蛋白正向加权**：同等条件下优先高蛋白

### 剪枝策略

1. **单品级粗筛**：先按约束过滤单品，缩小搜索空间
2. **同类目截断**：每个类别保留钠含量最低的 6 项
3. **增量剪枝**：递归过程中钠/热量一旦超标立即剪枝
4. **多样性约束**：同类别最多选 2 项，避免堆砌同类

分类覆盖率：148/158（剩余 10 项为联名新品，无法可靠归类，保留 `other` 类别）

---

## 目标用户

| 用户 | 典型诉求 |
|---|---|
| 上班族 | 「30 块以内早餐怎么点」「今天的券别浪费了」 |
| 健身/控卡人群 | 「低钠高蛋白的套餐」「热量别超 500」 |
| 家庭用户 | 「小孩能吃的低钠选择」「零热量饮料替换」 |
| 企业行政 | 团餐预算与满减满折规则解读（接口已预留） |

---

## 项目特色

**1. 基于实测，而非文档推测**

`MCP_INTEGRATION.md` 中记录的每一条接口行为都来自真实联调，包括三个「反直觉」发现：

- 卡包 14 张券 ≠ 14 张可用券
- 传 `reservationDate` 反而让可用券查询返回空
- 营养接口原始返回 162 行，含 4 行重复数据

这些特征直接决定了项目的实现方式，文档中均如实记录。

**2. 双层架构，可离线验证**

MCP 只负责必须实时的部分（门店、券、价格），营养计算放在离线层。
好处是核心算法能被单元测试覆盖，项目在无 MCP 环境下也能完整运行和演示。

**3. 有安全边界的自动化**

明确不调用 `create-order`（需用户明确确认），不调用 `draw-lottery`
（MCP 要求人工确认消耗且有频次限制）。自动化程度止于「推荐」而非「购买」。

---

## 隐私与合规

- 不含任何真实 Token、密钥、密码或账号凭证
- 不含任何用户个人信息
- 不执行下单操作，不产生实际消费
- 营养数据来自 MCP 公开接口，不含用户数据

详见 `CONTEST_DECLARATION.md`。

---

## License

MIT License，见 [LICENSE](LICENSE)。

本项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。
项目输出仅供参考，不构成医疗、营养或其他专业建议；
餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。