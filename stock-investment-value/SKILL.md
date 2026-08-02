---
name: stock-investment-value
description: >
  基于 Tushare 真实基本面数据评估股票投资价值。先做风格分类（当前实现成长股，
  红利/周期/质量等类型框架预留待扩展），再按对应评估框架输出打分卡与评级。
  支持单股评估（fetch_fundamentals.py）与全市场扫描低估成长股
  （scan_growth_a.py：PEG<1 且 PE-TTM 近5年分位<50%）。
  评估只用预写脚本拉取的真实数据，禁止虚构数字，结论附免责声明。
  用于"帮我看看XX值不值得买""评估XX的投资价值""XX是不是成长股""给XX打个分"
  "帮我找低估成长股"等请求。
author: Generated from user request
version: 1.1.0
credentials:
  - name: TUSHARE_TOKEN
    description: Tushare Token，用于认证和授权访问 Tushare 数据服务。
    how_to_get: "https://tushare.pro/register"
requirements:
  python: 3.8+
  packages:
    - name: tushare
    - name: pandas
  environment_variables:
    - name: TUSHARE_TOKEN
      required: false
      sensitive: true
  network_access: true
---

# 股票投资价值评估（成长股框架）

基于 Tushare 真实数据评估个股投资价值。**分类驱动**：先判断股票类型，再套用对应
评估框架。v1.0 实现**成长股**框架，其余类型（红利、周期、质量等）在
`references/` 中预留结构，后续按同一模式扩展。

## 核心原则

1. **数据优先脚本**：所有数据必须来自 `scripts/fetch_fundamentals.py` 的输出，
   禁止凭空编造任何数字。
2. **分类驱动**：先分类，再评估。评估框架见 `references/`。
3. **避免繁琐**：打分卡只保留业内共识的经典指标，阈值清晰可复现。
4. **不构成投资建议**：每次输出必须附免责声明。

## 核心工作流

1. **确认标的**：从用户请求中解析出股票（代码或名称，如 `300750.SZ` /
   "宁德时代"）。名称需先用 `stock_basic` 反查代码（脚本支持 `--name`）。
2. **拉取数据**：运行取数脚本，得到原始数据 JSON 与衍生指标
   `derived_metrics.json`。若脚本报错（如接口权限不足、数据缺失），
   如实汇报"该数据不可得"，不得用假设值补齐。
3. **分类**：按 `references/分类方法.md` 判定是否成长股。
   - 是 → 进入步骤 4；
   - 否 → 明确告知"当前版本仅实现成长股框架"，列出该股所属类型的判定依据，
     并提示可用 tushare-data 技能做基础数据研究，不强行打分。
4. **打分**：按 `references/成长股.md` 的打分卡逐维打分，**每一分都必须
   引用 `derived_metrics.json` 或原始数据中的真实数值**。
5. **输出**：见下方"输出结构"。

## 输出结构（固定格式）

```
📋 XX（300750.SZ）投资价值评估 — 成长股框架
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 成长性      XX / 35    （依据：营收增速 x%，净利增速 x%，稳定性 CV…）
2. 盈利质量    XX / 25    （依据：毛利率 x%，净利率 x%，经营现金流/净利 x…）
3. 估值吸引力  XX / 20    （依据：PEG=x，5年PE-TTM分位 x%）
4. 财务健康    XX / 12    （依据：负债率 x%…）
5. 流动性与规模 XX / 8    （依据：日均成交额 x 亿，市值 x 亿）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
综合得分：XX / 100 → 评级：低估/合理/谨慎/回避
关键数据表（真实数据）：
| 指标 | 数值 | 来源 |
| ...  | ...  | derived_metrics.json |
风险提示：...
免责声明：本内容仅为数据分析，不构成投资建议。
```

评分、评级与判定阈值一律以 `references/成长股.md` 为准，不得临场改动。

## 脚本用法

### 1. 单股评估 `scripts/fetch_fundamentals.py`

```bash
# 按代码
python scripts/fetch_fundamentals.py 300750.SZ --outdir ./output
# 按名称（自动反查代码）
python scripts/fetch_fundamentals.py --name 宁德时代 --outdir ./output
```

输出目录含：`basic.json`、`valuation.json`（最新估值 + 近5年序列）、
`fina_indicator.json`、`income.json`、`cashflow.json`、`dividend.json`、
`daily.json`、`forecast.json`、`report_rc.json`、`derived_metrics.json`。
详见脚本 docstring。

### 2. 全市场扫描 `scripts/scan_growth_a.py`

用于在 A 股全市场筛选**情形 A（PEG<1 且 PE-TTM 近5年分位<50%，真便宜双重确认）**
的成长股。两阶段：阶段1 低限制接口全市场粗筛（2~3 次批量调用）→
阶段2 对候选逐只精筛（带延迟防限频），每只打印选中/淘汰及原因。

```bash
# 全量扫描（默认市值下限 50 亿、逐只延迟 0.5s）
python scripts/scan_growth_a.py --outdir ./scan_result

# 只做阶段1粗筛，看候选池规模
python scripts/scan_growth_a.py --list-only --outdir ./scan_result

# 指定候选精筛（跳过阶段1）
python scripts/scan_growth_a.py --only-codes 300308.SZ,300750.SZ --outdir ./scan_result

# 中断后续跑（复用缓存）
python scripts/scan_growth_a.py --resume --outdir ./scan_result
```

参数：`--min-mv`（市值下限，默认 50 亿）、`--limit`（最多检查只数）、
`--delay`（逐只延迟秒数，默认 0.2，适配 5000 积分=500次/分钟；触发限频会自动退避重试）、
`--outdir`。

输出：`hits.csv`（命中清单）+ `scan_cache.json`（断点续跑缓存）。

注意：`report_rc`（一致预期）有 10次/小时 频率限制，扫描脚本**不调用**该接口，
PEG 增速分母统一用近3年净利增速均值；对命中清单如需前瞻验证，
可再对个股跑 `fetch_fundamentals.py` 获取一致预期对照。

### 3. 阈值定义

筛选阈值与 `references/成长股.md` / `references/分类方法.md` 保持一致：
营收增速均值≥15%、净利增速均值≥20%、扣非增速>0、PEG<1、PE分位<50%，
上市≥3年，排除周期/金融行业黑名单。

## 防虚构规则（强制）

- 只允许引用脚本输出文件中的字段值。
- PEG 采用**混合 PEG**（PE-TTM ÷ 一致预期增速）：增速分母按优先级链
  一致预期 → 业绩预告 → TTM 同比 → 累计同比 → 3 年均值逐级回退，
  并通过 `growth_basis`/`growth_period` 显式标注所用口径，禁止混用不标注。
- 某接口失败或权限不足：写"数据不可得"，该维度按缺失处理（按 `成长股.md`
  中"数据缺失处理"执行），绝不编数字。
- PEG 中增速 ≤ 0 时 PEG 无意义：标注"增速为负，PEG 不适用"，不硬算。

## When to use

- "帮我看看 XX 值不值得买 / 有没有投资价值"
- "评估一下 XX 这只股票"
- "XX 是成长股吗？现在估值贵不贵"
- "给 XX 打个分 / 做个基本面评估"
- "帮我找找 A 股里便宜又高成长的股票" / "扫描低估成长股"（用 scan_growth_a.py）
- 任何要求基于基本面判断个股价值的请求（A 股为主）

## Trigger phrases

- "值不值得买"、"投资价值"、"评估股票"、"给XX打分"
- "基本面分析"、"成长股"、"估值贵不贵"、"PEG"
- "低估成长股"、"便宜的高成长"、"PEG小于1"、"扫描选股"
- "XX 这只股票怎么样（基本面角度）"

## 与其他技能的关系

- **tushare-data**：通用取数技能，本技能脚本未覆盖的接口可回退使用；
  本技能自身保持自包含。
- **vibe-trading / tushare-data**：仅做数据研究，不做回测与交易执行。

## 边界与限制

- v1.0 仅实现成长股框架；银行、保险、周期、亏损困境股请明确提示不适用。
- 数据以 tushare 披露为准，财报有滞后（季报/年报披露节奏），输出时注明
  数据截止日期。
