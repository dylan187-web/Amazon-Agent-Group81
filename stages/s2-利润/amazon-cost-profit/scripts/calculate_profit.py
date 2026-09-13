#!/usr/bin/env python3
"""Calculate estimated or actual Amazon US profitability from canonical CSV files."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")
ZERO = Decimal("0")

ESTIMATE_REQUIRED = (
    "sku", "fulfillment_channel", "currency", "fx_cny_per_usd", "sales_price_usd",
    "buyer_shipping_usd", "promo_discount_usd", "referral_fee_rate", "referral_fee_min_usd",
    "per_item_fee_usd", "product_cost_cny", "packaging_cost_cny", "labeling_qc_cost_cny",
    "domestic_freight_cny", "international_freight_cny", "duty_cny", "inbound_placement_usd",
    "fba_fulfillment_usd", "fba_storage_usd", "fbm_warehouse_usd", "fbm_pick_pack_usd",
    "fbm_last_mile_usd", "coupon_fee_usd", "return_loss_per_unit_usd",
    "payment_fee_usd", "fx_fee_usd", "financing_fee_usd", "other_direct_cost_usd",
    "expected_units", "fixed_cost_usd",
)

DIRECT_BUCKETS = {
    "product_cost": {"product_cogs", "packaging", "prep_qc"},
    "logistics": {"domestic_freight", "international_freight", "duty", "inbound_placement"},
    "platform": {"referral_fee", "per_item_fee", "fba_fulfillment", "fba_storage", "fbm_warehouse", "fbm_pick_pack", "fbm_last_mile", "other_platform_fee"},
    "ads": {"ads", "coupon_fee", "promo_service_fee"},
    "after_sales": {"return_processing", "damage_loss", "removal_disposal", "compensation"},
    "finance": {"payment_fee", "fx_fee", "financing_fee"},
    "other_direct": {"other_direct"},
}
REVENUE_CATEGORIES = {"product_revenue", "buyer_shipping"}
DEDUCTION_CATEGORIES = {"promotion_discount", "refund"}
VALID_CHANNELS = {"FBA", "FBM"}
VALID_CATEGORIES = REVENUE_CATEGORIES | DEDUCTION_CATEGORIES | {"marketplace_tax", "fixed_cost"} | set().union(*DIRECT_BUCKETS.values())


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def number(raw: str, field: str, row_no: int, issues: list[str], *, required: bool = True) -> Decimal | None:
    value = (raw or "").strip()
    if not value:
        if required:
            issues.append(f"第 {row_no} 行缺少 {field}；请明确填数值或 0。")
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        issues.append(f"第 {row_no} 行 {field} 不是有效数字：{value}。")
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def load_ad_performance(path: Path, issues: list[str]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Convert ad performance to canonical expense rows and retain efficiency inputs."""
    canonical, metrics = [], []
    for row_no, raw in enumerate(read_csv(path), start=2):
        required = ("month", "date", "sku", "fulfillment_channel", "ad_spend_usd", "attributed_orders", "attributed_sales_usd", "source", "source_reference")
        if any(not (raw.get(field) or "").strip() for field in required):
            issues.append(f"广告表第 {row_no} 行缺少必填字段，未导入。")
            continue
        spend = number(raw.get("ad_spend_usd", ""), "ad_spend_usd", row_no, issues)
        orders = number(raw.get("attributed_orders", ""), "attributed_orders", row_no, issues)
        sales = number(raw.get("attributed_sales_usd", ""), "attributed_sales_usd", row_no, issues)
        if spend is None or orders is None or sales is None or orders <= ZERO:
            issues.append(f"广告表第 {row_no} 行归因订单必须大于 0，未导入。")
            continue
        canonical.append({"month": raw["month"], "date": raw["date"], "record_type": "actual", "sku": raw["sku"], "fulfillment_channel": raw["fulfillment_channel"], "currency": "USD", "amount_usd": str(spend), "units": "", "category": "ads", "source": raw["source"], "source_reference": raw["source_reference"], "estimated_amount_usd": ""})
        metrics.append(raw)
    return canonical, metrics


def write_ad_efficiency(metrics: list[dict[str, str]], results: list[dict[str, str]], output: Path) -> None:
    sales_by_key = {(r.get("month"), r.get("sku"), r.get("fulfillment_channel")): Decimal(r.get("net_sales", "0") or "0") for r in results}
    rows = []
    for raw in metrics:
        spend, orders, attributed_sales = Decimal(raw["ad_spend_usd"]), Decimal(raw["attributed_orders"]), Decimal(raw["attributed_sales_usd"])
        key = (raw["month"], raw["sku"], raw["fulfillment_channel"].upper())
        net_sales = sales_by_key.get(key, ZERO)
        rows.append({"month": key[0], "sku": key[1], "fulfillment_channel": key[2], "ad_spend_usd": money(spend), "attributed_orders": str(orders), "attributed_sales_usd": money(attributed_sales), "cost_per_attributed_order": money(spend / orders), "acos": money(spend / attributed_sales) if attributed_sales > ZERO else "", "tacos": money(spend / net_sales) if net_sales > ZERO else "", "source": raw["source"], "source_reference": raw["source_reference"]})
    write_csv(output / "ad_efficiency.csv", ["month", "sku", "fulfillment_channel", "ad_spend_usd", "attributed_orders", "attributed_sales_usd", "cost_per_attributed_order", "acos", "tacos", "source", "source_reference"], rows)


def write_source_reconciliation(rows: list[dict[str, str]], manifest_path: Path, output: Path, issues: list[str]) -> None:
    mapped = defaultdict(Decimal)
    for raw in rows:
        amount = number(raw.get("amount_usd", ""), "amount_usd", 0, issues, required=False)
        if amount is not None:
            mapped[(raw.get("month", "").strip(), raw.get("source", "").strip(), raw.get("source_reference", "").strip())] += amount
    expected = {}
    for row_no, raw in enumerate(read_csv(manifest_path), start=2):
        key = (raw.get("month", "").strip(), raw.get("source", "").strip(), raw.get("source_reference", "").strip())
        amount = number(raw.get("expected_mapped_total_usd", ""), "expected_mapped_total_usd", row_no, issues)
        if not all(key) or amount is None:
            issues.append(f"来源清单第 {row_no} 行缺少匹配键或金额，未对账。")
            continue
        expected[key] = amount
    output_rows = []
    for key in sorted(set(mapped) | set(expected)):
        actual, target = mapped.get(key, ZERO), expected.get(key)
        status = "matched" if target is not None and actual == target else "unmatched"
        if status == "unmatched":
            issues.append(f"来源对账不一致：{key[1]}／{key[2]}。")
        output_rows.append({"month": key[0], "source": key[1], "source_reference": key[2], "expected_mapped_total_usd": money(target) if target is not None else "", "mapped_total_usd": money(actual), "difference_usd": money(actual - target) if target is not None else "", "status": status})
    write_csv(output / "source_reconciliation.csv", ["month", "source", "source_reference", "expected_mapped_total_usd", "mapped_total_usd", "difference_usd", "status"], output_rows)


def apply_inventory_batches(rows: list[dict[str, str]], batches_path: Path, output: Path, issues: list[str]) -> list[dict[str, str]]:
    """Generate moving-weighted-average COGS for sales lacking explicit product COGS."""
    existing_cogs = {raw.get("sku", "").strip() for raw in rows if raw.get("category") in {"product_cogs", "packaging", "prep_qc"} and raw.get("sku", "").strip()}
    events = defaultdict(list)
    for row_no, raw in enumerate(read_csv(batches_path), start=2):
        sku, date = raw.get("sku", "").strip(), raw.get("received_date", "").strip()
        qty = number(raw.get("units_received", ""), "units_received", row_no, issues)
        costs = [number(raw.get(field, ""), field, row_no, issues) for field in ("total_product_cost_usd", "total_packaging_cost_usd", "total_prep_qc_cost_usd")]
        if not sku or not date or qty is None or any(cost is None for cost in costs) or qty <= ZERO:
            issues.append(f"批次表第 {row_no} 行不完整或数量无效，未导入。")
            continue
        events[sku].append((date, 0, "batch", qty, costs, raw.get("batch_id", "").strip()))
    for raw in rows:
        if raw.get("category") != "product_revenue" or not raw.get("sku", "").strip() or raw.get("sku", "").strip() in existing_cogs:
            continue
        qty = number(raw.get("units", ""), "units", 0, issues)
        if qty is None or qty <= ZERO:
            issues.append(f"SKU {raw.get('sku', '')} 的销售收入行缺少 units，无法用批次成本结转。")
            continue
        events[raw["sku"].strip()].append((raw.get("date", "").strip(), 1, "sale", qty, raw, ""))
    generated = []
    for sku, sku_events in events.items():
        stock_units, stock_costs = ZERO, [ZERO, ZERO, ZERO]
        for date, _, event_type, qty, payload, batch_id in sorted(sku_events, key=lambda item: (item[0], item[1])):
            if event_type == "batch":
                stock_units += qty
                stock_costs = [left + right for left, right in zip(stock_costs, payload)]
                continue
            if stock_units < qty:
                issues.append(f"SKU {sku} 在 {date} 可用批次库存不足，未生成销售成本。")
                continue
            average = [cost / stock_units for cost in stock_costs]
            sale_costs = [unit_cost * qty for unit_cost in average]
            stock_units -= qty
            stock_costs = [cost - sale_cost for cost, sale_cost in zip(stock_costs, sale_costs)]
            sale = payload
            for category, amount in zip(("product_cogs", "packaging", "prep_qc"), sale_costs):
                if amount:
                    generated.append({"month": sale["month"], "date": sale["date"], "record_type": "generated", "sku": sku, "fulfillment_channel": sale.get("fulfillment_channel", ""), "currency": "USD", "amount_usd": str(amount), "units": str(qty), "category": category, "source": "Inventory batch allocation", "source_reference": f"moving-average to {date}", "estimated_amount_usd": ""})
    if generated:
        write_csv(output / "inventory_cogs_generated.csv", list(generated[0].keys()), generated)
    return rows + generated


def solve_price(base_cost: Decimal, rate: Decimal, minimum: Decimal, target_margin: Decimal) -> Decimal | None:
    """Find the lowest price with referral fee max(price*rate, minimum)."""
    if target_margin >= Decimal("1"):
        return None
    candidates = []
    denominator = Decimal("1") - rate - target_margin
    if denominator > ZERO:
        candidates.append((base_cost / denominator).quantize(CENT, rounding=ROUND_CEILING))
    if Decimal("1") - target_margin > ZERO:
        candidates.append(((base_cost + minimum) / (Decimal("1") - target_margin)).quantize(CENT, rounding=ROUND_CEILING))
    valid = []
    for candidate in candidates:
        referral = max(candidate * rate, minimum)
        profit = candidate - referral - base_cost
        if candidate > ZERO and profit / candidate >= target_margin:
            valid.append(candidate)
    return min(valid) if valid else None


def estimate(rows: list[dict[str, str]], output: Path) -> tuple[list[dict[str, str]], list[str]]:
    results, issues = [], []
    for row_no, raw in enumerate(rows, start=2):
        missing = [field for field in ESTIMATE_REQUIRED if not (raw.get(field) or "").strip()]
        sku, channel = (raw.get("sku") or "").strip(), (raw.get("fulfillment_channel") or "").strip().upper()
        if missing:
            issues.append(f"第 {row_no} 行 SKU {sku or '未填写'} 缺少字段：{'、'.join(missing)}。")
            continue
        if channel not in VALID_CHANNELS:
            issues.append(f"第 {row_no} 行 SKU {sku} 的 fulfillment_channel 必须为 FBA 或 FBM。")
            continue
        values = {field: number(raw.get(field, ""), field, row_no, issues) for field in ESTIMATE_REQUIRED if field not in {"sku", "fulfillment_channel", "currency"}}
        if any(value is None for value in values.values()):
            continue
        ad_per_unit = number(raw.get("ads_per_unit_usd", ""), "ads_per_unit_usd", row_no, issues, required=False)
        ad_spend = number(raw.get("ad_spend_usd", ""), "ad_spend_usd", row_no, issues, required=False)
        attributed_orders = number(raw.get("ad_attributed_orders", ""), "ad_attributed_orders", row_no, issues, required=False)
        if ad_per_unit is None and ad_spend is not None and attributed_orders is not None:
            if attributed_orders <= ZERO:
                issues.append(f"第 {row_no} 行 SKU {sku} 的 ad_attributed_orders 必须大于 0。")
                continue
            ad_per_unit = ad_spend / attributed_orders
        if ad_per_unit is None:
            issues.append(f"第 {row_no} 行 SKU {sku} 缺少广告单件成本，或 ad_spend_usd 与 ad_attributed_orders。")
            continue
        values["ads_per_unit_usd"] = ad_per_unit
        if values["fx_cny_per_usd"] <= ZERO or values["expected_units"] <= ZERO:
            issues.append(f"第 {row_no} 行 SKU {sku} 的汇率和预计销量必须大于 0。")
            continue
        if not (raw.get("currency") or "").strip().upper() == "USD":
            issues.append(f"第 {row_no} 行 SKU {sku} 的输出币种必须为 USD。")
            continue
        cny_cost = sum(values[f] for f in ("product_cost_cny", "packaging_cost_cny", "labeling_qc_cost_cny", "domestic_freight_cny", "international_freight_cny", "duty_cny")) / values["fx_cny_per_usd"]
        referral_base = values["sales_price_usd"] + values["buyer_shipping_usd"]
        referral = max(referral_base * values["referral_fee_rate"], values["referral_fee_min_usd"])
        fba = values["fba_fulfillment_usd"] + values["fba_storage_usd"] if channel == "FBA" else ZERO
        fbm = values["fbm_warehouse_usd"] + values["fbm_pick_pack_usd"] + values["fbm_last_mile_usd"] if channel == "FBM" else ZERO
        net_sales = referral_base - values["promo_discount_usd"]
        product = (values["product_cost_cny"] + values["packaging_cost_cny"] + values["labeling_qc_cost_cny"]) / values["fx_cny_per_usd"]
        logistics = (values["domestic_freight_cny"] + values["international_freight_cny"] + values["duty_cny"]) / values["fx_cny_per_usd"] + values["inbound_placement_usd"]
        platform = referral + values["per_item_fee_usd"] + fba + fbm
        after_sales = values["return_loss_per_unit_usd"]
        finance = values["payment_fee_usd"] + values["fx_fee_usd"] + values["financing_fee_usd"]
        pre_ads = net_sales - product - logistics - platform - after_sales - finance - values["other_direct_cost_usd"]
        post_ads = pre_ads - values["ads_per_unit_usd"] - values["coupon_fee_usd"]
        fixed_per_unit = values["fixed_cost_usd"] / values["expected_units"]
        operating = post_ads - fixed_per_unit
        baseline_cost = product + logistics + values["per_item_fee_usd"] + fba + fbm + after_sales + finance + values["other_direct_cost_usd"] + values["ads_per_unit_usd"] + values["coupon_fee_usd"] + fixed_per_unit - values["buyer_shipping_usd"] + values["promo_discount_usd"]
        breakeven = solve_price(baseline_cost, values["referral_fee_rate"], values["referral_fee_min_usd"], ZERO)
        target_raw = number(raw.get("target_profit_margin", ""), "target_profit_margin", row_no, issues, required=False)
        target_price = solve_price(baseline_cost, values["referral_fee_rate"], values["referral_fee_min_usd"], target_raw) if target_raw is not None else None
        ads_cap = pre_ads
        stress_price = values["sales_price_usd"] * Decimal("0.90")
        stress_referral = max((stress_price + values["buyer_shipping_usd"]) * values["referral_fee_rate"], values["referral_fee_min_usd"])
        stress_post_ads = (stress_price + values["buyer_shipping_usd"] - values["promo_discount_usd"] - product - logistics - (platform - referral + stress_referral) - after_sales - finance - values["other_direct_cost_usd"] - values["ads_per_unit_usd"] * Decimal("1.20") - values["coupon_fee_usd"])
        coverage = []
        for label, field in (("广告", "ads_cost_status"), ("仓储", "storage_cost_status"), ("固定费用", "fixed_cost_status")):
            status = (raw.get(field) or "unknown").strip().lower()
            if status not in {"included", "excluded"}:
                coverage.append(label)
            elif status == "excluded":
                coverage.append(label)
        results.append({
            "sku": sku, "fulfillment_channel": channel, "currency": "USD", "net_sales_per_unit": money(net_sales), "product_cost": money(product), "logistics_cost": money(logistics), "platform_cost": money(platform), "ads_cost": money(values["ads_per_unit_usd"] + values["coupon_fee_usd"]), "after_sales_cost": money(after_sales), "finance_cost": money(finance), "other_direct_cost": money(values["other_direct_cost_usd"]), "pre_ads_contribution": money(pre_ads), "post_ads_contribution": money(post_ads), "fixed_cost_per_unit": money(fixed_per_unit), "operating_profit_per_unit": money(operating), "operating_margin": money(operating / net_sales) if net_sales else "", "expected_operating_profit": money(operating * values["expected_units"]), "breakeven_price": money(breakeven) if breakeven is not None else "", "target_margin_price": money(target_price) if target_price is not None else "", "max_ad_spend_per_unit": money(ads_cap), "stress_post_ads_profit_per_unit": money(stress_post_ads), "referral_fee_source": (raw.get("referral_fee_source") or "").strip(), "referral_fee_effective_date": (raw.get("referral_fee_effective_date") or "").strip(), "fba_fee_source": (raw.get("fba_fee_source") or "").strip(), "fba_fee_effective_date": (raw.get("fba_fee_effective_date") or "").strip(), "coverage_status": "partial" if coverage else "complete", "uncovered_items": "、".join(coverage), "cost_basis": "estimate",
        })
    write_csv(output / "estimated_profitability.csv", list(results[0].keys()) if results else ["sku"], results)
    return results, issues


def actual(rows: list[dict[str, str]], output: Path) -> tuple[list[dict[str, str]], list[str]]:
    issues, groups, unallocated, estimated, actual_by_category = [], defaultdict(lambda: defaultdict(Decimal)), defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
    required = ("month", "date", "record_type", "currency", "amount_usd", "category", "source", "source_reference")
    for row_no, raw in enumerate(rows, start=2):
        category, sku = (raw.get("category") or "").strip(), (raw.get("sku") or "").strip()
        if any(not (raw.get(field) or "").strip() for field in required if field != "sku"):
            issues.append(f"第 {row_no} 行存在必填字段为空，无法核算。")
            continue
        amount = number(raw.get("amount_usd", ""), "amount_usd", row_no, issues)
        if amount is None:
            continue
        if (raw.get("currency") or "").strip().upper() != "USD":
            issues.append(f"第 {row_no} 行只接受 USD 标准表；请先换算。")
            continue
        channel = (raw.get("fulfillment_channel") or "").strip().upper()
        if channel and channel not in VALID_CHANNELS:
            issues.append(f"第 {row_no} 行 fulfillment_channel 必须为 FBA、FBM 或留空。")
            continue
        month = (raw.get("month") or "").strip()
        key = (month, sku, channel or "未标配送方式")
        estimate_value = number(raw.get("estimated_amount_usd", ""), "estimated_amount_usd", row_no, issues, required=False)
        if category not in VALID_CATEGORIES:
            issues.append(f"第 {row_no} 行类别 {category} 未定义，未计入利润。")
            continue
        if not sku:
            actual_by_category[((month, "STORE_UNALLOCATED", ""), category)] += amount
            unallocated[(month, category)] += amount
            if estimate_value is not None:
                estimated[((month, "STORE_UNALLOCATED", ""), category)] += estimate_value
            continue
        actual_by_category[(key, category)] += amount
        if category in REVENUE_CATEGORIES:
            groups[key]["net_sales"] += amount
        elif category in DEDUCTION_CATEGORIES:
            groups[key]["net_sales"] -= amount
        elif category == "marketplace_tax":
            groups[key]["marketplace_tax"] += amount
        elif category == "fixed_cost":
            groups[key]["fixed_direct"] += amount
        else:
            bucket = next((name for name, codes in DIRECT_BUCKETS.items() if category in codes), None)
            groups[key][bucket] += -amount if category == "compensation" else amount
        if estimate_value is not None:
            estimated[(key, category)] += estimate_value
    months = {key[0] for key in groups} | {key[0] for key in unallocated}
    for month in months:
        shared_fixed = unallocated[(month, "fixed_cost")]
        positive_sales = sum(values["net_sales"] for key, values in groups.items() if key[0] == month and values["net_sales"] > ZERO)
        for key, values in groups.items():
            if key[0] == month and positive_sales > ZERO and values["net_sales"] > ZERO:
                values["fixed_allocated"] = shared_fixed * values["net_sales"] / positive_sales
        unallocated.pop((month, "fixed_cost"), None)
    results = []
    for key in sorted(groups):
        values = groups[key]
        direct_cost = sum(values[bucket] for bucket in DIRECT_BUCKETS)
        pre_ads = values["net_sales"] - direct_cost + values["ads"]
        post_ads = values["net_sales"] - direct_cost
        operating = post_ads - values["fixed_direct"] - values["fixed_allocated"]
        results.append({"month": key[0], "sku": key[1], "fulfillment_channel": key[2], "currency": "USD", "net_sales": money(values["net_sales"]), "marketplace_tax": money(values["marketplace_tax"]), "product_cost": money(values["product_cost"]), "logistics_cost": money(values["logistics"]), "platform_cost": money(values["platform"]), "ads_cost": money(values["ads"]), "after_sales_cost": money(values["after_sales"]), "finance_cost": money(values["finance"]), "other_direct_cost": money(values["other_direct"]), "pre_ads_contribution": money(pre_ads), "post_ads_contribution": money(post_ads), "fixed_direct": money(values["fixed_direct"]), "fixed_allocated": money(values["fixed_allocated"]), "operating_profit": money(operating), "operating_margin": money(operating / values["net_sales"]) if values["net_sales"] else "", "cost_basis": "actual"})
    for (month, category), amount in sorted(unallocated.items()):
        if amount:
            bucket = next((name for name, codes in DIRECT_BUCKETS.items() if category in codes), "")
            net_sales = amount if category in REVENUE_CATEGORIES else -amount if category in DEDUCTION_CATEGORIES else ZERO
            effective_cost = -amount if category == "compensation" else amount
            direct_cost = effective_cost if bucket else ZERO
            results.append({"month": month, "sku": "STORE_UNALLOCATED", "fulfillment_channel": "", "currency": "USD", "net_sales": money(net_sales), "marketplace_tax": money(amount) if category == "marketplace_tax" else "0.00", "product_cost": money(effective_cost) if bucket == "product_cost" else "0.00", "logistics_cost": money(effective_cost) if bucket == "logistics" else "0.00", "platform_cost": money(effective_cost) if bucket == "platform" else "0.00", "ads_cost": money(effective_cost) if bucket == "ads" else "0.00", "after_sales_cost": money(effective_cost) if bucket == "after_sales" else "0.00", "finance_cost": money(effective_cost) if bucket == "finance" else "0.00", "other_direct_cost": money(effective_cost) if bucket == "other_direct" else "0.00", "pre_ads_contribution": "", "post_ads_contribution": "", "fixed_direct": "0.00", "fixed_allocated": "0.00", "operating_profit": money(net_sales - direct_cost), "operating_margin": "", "cost_basis": f"actual:{category}"})
    write_csv(output / "monthly_profitability.csv", list(results[0].keys()) if results else ["month"], results)
    variance_rows = []
    for (key, category), estimate_amount in sorted(estimated.items()):
        actual_amount = actual_by_category[(key, category)]
        variance_rows.append({"month": key[0], "sku": key[1], "fulfillment_channel": key[2], "category": category, "estimated_amount_usd": money(estimate_amount), "actual_amount_usd": money(actual_amount), "actual_minus_estimate_usd": money(actual_amount - estimate_amount)})
    write_csv(output / "monthly_variance.csv", ["month", "sku", "fulfillment_channel", "category", "estimated_amount_usd", "actual_amount_usd", "actual_minus_estimate_usd"], variance_rows)
    return results, issues


def report(mode: str, results: list[dict[str, str]], issues: list[str], output: Path) -> None:
    profit = sum((Decimal(row.get("operating_profit", row.get("expected_operating_profit", "0")) or "0") for row in results), ZERO)
    losses = [row.get("sku", "") for row in results if row.get("sku") != "STORE_UNALLOCATED" and Decimal(row.get("operating_profit", row.get("expected_operating_profit", "0")) or "0") < ZERO]
    lines = [f"# 亚马逊成本利润核算报告（{ '上架前测算' if mode == 'estimate' else '月度实际核算'}）", "", "- 币种：USD。利润为所得税前管理口径。", f"- 已核算行数：{len(results)}。", f"- 汇总经营利润：${money(profit)}。", f"- 亏损 SKU：{'、'.join(losses) if losses else '无'}。", "", "## 数据质量与异常", ""]
    lines.extend([f"- {issue}" for issue in issues] or ["- 未发现格式或分类异常。"])
    if mode == "estimate":
        partial = [f"{row['sku']}：{row['uncovered_items']}" for row in results if row.get("coverage_status") == "partial"]
        if partial:
            lines.extend(["", "## 未覆盖费用", "", *[f"- {item}" for item in partial]])
    if mode == "actual":
        lines.extend(["", "## 口径", "", "- 按平台入账月份及广告发生月份核算；跨月退款按发生月计入。", "- 结算打款不等同利润，未作为收入或成本计入。", "- 共享固定费用仅按正净销售收入分摊；无 SKU 费用保留为 STORE_UNALLOCATED。"])
    (output / f"{mode}_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("estimate", "actual"))
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("profit-output"))
    parser.add_argument("--ad-performance", type=Path, help="广告花费与归因订单标准表，仅 actual 模式使用")
    parser.add_argument("--source-manifest", type=Path, help="来源映射总额清单，仅 actual 模式使用")
    parser.add_argument("--inventory-batches", type=Path, help="采购批次成本表，仅 actual 模式使用")
    parser.add_argument("--unmapped-rows", type=Path, help="导入器输出的未映射行；非空时利润报告不可定稿")
    args = parser.parse_args()
    if not args.input_csv.is_file():
        print(f"输入文件不存在：{args.input_csv}", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_csv(args.input_csv)
    pre_issues = []
    ad_metrics = []
    if args.mode == "actual" and args.ad_performance:
        if not args.ad_performance.is_file():
            print(f"广告文件不存在：{args.ad_performance}", file=sys.stderr)
            return 2
        ad_rows, ad_metrics = load_ad_performance(args.ad_performance, pre_issues)
        rows.extend(ad_rows)
    if args.mode == "actual" and args.inventory_batches:
        if not args.inventory_batches.is_file():
            print(f"批次成本表不存在：{args.inventory_batches}", file=sys.stderr)
            return 2
        rows = apply_inventory_batches(rows, args.inventory_batches, args.output_dir, pre_issues)
    if args.mode == "actual" and args.unmapped_rows:
        if not args.unmapped_rows.is_file():
            print(f"未映射行文件不存在：{args.unmapped_rows}", file=sys.stderr)
            return 2
        unmapped_count = len(read_csv(args.unmapped_rows))
        if unmapped_count:
            pre_issues.append(f"原始报表仍有 {unmapped_count} 条未映射费用；当前利润结果不能定稿。")
    results, issues = estimate(rows, args.output_dir) if args.mode == "estimate" else actual(rows, args.output_dir)
    issues = pre_issues + issues
    if args.mode == "actual":
        if ad_metrics:
            write_ad_efficiency(ad_metrics, results, args.output_dir)
        if args.source_manifest:
            if not args.source_manifest.is_file():
                print(f"来源清单不存在：{args.source_manifest}", file=sys.stderr)
                return 2
            write_source_reconciliation(rows, args.source_manifest, args.output_dir, issues)
    report(args.mode, results, issues, args.output_dir)
    print(f"已写入 {args.output_dir}；核算行数 {len(results)}，异常 {len(issues)} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
