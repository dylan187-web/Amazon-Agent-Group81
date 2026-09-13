#!/usr/bin/env python3
"""冻结本轮证据并比较广告方案；不调用 MCP，不覆盖已有版本。"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from check_ads import render, sha, table

HERE = Path(__file__).resolve().parent
FILES = ("s1_选品.md", "s2_利润.md", "s3_listing.md", "s3_draft.json",
         "s4_draft.json", "s4_validation.json", "issues.md", "calls.json",
         "run_manifest.json", "chain_validation.json", "review.md", "review_annotations.json",
         "s1_selection.json", "verify_chain.py", "s3_validation.txt", "产品信息.md",
         "verification.md")


def version_name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError("版本只允许字母、数字、点、下划线或短横线")
    return value


def projection(d):
    return {
        "选词与匹配": sorted((a["keyword"], a["match"]) for a in d["ads"]),
        "预算": sorted((r["match"], r["percent"], r.get("amount")) for r in d["budgets"]),
        "竞价": sorted((a["keyword"], a["match"], str(a["bid"])) for a in d["ads"]),
        "否定词": sorted((n["keyword"], n["match"], tuple(sorted(n["scopes"]))) for n in d["negatives"]),
        "暂缓词": sorted((r["keyword"], r["reason"]) for r in d["deferred"]),
    }


def save(run, version, previous=None):
    version_name(version)
    if previous:
        version_name(previous)
    target = run / "iterations" / version
    prior = run / "iterations" / previous if previous else None
    if target.exists():
        raise ValueError("版本已存在，拒绝覆盖：" + str(target))
    required = ("s3_listing.md", "s4_draft.json", "s4_validation.json")
    if any(not (run / name).is_file() for name in required):
        raise ValueError("先生成 S3、S4 draft 和本轮校验结果")
    report = json.loads((run / "s4_validation.json").read_text(encoding="utf-8"))
    for name, field in (("s4_draft.json", "draft_sha256"), ("s3_listing.md", "s3_sha256")):
        if sha(run / name) != report.get(field):
            raise ValueError("校验结果已过期，请重新运行 check_ads.py")
    if prior and not (prior / "manifest.json").is_file():
        raise ValueError("上一版本不存在")
    if report.get("passed") and not (run / "s4_广告.md").is_file():
        raise ValueError("校验通过后请使用 --render 生成本轮报告")
    draft = json.loads((run / "s4_draft.json").read_text(encoding="utf-8"))
    if report.get("passed") and (run / "s4_广告.md").read_text(encoding="utf-8") != render(draft):
        raise ValueError("渲染报告与本轮 draft 不一致，请使用 --render 重新生成")
    target.mkdir(parents=True)
    for name in FILES + (("s4_广告.md",) if report.get("passed") else ()):
        if (run / name).is_file():
            shutil.copy2(run / name, target / name)
    for path in (run / "raw").glob("*.json"):
        (target / "raw").mkdir(exist_ok=True)
        shutil.copy2(path, target / "raw" / path.name)
    for name in ("prompt.md", "check_ads.py", "review_iteration.py"):
        shutil.copy2(HERE / name, target / name)
    hashes = {str(p.relative_to(target)).replace("\\", "/"): sha(p)
              for p in sorted(target.rglob("*")) if p.is_file()}
    manifest = {"version": version, "previous": previous,
                "created_utc": datetime.now(timezone.utc).isoformat(), "sha256": hashes}
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    current = json.loads((target / "s4_draft.json").read_text(encoding="utf-8"))
    out = [f"# S4 {version} 评审对比", ""]
    if prior:
        old_manifest = json.loads((prior / "manifest.json").read_text(encoding="utf-8"))
        old = json.loads((prior / "s4_draft.json").read_text(encoding="utf-8"))
        keys = lambda h: {k: v for k, v in h.items() if k in ("s3_listing.md", "产品信息.md") or k.startswith("raw/")}
        same = keys(old_manifest["sha256"]) == keys(hashes) and old.get("daily_budget") == current.get("daily_budget")
        out += ["S3 输入与缓存相同，日预算及产品补充信息也相同，可以比较策略差异。" if same else
                "S3 输入、缓存、日预算或产品补充信息已改变，变化不能只归因于广告策略。", ""]
        before, after = projection(old), projection(current)
        out += [table(["项目", previous, version, "是否变化"],
                      [[k, json.dumps(before[k], ensure_ascii=False), json.dumps(after[k], ensure_ascii=False),
                        "变化" if before[k] != after[k] else "不变"] for k in before])]
    else:
        out += ["首次基线，尚无上一轮。后续以相同 S3 与缓存对比。", "",
                table(["项目", version], [[k, json.dumps(v, ensure_ascii=False)] for k, v in projection(current).items()])]
    out += ["", "结构校验：" + ("通过" if report.get("passed") else "失败"),
            "广告业务判断见 issues.md / review.md；真实投放效果尚未验证。", ""]
    (target / "comparison.md").write_text("\n".join(out), encoding="utf-8")
    return target


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path)
    ap.add_argument("--version", required=True)
    ap.add_argument("--previous")
    args = ap.parse_args()
    try:
        print(save(args.run.resolve(), args.version, args.previous))
        return 0
    except (ValueError, OSError) as exc:
        print("FAIL:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
