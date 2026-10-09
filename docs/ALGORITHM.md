# 算法说明

本文档解释 `src/mcd_planner/solver.py` 的设计依据与实现细节。

---

## 1. 为什么需要约束求解

单看营养数据，158 项餐品中「钠含量最低」的结果往往是可乐、纯悦这类饮品——
它们钠含量为 0，但显然不构成一顿正餐。

同样，只看价格也无法回答「我想吃麦当劳但要控钠」这类复合诉求。

因此本模块的设计目标是：**在多个硬约束下，找出仍然像一顿饭的组合。**

---

## 2. 数据模型

### 2.1 NutritionItem

```python
@dataclass(frozen=True)
class NutritionItem:
    name: str
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float
    sodium_mg: float
    calcium_mg: float
    category: str  # burger / side / drink / dessert / other
```

`frozen=True` 保证条目不可变，组合运算中不会被意外修改。

派生属性 `kcal_per_protein`（每克蛋白质对应热量）用于高蛋白低热优选。

### 2.2 Constraints

```python
@dataclass(frozen=True)
class Constraints:
    max_kcal: float | None = None
    max_sodium_mg: float | None = None
    max_fat_g: float | None = None
    min_protein_g: float | None = None
    min_calcium_mg: float | None = None
    budget: float | None = None
    exclude: frozenset[str] = frozenset()
    categories: frozenset[str] | None = None
```

全部字段可选，任意组合均可。`None` 表示该维度不设限。

### 2.3 NutritionTotals

组合的营养合计，支持增量累加（`add(item, qty)`），便于递归过程中逐步计算。

---

## 3. 餐品分类

分类基于名称关键词匹配。实测 158 项中148 项可归类，
剩余 10 项为联名新品（苹板、果然多肉等），无法可靠判断类别，保留 `other`。

**设计取舍**：宁可归为 `other` 也不要归错。
错误的分类会让高钠汉堡被当作低钠小食推荐出去，
这比「无法分类」危害更大。

分类规则的优先级：

```
KNOWN_BURGERS（显式名单） → dessert → side → drink → burger（结构词）
```

### 为什么要显式列KNOWN_BURGERS

「巨无霸」「麦香鸡」「麦香鱼」等经典汉堡名中**不含量词**（「堡」「卷」「三件套」），
纯关键词匹配会漏判为 `other`，导致这类高蛋白餐品无法进入组合。
因此对这部分做显式枚举。

这是一个在开发中真实发现并修复的缺陷——`tests/test_solver.py::test_classify` 是其回归保护。

---

## 4. 求解流程

```
load_dataset()
     │
     ▼
filter_items()          ← 单品级粗筛，缩小搜索空间
  · 排除 exclude 中的餐品
  · 类别过滤
  · 单项已超标的直接剔除（如热量上限 300kcal 时，巨无霸 513kcal 必被剔除）
     │
     ▼
类别内截断             ← 每个类别保留钠含量最低的 6 项
  · 组合爆炸的主要来源是同质候选
  · 按 (钠, 热量) 排序后截断
     │
     ▼
递归枚举 + 剪枝
  · 增量剪枝：钠/热量一旦超标，立即跳过该分支
  · 多样性约束：同类别最多 2 项
  · 集合去重：按餐品名排序后作为 key
     │
     ▼
_score() 排序          ← 按综合评分升序
     │
     ▼
top-N 输出
```

---

## 5. 评分函数

```python
def _score(t: NutritionTotals) -> float:
    sodium_penalty = t.sodium_mg / 100.0 * 3.0
    kcal_penalty = t.kcal / 100.0 * 1.0
    protein_bonus = t.protein_g * 0.15

    if t.kcal < 200:
        satiety_penalty = (200 - t.kcal) / 100.0 * 2.5
    else:
        satiety_penalty = 0.0

    return sodium_penalty + kcal_penalty - protein_bonus + satiety_penalty
```

### 权重设定依据

| 项 | 权重 | 依据 |
|---|---|---|
| 钠 | 3.0 | 实测数据中钠含量从 0mg 到 1373mg，跨越三个数量级，是最主要的差异维度 |
| 热量 | 1.0 | 作为基础约束，量级相对可控 |
| 蛋白 | −0.15 | 正向奖励，鼓励高蛋白选择 |
| 饱腹 | 动态 | 见下|

### 饱腹惩罚：一个真实缺陷的修复

初版评分函数只有前三项，在「控钠午餐（钠 ≤ 600mg，热量 ≤ 500kcal）」场景下，
算法输出了这样的结果：

```
冰美式小杯 + 热美式小杯 + 浓缩咖啡
热量 33kcal · 钠 0mg
```

三杯咖啡，钠含量完美为0，但显然不是一顿午餐。

**根因**：评分函数只惩罚钠和热量，而这三项恰好在两个维度都最优
（零钠、近乎零热量），在纯数值上碾压了含汉堡的正餐方案。

**修复**：加入饱腹惩罚。热量低于 200kcal（一份正餐的下限）的组合会被施加惩罚：

```
satiety_penalty = (200 - kcal) / 100 * 2.5
```

同时加入多样性约束（同类别最多 2 项），防止出现「三杯咖啡」这类堆砌。

修复后同一场景的输出变为：

```
小杯玉米杯 + 大杯玉米杯 + 浓缩咖啡
热量 153kcal · 蛋白 7g · 钠 3mg
```

**回归测试**：`test_satiety_penalty_avoids_drink_only_combos`
断言每个推荐组合都必须包含 burger 或 side 类餐品。

---

## 6. 复杂度

设截断后候选数为 `n`，最大组合大小为 `k`：

- 过滤阶段：`O(n)`
- 枚举阶段：最坏 `O(n^k)`，但增量剪枝使实际搜索量大幅下降
- 多样性约束进一步将同质分支排除

实测 158 项数据集、`max_size=3` 时响应在毫秒级。

---

## 7. 已知局限

| 局限 | 说明 |
|---|---|
| 无价格数据 | 离线层不含价格，`budget` 约束需由在线层的 `calculate-price` 补足 |
| 营养为静态数据 | MCP 营养表为固定值，与门店实际出品可能存在偏差 |
| 不考虑饱腹感主观因素 | 200kcal 阈值是经验值，非营养学标准 |
| 分类覆盖 148/158 | 联名新品无法可靠归类 |
| 不处理套餐组合 | 仅支持单品组合，未解析套餐（round）结构 |

---

## 8. 与在线层的衔接

离线求解器产出**候选组合**，在线层负责**真实定价**：

```
离线层：营养约束 → 候选组合（不关心价格）
          │
          ▼
在线层：MCP calculate-price → 真实实付金额
          │
          ▼
最终排序：实付金额优先 / 营养达标的组合中选最便宜
```

这样分工的原因是：营养计算需要遍历大量组合，放在离线层可被单元测试验证；
而价格试算每次调用都有网络开销，应只对少量候选执行。