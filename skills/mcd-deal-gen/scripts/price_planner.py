#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳带券价格试算器

用途：给定门店、餐品、用券，批量调用 calculate-price 逻辑前先做本地预筛，
      避免为不可能成交的组合浪费接口调用。

本脚本不直接发起 MCP 调用（沙箱内无法访问 MCP），
而是输出「试算任务清单」，供上层Agent 逐条交给 MCP 执行。

用法示例：
    python price_planner.py --store 3450312 --budget 30
    python price_planner.py --store 3450312 --coupon E86377A0349D730EF7C27EBBE7B4C0FE
"""

import argparse
import json
import sys

# 参数传递规则：beType -> (orderType, 是否必传 beCode)
BE_TYPE_RULES = {
    1: (1, False),   # 到店自取
    5: (1, True),    # 得来速
    2: (2, True),    # 麦乐送
    6: (2, True),    # 企业团餐
}

BE_TYPE_NAMES = {
    1: "到店自取",
    5: "得来速",
    2: "麦乐送",
    6: "企业团餐",
}


def build_task(store_code, be_type, items, coupon=None, need_tableware=False,
               reservation_date=None, be_code=None):
    """生成一个 calculate-price 调用任务。"""
    if be_type not in BE_TYPE_RULES:
        raise ValueError(f"beType 必须为 1/5/2/6，收到 {be_type}")

    order_type, need_be_code = BE_TYPE_RULES[be_type]

    task = {
        "tool": "mcp__mcd-mcp__calculate-price",
        "params": {
            "storeCode": store_code,
            "orderType": order_type,
            "beType": be_type,
            "items": items,
            "needTableware": need_tableware,
        },
    }

    if need_be_code:
        if not be_code:
            raise ValueError(f"{BE_TYPE_NAMES[be_type]} 场景必须传 beCode")
        task["params"]["beCode"] = be_code
    elif be_code:
        # 到店自取传 beCode 会报错，必须剔除
        print("[warn] 到店自取场景不传 beCode，已自动移除", file=sys.stderr)

    if coupon:
        task["params"]["items"] = [
            dict(it, couponId=coupon.get("couponId"),
                 couponCode=coupon.get("couponCode"))
            for it in items
        ]

    # 注意：实测显示传 reservationDate 可能导致 query-store-coupons 返回空，
    # 此处仅在用户明确要求预约时透传
    if reservation_date:
        task["params"]["reservationDate"] = reservation_date

    return task


def parse_coupon(raw):
    """解析 coupon 字符串，支持 couponId 或 couponId:couponCode。"""
    if ":" in raw:
        cid, code = raw.split(":", 1)
        return {"couponId": cid.strip(), "couponCode": code.strip()}
    return {"couponId": raw.strip(), "couponCode": None}


def main():
    ap = argparse.ArgumentParser(
        description="生成 calculate-price 试算任务清单")
    ap.add_argument("--store", required=True, help="门店编码 storeCode")
    ap.add_argument("--be-type", required=True, type=int, choices=[1, 2, 5, 6],
                    help="1-到店自取 2-麦乐送 5-得来速 6-团餐")
    ap.add_argument("--item", action="append", required=True,
                    metavar="CODE:QTY",
                    help="餐品，格式 商品编码:数量，可重复")
    ap.add_argument("--coupon", help="券，格式 couponId 或 couponId:couponCode")
    ap.add_argument("--be-code", help="业务编码，得来速/外送/团餐必传")
    ap.add_argument("--budget", type=float, help="预算上限（元），仅作提示")
    ap.add_argument("--tableware", action="store_true", help="需要餐具")
    ap.add_argument("--reservation", help="预约时间 yyyy-MM-dd HH:mm")

    args = ap.parse_args()

    items = []
    for raw in args.item:
        parts = raw.split(":")
        if len(parts) != 2:
            print(f"[error] --item 格式应为 商品编码:数量，收到 {raw}",
                  file=sys.stderr)
            sys.exit(1)
        code, qty = parts[0].strip(), parts[1].strip()
        try:
            qty = int(qty)
        except ValueError:
            print(f"[error] 数量必须是整数：{raw}", file=sys.stderr)
            sys.exit(1)
        if qty < 1:
            print(f"[error] 数量必须 ≥1：{raw}", file=sys.stderr)
            sys.exit(1)
        items.append({"productCode": code, "quantity": qty})

    coupon = parse_coupon(args.coupon) if args.coupon else None

    try:
        task = build_task(
            args.store, args.be_type, items,
            coupon=coupon, need_tableware=args.tableware,
            reservation_date=args.reservation, be_code=args.be_code,
        )
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)

    if args.budget:
        task["params"]["_预算上限_元"] = args.budget
        task["params"]["_提示"] = "试算后需除以100转为元再与预算比较"

    print(json.dumps(task, ensure_ascii=False, indent=2))
    print("\n[note] 金额单位为分，展示时须除以 100。",
          file=sys.stderr)
    print("[note] 本工具仅试算，不会自动下单。", file=sys.stderr)


if __name__ == "__main__":
    main()