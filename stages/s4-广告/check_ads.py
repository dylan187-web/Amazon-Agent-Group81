#!/usr/bin/env python3
"""S4 结构校验与 Markdown 渲染。标准库；不判断广告策略或实际效果。"""
import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

MATCHES = ("精准", "词组", "广泛")
MISSING = "未查到"


def norm(value):
    return " ".join(str(value).strip().lower().split())


def candidate_code(value):
    """S3 v0.3 写成「C2（对标 B0…，…）」，只取开头的候选编号比较。"""
    found = re.match(r"\s*(C\d+)", str(value), re.I)
    return found.group(1).upper() if found else norm(value)


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def read_s3(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    meta = {}
    for key, label in (("seed", "种子词"), ("site", "站点"), ("candidate", "针对候选")):
        found = re.findall(r"^\s*" + label + r"[：:]\s*(.+?)\s*$", text, re.M)
        if len(found) != 1:
            raise ValueError("S3 必须有唯一的 " + label)
        meta[key] = found[0].strip(chr(96) + "* ")
    keywords = {}
    in_table = False
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            in_table = False
            continue
        cells = [c.strip().strip(chr(96)) for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if cells == ["词", "放在哪", "来源"]:
            in_table = True
            continue
        if not in_table or all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) != 3 or not all(cells):
            raise ValueError("S3 关键词清单字段不完整")
        keywords[norm(cells[0])] = {"keyword": cells[0], "placement": cells[1], "source": cells[2]}
    if not keywords:
        raise ValueError("未找到 S3 的 词 / 放在哪 / 来源 表")
    return {"meta": meta, "keywords": keywords}


def validate(draft, s3):
    errors = []
    def fail(code, detail):
        errors.append({"code": code, "detail": detail})
    def required(obj, fields, where):
        for field in fields:
            if not isinstance(obj.get(field), str) or not obj[field].strip():
                fail("FIELD", f"{where}.{field} 必须为非空字符串")
    def rows(field, allow_empty=True):
        value = draft.get(field)
        if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
            fail("FIELD", field + " 必须为对象数组")
            return []
        if not value and not allow_empty:
            fail("FIELD", field + " 不能为空")
        return value
    if not isinstance(draft, dict):
        return [{"code": "FIELD", "detail": "draft 必须为对象"}]
    meta = draft.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    required(meta, ("seed", "site", "candidate", "generated", "data_period", "upstream", "strategy_version"), "meta")
    if candidate_code(meta.get("candidate", "")) != candidate_code(s3["meta"].get("candidate", "")):
        fail("CANDIDATE", "S4 与 S3 的 candidate 不一致")
    for field in ("seed", "site"):
        if norm(meta.get(field, "")) != norm(s3["meta"].get(field, "")):
            fail("INPUT", "S4 与 S3 的 " + field + " 不一致")
    calls = meta.get("sellersprite_calls")
    if not isinstance(calls, dict):
        calls = {}
    for field in ("new", "cache"):
        if type(calls.get(field)) is not int or calls[field] < 0:
            fail("FIELD", "调用次数 " + field + " 必须为非负整数")
    ads, deferred, negatives, budgets = rows("ads", False), rows("deferred"), rows("negatives"), rows("budgets", False)
    notes = draft.get("notes")
    if not isinstance(notes, list) or not notes or any(not isinstance(x, str) or not x.strip() for x in notes):
        fail("FIELD", "notes 必须为非空字符串数组")
    selected, skipped, used_groups, pairs = set(), set(), set(), set()
    for i, ad in enumerate(ads):
        required(ad, ("keyword", "match", "source", "reason", "bid_source", "bid_period"), f"ads[{i}]")
        key, match = norm(ad.get("keyword", "")), ad.get("match")
        if key not in s3["keywords"]:
            fail("KEYWORD_SOURCE", f"投放词不在 S3 清单：{ad.get('keyword')}")
        selected.add(key)
        if not isinstance(match, str) or match not in MATCHES:
            fail("MATCH", f"未知匹配方式：{match}")
        else:
            used_groups.add(match)
            if (key, match) in pairs:
                fail("DUPLICATE", f"同词同匹配重复：{key}/{match}")
            pairs.add((key, match))
        bid = ad.get("bid")
        if bid == MISSING:
            required(ad, ("missing_reason",), f"ads[{i}]")
        elif number(bid) is None or number(bid) <= 0:
            fail("BID", f"{key} 的竞价必须为正数或“未查到”")
        for field in ("bid_min", "bid_max"):
            v = ad.get(field, MISSING)
            if v != MISSING and (number(v) is None or number(v) <= 0):
                fail("BID", f"{key}.{field} 必须为正数或“未查到”")
        low, high = number(ad.get("bid_min")), number(ad.get("bid_max"))
        if low is not None and high is not None and low > high:
            fail("BID", f"{key} 竞价区间下限大于上限")
    for i, row in enumerate(deferred):
        required(row, ("keyword", "reason"), f"deferred[{i}]")
        key = norm(row.get("keyword", ""))
        if key not in s3["keywords"]:
            fail("KEYWORD_SOURCE", "暂缓词不在 S3：" + key)
        if key in selected or key in skipped:
            fail("COVERAGE", "暂缓词重复或同时投放：" + key)
        skipped.add(key)
    missing = set(s3["keywords"]) - selected - skipped
    if missing:
        fail("COVERAGE", "S3 词未说明去向：" + ", ".join(sorted(missing)))
    seen, total = set(), Decimal(0)
    for row in budgets:
        match, percent = row.get("match"), number(row.get("percent"))
        if not isinstance(match, str) or match not in MATCHES or match in seen:
            fail("BUDGET", "预算组未知或重复")
        else:
            seen.add(match)
        if percent is None or percent < 0 or percent > 100:
            fail("BUDGET", "预算比例必须在 0–100")
        else:
            total += percent
            if percent > 0 and isinstance(match, str) and match not in used_groups:
                fail("EMPTY_GROUP", f"空组 {match} 不能分配预算")
    if seen != set(MATCHES) or total != 100:
        fail("BUDGET", f"必须列出三个组且比例合计 100%，当前 {total}%")
    daily = draft.get("daily_budget")
    if daily is None:
        if any("amount" in b for b in budgets):
            fail("BUDGET", "未提供日预算却填写了金额")
    elif not isinstance(daily, dict):
        fail("BUDGET", "daily_budget 必须为空或对象")
    else:
        amount = number(daily.get("amount"))
        if amount is None or amount <= 0 or not str(daily.get("currency", "")).strip():
            fail("BUDGET", "日预算需为正数且币种非空")
        amounts = [number(b.get("amount")) for b in budgets]
        if any(n is None or n < 0 for n in amounts) or sum(n for n in amounts if n is not None) != amount:
            fail("BUDGET", "各组金额无效或合计不等于日预算")
        elif amount is not None:
            for b, cash in zip(budgets, amounts):
                pct = number(b.get("percent"))
                if pct is not None and abs(cash - amount * pct / 100) > Decimal("0.02"):
                    fail("BUDGET", "组金额与比例不符（允许分币尾差）")
    for i, neg in enumerate(negatives):
        required(neg, ("keyword", "match", "reason"), f"negatives[{i}]")
        scopes = neg.get("scopes")
        if (not isinstance(scopes, list) or not scopes
                or any(not isinstance(x, str) or x not in (*MATCHES, "全部") for x in scopes)):
            fail("NEGATIVE", "否定范围需为匹配组数组或 [全部]")
            continue
        if neg.get("match") not in ("否定精准", "否定词组"):
            fail("NEGATIVE", "未知否定方式")
            continue
        nk = norm(neg.get("keyword", ""))
        if not nk:
            continue
        for ad in ads:
            if "全部" not in scopes and ad.get("match") not in scopes:
                continue
            ak = norm(ad.get("keyword", ""))
            conflict = ak == nk if neg["match"] == "否定精准" else " " + nk + " " in " " + ak + " "
            if conflict:
                fail("NEGATIVE_CONFLICT", f"{nk} 在 {ad.get('match')} 组字面冲突：{ak}")
    return errors


def table(headers, rows):
    def esc(v):
        return str(v).replace("|", r"\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
                     + ["| " + " | ".join(esc(x) for x in row) + " |" for row in rows])


def render(d):
    m = d["meta"]
    out = ["# S4 广告 · 试跑草案", ""]
    for label, key in (("种子词", "seed"), ("站点", "site"), ("生成时间", "generated"),
                       ("数据周期", "data_period"), ("上游文件", "upstream"),
                       ("针对候选", "candidate"), ("策略版本", "strategy_version")):
        out.append(f"{label}：{m[key]}")
    out += ["", "## 投放词", "", table(
        ["词", "匹配方式", "建议竞价", "参考区间", "竞价来源与周期", "S3 来源", "理由"],
        [[a["keyword"], a["match"], a["bid"], f"{a.get('bid_min', MISSING)}–{a.get('bid_max', MISSING)}",
          f"{a['bid_source']}；{a['bid_period']}；{a.get('missing_reason', '')}", a["source"], a["reason"]]
         for a in d["ads"]]), "", "竞价为市场参考，币种沿用站点来源；不代表实际广告 CPC 或已执行出价。",
        "", "## 暂缓词", "", table(["词", "理由"], [[r["keyword"], r["reason"]] for r in d["deferred"]])
        if d["deferred"] else "暂无", "", "## 预算", ""]
    daily = d.get("daily_budget")
    out += [f"用户日预算：{daily['amount']} {daily['currency']}" if daily else "未提供日预算，仅输出比例。",
            "", table(["匹配方式", "预算比例"] + (["金额"] if daily else []),
                      [[r["match"], str(r["percent"]) + "%"] + ([r["amount"]] if daily else [])
                       for r in d["budgets"]]), "", "## 否定预案", ""]
    out += [table(["否定词", "方式", "范围", "理由"],
                  [[r["keyword"], r["match"], "、".join(r["scopes"]), r["reason"]] for r in d["negatives"]])
            if d["negatives"] else "暂无：当前证据不足以新增否定词。",
            "", "## 假设、缺口与评审", ""]
    out += ["- " + n for n in d["notes"]]
    out += ["", "## 校验", "", "结构校验通过；详见 s4_validation.json。广告策略与实际效果另行评审。",
            "", f"卖家精灵调用：新调用 {m['sellersprite_calls']['new']} 次 / 读缓存 {m['sellersprite_calls']['cache']} 次", ""]
    return "\n".join(out)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("draft", type=Path)
    ap.add_argument("--s3", type=Path, required=True)
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    try:
        d = json.loads(args.draft.read_text(encoding="utf-8-sig"))
        errors = validate(d, read_s3(args.s3))
    except (OSError, ValueError) as exc:
        print("FAIL INPUT:", exc)
        return 1
    report = {"passed": not errors, "errors": errors, "draft_sha256": sha(args.draft),
              "s3_sha256": sha(args.s3), "scope": "字段、来源、预算与否词字面冲突；不验证业务效果"}
    out = args.draft.parent
    (out / "s4_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for e in errors:
        print("FAIL", e["code"], e["detail"])
    if errors:
        print("未渲染本轮报告；同目录已有 s4_广告.md 如存在，属于旧轮次。")
        return 1
    if args.render:
        (out / "s4_广告.md").write_text(render(d), encoding="utf-8")
    print(f"PASS: {len(d['ads'])} 条投放配置，{len(d['deferred'])} 个暂缓词；结构通过，效果未验证")
    return 0


if __name__ == "__main__":
    sys.exit(main())
