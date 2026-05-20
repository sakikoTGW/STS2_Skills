# 铁甲战士构筑思路（STS2 study 用）

插件代码：`plugins/sts2/ironclad_builds.py` — 自动注入【构筑诊断】到选牌/战斗 LLM。

## 主轴（五类）

| 主轴 | 标志卡 | 选牌方向 | 战斗要点 |
|------|--------|----------|----------|
| 前期通用 | floor≤8 且无核心 | 易伤、AOE、格挡+抽、0费过牌 | 拿功能不堆打击 |
| 力量成长 | Inflame / Demon Form | 力量、多段攻、抽牌 | 先能力后输出 |
| 格挡壁垒 | Barricade / Entrench | 格挡技、Iron Wave | 先叠防再 Entrench |
| 消耗组合 | Feel No Pain | 带 Exhaust 的牌 | FNP 换防/抽 |
| 节奏功能 | Bash / Cleave 等 | 补 AOE、不重复打击 | 斩杀优先 |

## Wiki

每张候选牌应 `sts2_wiki_search` 进 `~/.hermes/sts2/knowledge/cards.yaml`，LLM 读摘要再选。

## 与 STS1 区别

STS2 战后奖励是**精选池**，不是三张 Strike。禁止「全打击就跳过」。
