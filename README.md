# Amazon Agent Group81 · 亚马逊卖家通用选品 Agent

生财跨境 Agent 大课 · 黑客松第 81 组作业。

在 Claude Code 或 Codex 里说一句「**对 `<种子词>` 跑一遍**」，Agent 按四个阶段往下走：

```
S1 选品（有趋势、可以选的品） → S2 利润核算 → S3 Listing → S4 广告
```

每个阶段写一份产出文件交给下一阶段。铺货、精品卖家都能用。需求和边界见 [`SPEC.md`](SPEC.md)。

## 快速开始

1. **接入卖家精灵 MCP**（用你自己的 key，不要写进仓库）：
   ```
   地址：https://mcp.sellersprite.com/mcp
   Header：secret-key = 你的 MCP Key（卖家精灵开放平台 → 我的密钥）
   ```
2. **克隆仓库**，在仓库目录里打开 Claude Code 或 Codex。
   - Claude Code 也可以装成 Skill：`ln -s "$(pwd)" ~/.claude/skills/amazon-agent-group81`
3. **说一句话**：
   ```
   读 SKILL.md，对「bamboo drawer organizer」跑一遍，站点 US
   ```
   想用自己的成本算利润，就加上：`采购价 3.5 美元，头程 1.2 美元/件`

产出在 `runs/<日期>_<种子词>/`。

**参考运行**：[`runs/2026-09-12_bamboo-drawer-organizer/`](runs/2026-09-12_bamboo-drawer-organizer/)。这是一次真实跑通的完整结果（卖家精灵 11 次调用），四个阶段各该产出什么可以对着看。每份文件末尾的「运行备注」写了骨架提示词暴露的问题，各阶段负责人先看自己那份。

## 目录

| 路径 | 是什么 | 谁改 |
|---|---|---|
| `SKILL.md` | 路由入口：阶段顺序、输入参数、每阶段读写哪个文件 | Dylan |
| `contracts/交接内容.md` | 阶段之间必须交接的最低字段 | Dylan |
| `stages/s1-选品/` … `stages/s4-广告/` | 每阶段的提示词 `prompt.md`，可选 `scripts/` | 该阶段负责人 |
| `samples/` | 各阶段的样例产出（**全部虚构**），下游对着它开发 | 该阶段负责人 |
| `runs/` | 实际运行结果（默认不提交，演示用的那份单独挑出来提交） | — |
| `99_交接/` | 收工交接，文件名 `YYYY-MM-DD_姓名_阶段.md` | 各自 |
| `templates/` | 多 AI 协作模板（参考用） | — |

## 怎么参与开发

1. **认领阶段**：在群里说一声，Dylan 更新下表。
2. **Fork 或拉分支**：分支名 `s1-选品-你的名字` 这种格式。
3. **只改自己阶段的目录**（`stages/<你的阶段>/` 和 `samples/` 里你那份）。要改 `contracts/` 或 `SKILL.md`，先在群里说。
4. **提 PR**，写清：做了什么、怎么验证、用的 Codex 还是 Claude Code。Dylan 合并。
5. 细则见 [`协作开发要领.md`](协作开发要领.md) 与 [`AGENTS.md`](AGENTS.md)。

**原则：轻量全流程，力争高效不争完美，跑通为准。**

| 阶段 | 负责人 | 目录 | 状态 |
|---|---|---|---|
| S1 选品 | 张也、花无缺 | `stages/s1-选品/` | 开发中 |
| S2 利润和预算测算 | Snow | `stages/s2-利润/` | 开发中 |
| S3 Listing | Dylan | `stages/s3-listing/` | 开发中 |
| S4 广告 | 二十。 | `stages/s4-广告/` | 开发中 |
| 骨架 / 合并 / 视频 | Dylan | `SKILL.md`、`contracts/` | 进行中 |
| 学习与辅助 | 黄建雄、Y. | — | 跟进 |

S1 两人共用一个目录：先商量好谁主写 `prompt.md`，另一人把补充内容发给主写人合进去，或放到 `stages/s1-选品/notes-<名字>.md`，避免两人同时改同一个文件冲突。

## 红线（公开仓库）

- **不提交任何 key**（卖家精灵、大模型）。
- **不提交真实店铺数据**：店铺名、自家 ASIN 业绩、利润、后台导出。
- **不提交大文件**（ABA 原始包等）。
- **不用侵权词 / 品牌词 / IP 词**做种子词或样例。

## 致谢

业务判断思路参考了 [buluslan/bulus-amazon-skill](https://github.com/buluslan/bulus-amazon-skill)（MIT License © 2026 buluslan）。

## License

[MIT](LICENSE)
