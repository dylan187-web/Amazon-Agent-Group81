# S4 广告交付 · 二十。

本阶段由 Codex 按已批准方案实现：提示词负责广告判断，Python 负责交接校验和版本对比。只使用标准库，不安装第三方依赖。

## 文件

- prompt.md：执行步骤和唯一广告策略配置区。
- sample_draft.json：与课程 samples/s3_listing.md 对齐的虚构输入；竞价全部“未查到”。
- check_ads.py：检查候选、站点/种子、S3 原词来源、字段、预算和否词字面冲突；通过后渲染课程格式。
- test_check_ads.py：离线异常与版本保护测试。
- review_iteration.py：保存不可覆盖的本地快照、SHA256 和选词/匹配/预算/竞价/否词差异。
- ../../samples/s4_广告.md：虚构样例报告。真实运行在 git 忽略的 runs/ 下。

## 使用

从仓库根目录执行（把 python 替换为本机 Python 3 路径；macOS 上是 `python3`）：

```text
python -m unittest discover -s stages/s4-广告 -p "test_*.py" -v
python stages/s4-广告/check_ads.py runs/<本次>/s4_draft.json --s3 runs/<本次>/s3_listing.md --render
python stages/s4-广告/review_iteration.py runs/<本次> --version v1
```

修改前先确认 v1 已保存。按 prompt.md 策略配置生成下一份 draft，用同一 S3 和 raw 缓存校验，再保存 --version v2 --previous v1。每轮创建新版本名，脚本拒绝覆盖已有版本、过期校验或旧渲染报告。生成的 comparison.md 用于用户决策，不会自动推广策略或提交代码。

## 交接边界

广告是研究草案。竞价缺失写明原因；未提供日预算不填金额；S3 词可暂缓但不能另造投放词。检查器允许改预算权重和同词跨匹配，不把具体打法写死。否词检查仅检查同范围字面同词/完整词组，不模拟 Amazon 的近似变体或语义匹配。

候选多样性、评论是否代表本品、产品事实和广告效果属于人工评审；字段齐全不代表这些问题已解决。异常记录采用：

| 异常现象 | 证据 | 所属阶段 | 建议修改 | 修改后结果 |
|---|---|---|---|---|
| 示例：查询不相关 | 原始文件 + 请求参数 | S1/接口 | 负责人确认匹配模式 | 待验证 |

实现与虚构样例经负责人审核后，通过分支 PR 交付；真实试跑资料与迭代快照保留本地。策略变更可继续提交后续 PR，合并由组长处理。
