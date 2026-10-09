# 麦麦省钱营养师 · MCD Budget Planner

**「我想吃麦当劳，但想控钠 / 想花 30 块以内 / 别浪费我的券」——说人话，它算出实付最省的组合。**

基于麦当劳 MCP Server 的「预算 + 营养」双约束套餐优选 Skill。
不是券列表查询器，是**点餐决策器**：把「省钱的券」和「健康的餐」放在一起求解。

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-mcd--mcp-orange.svg)](MCP_INTEGRATION.md)
[![Tests](https://img.shields.io/badge/tests-12%2F12%20passed-brightgreen.svg)](tests/test_solver.py)

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
| 💰 带券价格试算 | 调用 `calculate-price` 拿真实实付金额，不是估算 |
| 🥗 营养约束求解 | 支持控钠 / 控热量 / 高蛋白 / 高钙多维约束组合枚举 |
| 🏪 四种场景适配 | 到店自取、得来速、麦乐送、企业团餐 |
| 🔒 安全边界 | 止步于试算，不自动下单；积分抽奖只算不动 |

---

## 快速开始

### 方式一：离线体验（无需 MCP、无需网络）

```bash
git clone https://github.com/AAA-EE/mcd-budget-planner.git
cd mcd-budget-planner

# 运行离线演示：5 个真实场景
python examples/demo_offline.py

# 运行单元测试：12 项
python tests/test_solver.py
```

`examples/demo_offline.py` 会输出：

```
场景一：控钠午餐｜钠 ≤ 600mg 且 热量 ≤ 500kcal
  → 小杯玉米杯 + 大杯玉米杯 + 浓缩咖啡
    热量 153kcal · 蛋白 7g · 钠 3mg

场景三：钠含量最低的 8 款餐品
  → 0mg  147kcal  可乐中杯
    0mg    2kcal  锡兰红茶
    ...

场景四：零热量饮品（用于替换含糖饮料）
  → 0kcal  钠 35mg  无糖可口可乐中杯
    0kcal  钠  0mg  纯悦
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
│       └── solver.py            # 营养约束求解器（核心算法）
├── examples/
│   └── demo_offline.py          # 离线演示：5 个场景
├── tests/
│   └── test_solver.py           # 12 项单元测试
├── skills/
│   └── mcd-deal-gen/            # 可安装的 WorkBuddy Skill
│       ├── SKILL.md
│       └── scripts/price_planner.py
└── docs/
    └── ALGORITHM.md             # 算法说明
```

---

## 算法说明

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