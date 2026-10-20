# -*- coding: utf-8 -*-
"""
营养约束求解器

在不依赖 MCP 的情况下，基于随包营养数据集完成：
  · 营养画像检索（低钠 / 低热量 / 高蛋白）
  · 预算约束下的套餐组合优选
  · 与门店可用券的交叉匹配

设计原则：纯函数、无网络依赖、可测试。
MCP 在线时由 skill 层负责拉取实时券与价格；离线时用data/nutrition_mcd.json 兜底。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "nutrition_mcd.json"

# 单人份量下，各餐品的默认份数与计价类别
# 计价类别用于组合时的价格估算；真实价格以 MCP calculate-price 为准
PORTION_DEFAULTS = {
    "drink": 1,
    "burger": 1,
    "side": 1,
    "dessert": 1,
}

CATEGORY_RULES = (
    # 关键词, 类别
    (("麦旋风", "新地", "派", "冰淇淋", "雪冰", "拉明顿", "奶冻", "棒", "甜品"), "dessert"),
    (("薯条", "玉米杯", "鸡块", "趣鸡球", "鸡翅", "脆汁鸡", "V翅", "小食", "油条",
      "脆薯饼", "笋卷", "多笋", "沙拉", "苹果片", "粥", "麦乐鸡", "那么大鸡排",
      "香肠", "营养卷", "黄金橙橙", "奶冻款", "爆珠款"), "side"),
    (("可乐", "雪碧", "红茶", "美式", "咖啡", "牛奶", "豆浆", "燕麦", "玛奇朵",
      "卡布奇诺", "阿芙佳朵", "怡泉", "苹果汁", "纯悦", "特浓", "浓缩", "浓醇",
      "奶铁", "朱古力", "麦旋酷"), "drink"),
    # 汉堡类：结构词（堡/卷/三件套）+ 无结构性修饰词的经典汉堡名
    (("堡", "麦满分", "三件套"), "burger"),
)

# 经典汉堡名（MCP 营养表中不含量词，需显式列出）
KNOWN_BURGERS = frozenset({
    "巨无霸", "汉堡包", "吉士汉堡包", "双层吉士汉堡", "麦香鸡", "麦香鱼",
    "板烧鸡腿堡", "麦辣鸡腿汉堡", "不素之霸双层牛堡", "双层深海鳕鱼堡",
    "儿童鱼排堡", "培根蔬萃双层牛堡", "培根安格斯厚牛堡", "芝士安格斯厚牛堡",
    "芝士双层安格斯厚牛堡", "培根双层安格斯厚牛堡", "猪柳炒双蛋堡",
    "原味板烧鸡腿炒双蛋堡",
})


@dataclass(frozen=True)
class NutritionItem:
    """单个餐品的营养条目。"""

    name: str
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float
    sodium_mg: float
    calcium_mg: float
    category: str = field(default="other", compare=False)

    @property
    def kcal_per_protein(self) -> float:
        """蛋白质密度：每克蛋白质带来的热量，用于高蛋白低热优选。"""
        return self.kcal / self.protein_g if self.protein_g > 0 else float("inf")


@dataclass(frozen=True)
class Constraints:
    """营养与预算约束。"""

    max_kcal: float | None = None
    max_sodium_mg: float | None = None
    max_fat_g: float | None = None
    min_protein_g: float | None = None
    min_calcium_mg: float | None = None
    budget: float | None = None
    exclude: frozenset[str] = frozenset()
    categories: frozenset[str] | None = None

    def is_empty(self) -> bool:
        return all(
            getattr(self, f) is None
            for f in ("max_kcal", "max_sodium_mg", "max_fat_g",
                      "min_protein_g", "min_calcium_mg", "budget")
        ) and not self.exclude and self.categories is None


@dataclass
class NutritionTotals:
    """组合的营养合计。"""

    kcal: float = 0.0
    protein_g: float = 0.0
    fat_g: float = 0.0
    carb_g: float = 0.0
    sodium_mg: float = 0.0
    calcium_mg: float = 0.0
    items: list[NutritionItem] = field(default_factory=list)

    def add(self, item: NutritionItem, qty: int = 1) -> None:
        self.kcal += item.kcal * qty
        self.protein_g += item.protein_g * qty
        self.fat_g += item.fat_g * qty
        self.carb_g += item.carb_g * qty
        self.sodium_mg += item.sodium_mg * qty
        self.calcium_mg += item.calcium_mg * qty
        self.items.extend([item] * qty)

    def summary(self) -> str:
        names = " + ".join(i.name for i in self.items)
        return (f"{names}\n"
                f"热量 {self.kcal:.0f}kcal · 蛋白 {self.protein_g:.0f}g · "
                f"脂肪 {self.fat_g:.0f}g · 碳水 {self.carb_g:.0f}g\n"
                f"钠 {self.sodium_mg:.0f}mg · 钙 {self.calcium_mg:.0f}mg")


def classify(name: str) -> str:
    """按名称关键词推断餐品类别。"""
    if name in KNOWN_BURGERS:
        return "burger"
    for keywords, category in CATEGORY_RULES:
        if any(k in name for k in keywords):
            return category
    return "other"


def load_dataset(path: Path | str | None = None) -> list[NutritionItem]:
    """加载营养数据集。"""
    target = Path(path) if path else DATA_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    items = []
    for row in raw["items"]:
        # 兼容个别条目可能出现的重复键字段
        carb = row.get("carb_g", row.get("carb_mg", 0))
        items.append(NutritionItem(
            name=row["name"],
            kcal=float(row["kcal"]),
            protein_g=float(row["protein_g"]),
            fat_g=float(row["fat_g"]),
            carb_g=float(carb),
            sodium_mg=float(row["sodium_mg"]),
            calcium_mg=float(row["calcium_mg"]),
            category=classify(row["name"]),
        ))
    return items


def _violates(totals: NutritionTotals, c: Constraints) -> str | None:
    """返回违反的约束名，全部满足则返回 None。"""
    if c.max_kcal is not None and totals.kcal > c.max_kcal:
        return f"热量 {totals.kcal:.0f} > {c.max_kcal:.0f}kcal"
    if c.max_sodium_mg is not None and totals.sodium_mg > c.max_sodium_mg:
        return f"钠 {totals.sodium_mg:.0f} > {c.max_sodium_mg:.0f}mg"
    if c.max_fat_g is not None and totals.fat_g > c.max_fat_g:
        return f"脂肪 {totals.fat_g:.0f} > {c.max_fat_g:.0f}g"
    if c.min_protein_g is not None and totals.protein_g < c.min_protein_g:
        return f"蛋白 {totals.protein_g:.0f} < {c.min_protein_g:.0f}g"
    if c.min_calcium_mg is not None and totals.calcium_mg < c.min_calcium_mg:
        return f"钙 {totals.calcium_mg:.0f} < {c.min_calcium_mg:.0f}mg"
    return None


def filter_items(items: Iterable[NutritionItem],
                 c: Constraints) -> list[NutritionItem]:
    """按单品级约束粗筛，缩小组合搜索空间。"""
    out = []
    for it in items:
        if it.name in c.exclude:
            continue
        if c.categories and it.category not in c.categories:
            continue
        if c.max_kcal is not None and it.kcal > c.max_kcal:
            continue
        if c.max_sodium_mg is not None and it.sodium_mg > c.max_sodium_mg:
            continue
        if c.max_fat_g is not None and it.fat_g > c.max_fat_g:
            continue
        out.append(it)
    return out


def _trim_pool(items: list[NutritionItem],
               per_category: int = 6) -> list[NutritionItem]:
    """同类别保留钠含量最低的若干项，压缩搜索空间。"""
    by_cat: dict[str, list[NutritionItem]] = {}
    for it in items:
        by_cat.setdefault(it.category, []).append(it)
    trimmed: list[NutritionItem] = []
    for group in by_cat.values():
        group.sort(key=lambda x: (x.sodium_mg, x.kcal))
        trimmed.extend(group[:per_category])
    return trimmed


def enumerate_combos(items: list[NutritionItem],
                     c: Constraints,
                     max_size: int = 3,
                     max_per_category: int = 2,
                     pool_cap: int = 6) -> list[NutritionTotals]:
    """
    枚举所有满足约束的组合。

    同时施加：增量剪枝（钠/热量超标立即回溯）、
    多样性约束（同类别最多 max_per_category 项）、
    按餐品名去重。
    """
    pool = filter_items(items, c)
    if not pool:
        return []

    trimmed = _trim_pool(pool, per_category=pool_cap)
    out: list[NutritionTotals] = []
    seen: set[tuple[str, ...]] = set()

    def walk(start: int, chosen: list[NutritionItem]) -> None:
        if len(chosen) >= 2:
            cats = [i.category for i in chosen]
            if max(cats.count(x) for x in set(cats)) <= max_per_category:
                t = NutritionTotals()
                for it in chosen:
                    t.add(it)
                if _violates(t, c) is None:
                    key = tuple(sorted(i.name for i in chosen))
                    if key not in seen:
                        seen.add(key)
                        out.append(t)
        if len(chosen) >= max_size:
            return
        for idx in range(start, len(trimmed)):
            cand = trimmed[idx]
            same = sum(1 for i in chosen if i.category == cand.category)
            if same >= max_per_category:
                continue
            cur = chosen + [cand]
            partial = NutritionTotals()
            for i in cur:
                partial.add(i)
            if c.max_sodium_mg is not None and partial.sodium_mg > c.max_sodium_mg:
                continue
            if c.max_kcal is not None and partial.kcal > c.max_kcal:
                continue
            walk(idx + 1, cur)

    walk(0, [])
    return out


def find_combos(items: list[NutritionItem],
                c: Constraints,
                max_size: int = 3,
                limit: int = 5) -> list[tuple[NutritionTotals, float]]:
    """
    枚举满足约束的组合，按「钠含量更低 + 热量更优」排序。

    返回 (营养合计, 综合评分) 列表，评分越小越优。
    评分函数对钠与热量做归一化加权，体现「同样吃饱，钠越低越好」。
    """
    found = [(t, _score(t)) for t in enumerate_combos(items, c, max_size=max_size)]
    found.sort(key=lambda pair: pair[1])
    return found[:limit]


def _score(t: NutritionTotals) -> float:
    """
    综合评分：钠权重最高，热量次之，蛋白正向加权。数值越小越优。

    另含「饱腹度」惩罚项：仅饮品构成的组合热量过低、不构成一餐，
    会被施加惩罚，避免出现「控钠午餐 = 三杯咖啡」这类不合理结果。
    """
    sodium_penalty = t.sodium_mg / 100.0 * 3.0
    kcal_penalty = t.kcal / 100.0 * 1.0
    protein_bonus = t.protein_g * 0.15

    # 饱腹度：一份正餐热量约在 200-700kcal 区间。
    # 低于 200kcal 说明只点了饮料/小食，不足以称为一餐。
    if t.kcal < 200:
        satiety_penalty = (200 - t.kcal) / 100.0 * 2.5
    else:
        satiety_penalty = 0.0

    return sodium_penalty + kcal_penalty - protein_bonus + satiety_penalty


def recommend(items: list[NutritionItem],
              c: Constraints,
              max_size: int = 3,
              limit: int = 5) -> list[tuple[NutritionTotals, float]]:
    """对外推荐接口：返回满足约束的最优组合。"""
    return find_combos(items, c, max_size=max_size, limit=limit)


def rank_by(items: list[NutritionItem],
            metric: str,
            reverse: bool = False,
            limit: int = 10) -> list[NutritionItem]:
    """按单个营养指标排行，便于「哪些菜钠最低」这类查询。"""
    if metric not in {"kcal", "protein_g", "fat_g", "carb_g",
                      "sodium_mg", "calcium_mg"}:
        raise ValueError(f"不支持的指标：{metric}")
    return sorted(items, key=lambda x: getattr(x, metric),
                  reverse=reverse)[:limit]


# --------------------------------------------------------------------------- #
# 帕累托前沿
# --------------------------------------------------------------------------- #

def pareto_frontier(items: list[NutritionItem],
                    max_kcal: float | None = None,
                    max_sodium_mg: float | None = None,
                    max_size: int = 3,
                    limit: int = 20) -> list[tuple[NutritionTotals, float]]:
    """
    营养维度（热量 × 钠）的帕累托前沿。

    含义：前沿上的每个组合都是「不可支配」的——想再降钠就必须接受更高热量，
    想再降热量就必须接受更高钠。它回答的是：

        平价与低钠不可兼得时，边界在哪？

    返回按钠含量升序排列的 (营养合计, 热量) 列表，
    热量字段直接取 totals.kcal，第二项保留以便与 find_combos 接口一致。
    """
    c = Constraints(max_kcal=max_kcal, max_sodium_mg=max_sodium_mg)
    combos = enumerate_combos(items, c, max_size=max_size)
    if not combos:
        return []

    # 先按 (热量, 钠) 排序，再做支配关系扫描
    combos.sort(key=lambda t: (t.kcal, t.sodium_mg))

    front: list[NutritionTotals] = []
    best_sodium = float("inf")
    for t in combos:
        # 已按热量升序遍历：只要钠严格低于此前所有点，即为前沿点
        if t.sodium_mg < best_sodium - 1e-9:
            front.append(t)
            best_sodium = t.sodium_mg

    front.sort(key=lambda t: t.sodium_mg)
    return [(t, t.kcal) for t in front[:limit]]


def is_dominated(a: NutritionTotals, b: NutritionTotals) -> bool:
    """
    a 是否被 b 支配（两个维度都不优于 b，且至少一个维度严格更差）。
    供测试与调试使用。
    """
    no_worse = b.kcal <= a.kcal and b.sodium_mg <= a.sodium_mg
    strictly_better = b.kcal < a.kcal or b.sodium_mg < a.sodium_mg
    return no_worse and strictly_better