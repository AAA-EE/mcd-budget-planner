# -*- coding: utf-8 -*-
"""
本地定价引擎

设计动机
--------
MCP 的 `calculate-price` 是逐次往返的远程调用：每试一个组合就要发一次请求，
既慢又依赖接口稳定性。一旦接口异常（开发期实测出现过 `/items must be array`），
整个报价能力就瘫痪。

本模块把「算术」搬到本地：菜单标价 + 券规则 + 叠加判定 → 实付金额。
MCP 只负责取数（菜单、券面信息），不再参与计算。

这带来三个好处：
1. 定价可被单元测试覆盖，结果确定可复现
2. 一次枚举上千组合也不产生网络开销
3. 接口不可用时仍能给出报价（降级可用）

重要声明
--------
麦当劳 MCP 并未公开券的叠加规则（`query-store-coupons` 只返回券的适用商品
与券后价，不含 stacking 字段）。因此本引擎的叠加策略是**显式假设**，
默认取最保守的 `SINGLE`（一单仅用一张券），并在输出中标注假设，
避免给出比实际更乐观的价格。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Iterable, Sequence

# --------------------------------------------------------------------------- #
# 叠加策略
# --------------------------------------------------------------------------- #

STACK_SINGLE = "single"
STACK_GREEDY = "greedy"

# 默认保守：一单一张券。实测麦当劳常规订单也基本遵循此规则。
# 若用户在 MCP 端确认了可叠加组合，可显式切换为 GREEDY。
DEFAULT_STACK_POLICY = STACK_SINGLE


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MenuItem:
    """门店在售餐品。价格均为元。"""

    code: str
    name: str
    price: float
    original_price: float
    category: str = "other"

    @property
    def discount_rate(self) -> float:
        """门店自身的折扣率（现价 / 原价）。"""
        if self.original_price <= 0:
            return 1.0
        return self.price / self.original_price


@dataclass(frozen=True)
class Coupon:
    """
    优惠券。

    kind:
      - "special"   特价券：指定商品以 coupon_price 结算
      - "bogo"      买一送一：低价件免单
      - "threshold" 满减券：满 threshold 减 discount_amount
      - "discount"  折扣券：整体或指定商品按 discount_rate 打折

    product_codes 为空集表示全场通用（仅对 threshold / discount 有意义）。
    """

    coupon_id: str
    title: str
    kind: str
    product_codes: frozenset[str] = frozenset()
    coupon_price: float | None = None
    threshold: float | None = None
    discount_amount: float | None = None
    discount_rate: float | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    weekdays: frozenset[int] | None = None      # 0=周一 … 6=周日
    time_window: tuple[dtime, dtime] | None = None
    scopes: frozenset[str] = frozenset({"dine_in", "delivery"})

    # ---- 可用性判定 ----

    def is_time_valid(self, now: datetime) -> tuple[bool, str]:
        """券的时间维度是否可用。返回 (是否可用, 原因)。"""
        if self.valid_from and now < self.valid_from:
            return False, f"未到生效时间（{self.valid_from:%m-%d %H:%M} 起）"
        if self.valid_to and now > self.valid_to:
            return False, f"已过期（{self.valid_to:%m-%d %H:%M} 止）"
        if self.weekdays is not None and now.weekday() not in self.weekdays:
            return False, "今日不在券的适用星期内"
        if self.time_window is not None:
            start, end = self.time_window
            if not (start <= now.time() <= end):
                return False, (f"当前 {now:%H:%M} 不在券的可用时段"
                               f"（{start:%H:%M}–{end:%H:%M}）")
        return True, ""

    def covers(self, code: str) -> bool:
        """该券是否覆盖此商品。空集视为全场。"""
        if not self.product_codes:
            return True
        return code in self.product_codes

    def is_global(self) -> bool:
        return not self.product_codes


# --------------------------------------------------------------------------- #
# 券冲突判定
# --------------------------------------------------------------------------- #

def conflict_reason(a: Coupon, b: Coupon) -> str | None:
    """
    判断两张券能否同时使用。可同时使用返回 None，否则返回冲突原因。

    规则（显式假设，见模块 docstring）：
      1. 两张券都作用在同一个商品上 → 冲突（同一商品不能被两张券优惠两次）
      2. 任一张是全场券，另一张作用于具体商品 → 冲突（全场券已覆盖该商品）
      3. 其余情况视为可叠加
    """
    if a.coupon_id == b.coupon_id:
        return "同一张券不能重复使用"

    a_global, b_global = a.is_global(), b.is_global()

    if a_global and b_global:
        return "两张全场券不可叠加"

    if a_global or b_global:
        specific = b if a_global else a
        # 全场券覆盖所有商品，与针对具体商品的券互斥
        if specific.product_codes:
            return f"全场券「{a.title if a_global else b.title}」已覆盖，不可叠加"

    overlap = a.product_codes & b.product_codes
    if overlap:
        names = "、".join(sorted(overlap))
        return f"两张券都作用于同一商品（{names}）"

    return None


def can_stack(coupons: Sequence[Coupon]) -> tuple[bool, str]:
    """一组券是否两两兼容。"""
    for i in range(len(coupons)):
        for j in range(i + 1, len(coupons)):
            reason = conflict_reason(coupons[i], coupons[j])
            if reason:
                return False, reason
    return True, ""


# --------------------------------------------------------------------------- #
# 计价结果
# --------------------------------------------------------------------------- #

@dataclass
class BasketLine:
    """一行结算明细。"""

    code: str
    name: str
    qty: int
    list_price: float          # 划线原价（不打折、不用券时的等价消费）
    paid_price: float          # 实际结算单价
    coupon_title: str | None = None

    @property
    def list_subtotal(self) -> float:
        return round(self.list_price * self.qty, 2)

    @property
    def paid_subtotal(self) -> float:
        return round(self.paid_price * self.qty, 2)


@dataclass
class Quote:
    """一次报价的完整结果。"""

    lines: list[BasketLine] = field(default_factory=list)
    applied_coupons: list[str] = field(default_factory=list)
    list_total: float = 0.0
    paid_total: float = 0.0
    order_discount: float = 0.0     # 满减/折扣带来的额外减免
    notes: list[str] = field(default_factory=list)

    @property
    def saving(self) -> float:
        return round(self.list_total - self.paid_total, 2)

    @property
    def saving_rate(self) -> float:
        if self.list_total <= 0:
            return 0.0
        return self.saving / self.list_total

    def summary(self) -> str:
        parts = [f"{ln.name}×{ln.qty}" for ln in self.lines]
        body = " + ".join(parts)
        head = f"实付 ¥{self.paid_total:.2f}（原价 ¥{self.list_total:.2f}，省 ¥{self.saving:.2f}）"
        return f"{body}\n{head}"


# --------------------------------------------------------------------------- #
# 计价核心
# --------------------------------------------------------------------------- #

def _normalize(items: Sequence[tuple[str, int]]) -> list[tuple[str, int]]:
    """合并同编码的行，保持首次出现顺序。"""
    order: list[str] = []
    counts: dict[str, int] = {}
    for code, qty in items:
        if qty <= 0:
            continue
        if code not in counts:
            counts[code] = 0
            order.append(code)
        counts[code] += qty
    return [(c, counts[c]) for c in order]


def price_basket(
    items: Sequence[tuple[str, int]],
    menu: dict[str, MenuItem],
    coupons: Sequence[Coupon] = (),
    now: datetime | None = None,
    scope: str = "dine_in",
    stack_policy: str = DEFAULT_STACK_POLICY,
) -> Quote:
    """
    计算菜篮的实付金额。

    items: [(productCode, 数量), ...]
    menu:  productCode -> MenuItem
    coupons: 候选券（会自动剔除时间不可用、场景不适用的）
    scope: "dine_in" 或 "delivery"
    """
    now = now or datetime.now()
    quote = Quote()
    normalized = _normalize(items)

    # 1) 过滤不可用券
    usable: list[Coupon] = []
    for cp in coupons:
        ok, reason = cp.is_time_valid(now)
        if not ok:
            quote.notes.append(f"券「{cp.title}」不可用：{reason}")
            continue
        if scope not in cp.scopes:
            label = "到店" if scope == "dine_in" else "外送"
            quote.notes.append(f"券「{cp.title}」不适用于{label}场景")
            continue
        usable.append(cp)

    # 2) 为每行挑选最省的可用券
    chosen_for_line: dict[str, Coupon] = {}
    for code, _qty in normalized:
        if code not in menu:
            quote.notes.append(f"菜单中未找到商品编码 {code}，已按 0 元计入")
            continue
        base = menu[code]
        candidates = [c for c in usable
                      if c.kind == "special" and c.covers(code)
                      and c.coupon_price is not None
                      and c.coupon_price <= base.price]
        if candidates:
            chosen_for_line[code] = min(candidates, key=lambda c: c.coupon_price)

    # 3) 叠加策略裁决
    if stack_policy == STACK_SINGLE and len(chosen_for_line) > 1:
        # 只保留节省最多的一张
        def _line_saving(c: Coupon) -> float:
            code = next(k for k, v in chosen_for_line.items() if v is c)
            return menu[code].price - c.coupon_price
        keep = max(chosen_for_line.values(), key=lambda c: _line_saving(c))
        dropped = [c for c in chosen_for_line.values() if c is not keep]
        chosen_for_line = {k: v for k, v in chosen_for_line.items() if v is keep}
        for c in dropped:
            quote.notes.append(
                f"券「{c.title}」未使用：当前策略为一单一张券，已保留节省更多的一张")

    elif stack_policy == STACK_GREEDY and chosen_for_line:
        # 校验两两兼容
        picked = list(chosen_for_line.values())
        ok, reason = can_stack(picked)
        if not ok:
            # 退回单券
            def _line_saving2(c: Coupon) -> float:
                code = next(k for k, v in chosen_for_line.items() if v is c)
                return menu[code].price - c.coupon_price
            keep = max(picked, key=lambda c: _line_saving2(c))
            chosen_for_line = {k: v for k, v in chosen_for_line.items() if v is keep}
            quote.notes.append(f"券组合冲突（{reason}），已退回单券结算")

    # 4) 生成明细行
    for code, qty in normalized:
        if code not in menu:
            continue
        item = menu[code]
        cp = chosen_for_line.get(code)
        paid = cp.coupon_price if cp else item.price
        quote.lines.append(BasketLine(
            code=code,
            name=item.name,
            qty=qty,
            # 划线原价作为对照基准：这样「买一送一」「三件套」这类
            # 本身已含优惠的 SKU 才能正确体现节省额
            list_price=item.original_price if item.original_price > 0 else item.price,
            paid_price=paid,
            coupon_title=cp.title if cp else None,
        ))
        if cp:
            quote.applied_coupons.append(cp.title)

    quote.list_total = round(sum(ln.list_subtotal for ln in quote.lines), 2)
    subtotal = sum(ln.paid_subtotal for ln in quote.lines)

    # 5) 全场券（满减 / 折扣）
    for cp in usable:
        if cp.kind == "threshold" and cp.is_global() and cp.threshold is not None:
            if subtotal >= cp.threshold and (cp.discount_amount or 0) > 0:
                quote.order_discount += cp.discount_amount
                quote.applied_coupons.append(cp.title)
        elif cp.kind == "discount" and cp.is_global() and cp.discount_rate is not None:
            quote.order_discount += subtotal * (1 - cp.discount_rate)
            quote.applied_coupons.append(cp.title)

    quote.order_discount = round(quote.order_discount, 2)
    quote.paid_total = round(max(subtotal - quote.order_discount, 0.0), 2)
    return quote


def best_single_coupon(
    items: Sequence[tuple[str, int]],
    menu: dict[str, MenuItem],
    coupons: Sequence[Coupon],
    now: datetime | None = None,
    scope: str = "dine_in",
) -> tuple[Quote, Coupon | None]:
    """逐张券试算，返回最省的一张及其报价。"""
    best: tuple[Quote, Coupon | None] | None = None
    for cp in coupons:
        q = price_basket(items, menu, [cp], now=now, scope=scope,
                         stack_policy=STACK_GREEDY)
        if best is None or q.paid_total < best[0].paid_total:
            best = (q, cp)
    if best is None:
        return price_basket(items, menu, (), now=now, scope=scope), None
    return best


# --------------------------------------------------------------------------- #
# 数据加载
# --------------------------------------------------------------------------- #

import json
from pathlib import Path

MENU_PATH = (Path(__file__).resolve().parent.parent.parent
             / "data" / "menu_mcd.json")


def load_menu(path: Path | str | None = None) -> dict[str, MenuItem]:
    """加载门店菜单，返回 productCode -> MenuItem。"""
    target = Path(path) if path else MENU_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    out: dict[str, MenuItem] = {}
    for row in raw["items"]:
        out[row["code"]] = MenuItem(
            code=row["code"],
            name=row["name"],
            price=float(row["price"]),
            original_price=float(row["original_price"]),
            category=row.get("category", "other"),
        )
    return out


def menu_items_by_category(menu: dict[str, MenuItem],
                           category: str) -> list[MenuItem]:
    """按类别取菜单项，按价格升序。"""
    return sorted((m for m in menu.values() if m.category == category),
                  key=lambda m: m.price)


COUPON_PATH = (Path(__file__).resolve().parent.parent.parent
               / "data" / "coupons_mcd.json")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间：{value}")


def _parse_time(value: str) -> dtime:
    hh, mm = value.split(":")[:2]
    return dtime(int(hh), int(mm))


def load_coupons(path: Path | str | None = None) -> list[Coupon]:
    """加载优惠券样例数据。"""
    target = Path(path) if path else COUPON_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    out: list[Coupon] = []
    for row in raw["coupons"]:
        tw = row.get("time_window")
        out.append(Coupon(
            coupon_id=row["coupon_id"],
            title=row["title"],
            kind=row["kind"],
            product_codes=frozenset(row.get("product_codes", [])),
            coupon_price=(float(row["coupon_price"])
                          if row.get("coupon_price") is not None else None),
            threshold=(float(row["threshold"])
                       if row.get("threshold") is not None else None),
            discount_amount=(float(row["discount_amount"])
                             if row.get("discount_amount") is not None else None),
            discount_rate=(float(row["discount_rate"])
                           if row.get("discount_rate") is not None else None),
            valid_from=_parse_dt(row.get("valid_from")),
            valid_to=_parse_dt(row.get("valid_to")),
            weekdays=(frozenset(row["weekdays"])
                      if row.get("weekdays") is not None else None),
            time_window=(_parse_time(tw[0]), _parse_time(tw[1])) if tw else None,
            scopes=frozenset(row.get("scopes", ["dine_in", "delivery"])),
        ))
    return out