#!/usr/bin/env python3
"""Route Amazon US products to the correct fee-calculation path before profit modeling."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path

TIERED_CATEGORIES = {
    "appliances - compact", "baby products", "beauty, health, and personal care",
    "clothing and accessories", "electronics accessories", "fine art", "furniture",
    "grocery and gourmet", "jewelry", "lawn mowers and snow throwers", "watches",
}
SPECIAL_FLAGS = {
    "hazmat", "dangerous_goods", "oversize", "low_price_fba", "awd", "mcf",
    "subscribe_and_save", "vine", "fba_new_selection", "return_restock",
}
VALID_CHANNELS = {"FBA", "FBM"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def flags(raw: str) -> set[str]:
    return {item.strip().lower() for item in (raw or "").replace("|", ";").split(";") if item.strip()}


def gate(raw: dict[str, str], row_no: int, as_of: date, max_fee_age_days: int) -> dict[str, str]:
    sku = (raw.get("sku") or "").strip()
    channel = (raw.get("fulfillment_channel") or "").strip().upper()
    category = (raw.get("amazon_fee_category") or "").strip()
    normalized_category = category.lower()
    problems, requirements, rules = [], [], []
    special = flags(raw.get("special_programs", ""))
    fee_date_text = (raw.get("fba_fee_effective_date") or raw.get("referral_fee_effective_date") or "").strip()
    fee_age_days, fee_freshness = "", "missing"
    if not sku:
        problems.append("缺少 SKU")
    if channel not in VALID_CHANNELS:
        problems.append("fulfillment_channel 必须为 FBA 或 FBM")
    if not category:
        problems.append("缺少 Amazon fee category")
    if not (raw.get("sales_price_usd") or "").strip():
        problems.append("缺少售价")
    is_media = normalized_category.startswith("media") or normalized_category in {"books", "dvd", "music", "software", "video"}
    if normalized_category in TIERED_CATEGORIES:
        rules.append("类目佣金可能按售价区间分段")
        requirements.append("使用当前 Fee Preview／Revenue Calculator，或提供分段佣金结果")
    if is_media:
        rules.append("媒体类需要单独核对 closing fee")
        requirements.append("提供当前媒体 closing fee 与佣金结果")
    if (raw.get("is_bundle") or "").strip().lower() in {"yes", "true", "1"}:
        rules.append("套装需要可售单位 BOM 成本")
        requirements.append("提供套装 BOM 与各组件数量")
    active_special = sorted(special & SPECIAL_FLAGS)
    if active_special:
        rules.append(f"特殊项目：{'、'.join(active_special)}")
        requirements.append("提供该项目的当前服务费或结算实际费用")
    if channel == "FBA":
        dimensional_fields = ("package_length_in", "package_width_in", "package_height_in", "shipping_weight_lb")
        if any(not (raw.get(field) or "").strip() for field in dimensional_fields):
            requirements.append("补齐包装长宽高和发货重量")
        if not (raw.get("fba_fee_source") or "").strip():
            requirements.append("提供当前 Revenue Calculator／Fee Preview 的 FBA 费用来源与生效日期")
        if not fee_date_text:
            requirements.append("提供 FBA 费用生效日期")
        else:
            try:
                fee_age = (as_of - datetime.strptime(fee_date_text, "%Y-%m-%d").date()).days
                fee_age_days = str(fee_age)
                fee_freshness = "current" if 0 <= fee_age <= max_fee_age_days else "stale"
                if fee_freshness == "stale":
                    requirements.append(f"FBA 费用来源已超过 {max_fee_age_days} 天，请更新 Fee Preview／Revenue Calculator")
            except ValueError:
                fee_freshness = "invalid_date"
                requirements.append("FBA 费用生效日期必须为 YYYY-MM-DD")
    if problems:
        status, route = "blocked", "补齐商品档案后再测算"
    elif rules or (channel == "FBA" and requirements):
        status, route = "manual_fee_override_required", "使用 Fee Preview／Revenue Calculator／实际费用，再进入利润测算"
    else:
        status, route = "standard_formula_allowed", "可使用普通利润模板；仍保留费用来源与生效日期"
    return {
        "row": str(row_no), "sku": sku, "fulfillment_channel": channel, "amazon_fee_category": category,
        "status": status, "calculation_route": route, "special_rules": "；".join(rules),
        "required_inputs": "；".join(dict.fromkeys(requirements)), "blocking_issues": "；".join(problems),
        "fee_source": (raw.get("fba_fee_source") or raw.get("referral_fee_source") or "").strip(),
        "fee_effective_date": fee_date_text, "fee_age_days": fee_age_days, "fee_freshness": fee_freshness,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("fee-gate-output"))
    parser.add_argument("--max-fee-age-days", type=int, default=90)
    args = parser.parse_args()
    if not args.input_csv.is_file():
        parser.error(f"输入文件不存在：{args.input_csv}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = [gate(row, row_no, date.today(), args.max_fee_age_days) for row_no, row in enumerate(read_csv(args.input_csv), start=2)]
    columns = list(results[0].keys()) if results else ["sku", "status"]
    write_csv(args.output_dir / "fee_gate.csv", columns, results)
    counts = {status: sum(row["status"] == status for row in results) for status in ("standard_formula_allowed", "manual_fee_override_required", "blocked")}
    lines = ["# 美国站商品费用决策报告", "", *[f"- {key}：{value}" for key, value in counts.items()], "", "## 需人工费用覆盖的 SKU", ""]
    manual = [row for row in results if row["status"] != "standard_formula_allowed"]
    lines.extend([f"- {row['sku'] or '未填写 SKU'}：{row['calculation_route']}。{row['required_inputs'] or row['blocking_issues']}" for row in manual] or ["- 无。"])
    (args.output_dir / "fee_gate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {args.output_dir}；普通公式 {counts['standard_formula_allowed']} 项，人工费用覆盖 {counts['manual_fee_override_required']} 项，阻塞 {counts['blocked']} 项。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
