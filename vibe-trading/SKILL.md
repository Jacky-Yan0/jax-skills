---
name: vibe-trading
description: 基于 Vibe-Trading AI 量化交易研究平台的自然语言技能。用于把"帮我回测这个策略""分析 BTC 动量""运行 Alpha 因子""查看持仓""列出运行记录"这类请求，转成可执行的 vibe-trading CLI 命令与工作流。适用于策略回测、因子研究、多 Agent 交易、跨市场数据查询、Broker 连接管理、假设管理等场景。
author: vibe-trading-ai (HKUDS)
version: 0.1.9
requirements:
  python: 3.7+
  packages:
    - name: vibe-trading-ai
  environment_variables:
    - name: VIBE_TRADING_HYPOTHESES_PATH
      required: false
      sensitive: false
  network_access: true
---

# vibe-trading

把自然语言量化交易请求，转成可执行的 Vibe-Trading 工作流。

这是一个面向自然语言的 AI 量化交易研究 skill。

## What this skill is for

使用这个 skill 的典型场景：

- 用自然语言描述策略并运行回测
- 分析某只股票/加密货币的动量与技术指标
- 浏览、对比、基准测试预构建量化因子（452 个因子，4 个 Alpha Zoo）
- 管理多 Agent 交易团队（29 个 Swarm 预设）
- 查询 Broker 账户、持仓、订单、报价、历史 K 线
- 管理持久化记忆与自进化技能
- 管理研究假设（探索 → 测试 → 验证 → 拒绝 → 监控）
- 跨市场数据获取（A 股 / 港美 / 加密货币 / 期货 / 外汇）

***

## When to use

当用户表达以下意图时，优先使用本 skill：

### 策略回测与研究

- "帮我回测 XX 策略"
- "分析 XX 的 20/50 均线交叉"
- "研究一下 BTC 动量策略"
- "回测沪深 300 指数 20 日均线策略，分析夏普比率和最大回撤"
- "用 2024 年数据跑一下这个策略"

### Alpha 因子研究

- "列出所有 Alpha 因子"
- "看看 gtja191 这个 Zoo 里有哪些因子"
- "帮我 benchmark 一下 alpha101 在沪深 300 上的表现"
- "对比 gtja191_171 和 gtja191_111 这两个因子"
- "导出因子清单"

### Swarm 多 Agent 交易

- "有哪些 Swarm 团队可以用"
- "运行 investment_committee 团队"
- "看看 quant_strategy_desk 的详情"
- "列出 Swarm 运行记录"

### Broker / 账户管理

- "连接 IBKR 模拟账户"
- "查看我的持仓"
- "查询 AAPL 实时报价"
- "拉取最近 30 天的历史 K 线"
- "查看账户摘要"

### 假设管理

- "列出所有研究假设"
- "看看 hyp_xxx 的详情"
- "标记这个假设为已拒绝"

### 持久化记忆

- "列出所有记忆"
- "搜索跟均线策略相关的记忆"
- "删除 xxx 记忆"

***

## What this skill is NOT for

- 直接生成投资建议或替代投资顾问
- 管理生产环境的实盘下单（仅在 Broker 连接器确认可用后）
- 替代专业回测引擎的深度分析
- 在没有安装 `vibe-trading-ai` 环境时强行模拟命令

如果环境不满足、命令不存在或权限不足，要明确说出限制，不要硬编。

***

## Environment check

在真正运行命令之前，先做前置校验：

1. 检查 `vibe-trading` CLI 命令是否存在（`which vibe-trading` 或 `vibe-trading --version`）
2. 检查 `~/.vibe-trading/.env` 配置文件是否存在（运行过 `vibe-trading init`）
3. 必要时运行 `vibe-trading init` 引导用户完成初始化
4. 如需 Tushare 数据源，检查 `TUSHARE_TOKEN` 是否配置

若缺失配置，直接提示最短修复路径：

```bash
pip install vibe-trading-ai
vibe-trading init
```

不要等到命令跑失败了才暴露环境问题。

***

## Intent taxonomy

先识别任务类型，再决定命令组合。

### 1. 运行策略 / 回测

典型问题：

- 回测 XX 策略
- 分析 XX 走势
- 研究 XX

命令：

```bash
# 直接传入提示
vibe-trading run -p "回测沪深300指数20日均线策略，分析夏普比率和最大回撤"

# 从文件读取
vibe-trading run -f strategy.txt

# 管道输入
echo "分析 BTC 动量策略" | vibe-trading run

# 限制迭代次数
vibe-trading run -p "研究 NVDA" --max-iter 10

# 继续之前的运行
vibe-trading --continue RUN_ID "继续分析"
```

### 2. Alpha 因子管理

典型问题：

- 列出 / 浏览因子
- 查看因子详情
- 基准测试
- 对比因子

命令：

```bash
# 列出所有因子
vibe-trading alpha list

# 按 Zoo 过滤
vibe-trading alpha list --zoo gtja191
vibe-trading alpha list --zoo alpha101 --limit 10

# 按主题过滤
vibe-trading alpha list --zoo gtja191 --theme reversal

# 按市场过滤
vibe-trading alpha list --universe csi300

# JSON 输出
vibe-trading alpha list --zoo alpha101 --json

# 查看单个因子详情
vibe-trading alpha show gtja191_171
vibe-trading alpha show alpha101_001 --brief

# 对整个 Zoo 做基准测试
vibe-trading alpha bench --zoo gtja191 --universe csi300 --period 2018-2025 --top 20

# 对比指定因子
vibe-trading alpha compare gtja191_171 gtja191_111 gtja191_163

# 导出清单
vibe-trading alpha export-manifest --out manifest.json
```

### 3. Swarm 多 Agent 交易

典型问题：

- 有哪些团队可用
- 运行 XX 团队
- 查看运行记录

内置 29 个预设，常用：

| 预设 | 用途 |
|------|------|
| `investment_committee` | 多空辩论 → 风险评估 |
| `quant_strategy_desk` | 因子筛选 → 回测 → 风险审计 |
| `crypto_trading_desk` | 资金费率 + 清算 + 链上分析 |
| `technical_analysis_panel` | 多技术分析流派共识 |
| `global_allocation_committee` | 跨市场资产配置 |

命令：

```bash
# 列出所有 Swarm 预设
vibe-trading --swarm-presets

# 查看预设详情
vibe-trading --swarm-invest PRESET

# 运行 Swarm 预设
vibe-trading --swarm-run PRESET [VARS ...]

# 列出运行记录
vibe-trading --swarm-list

# 查看运行详情
vibe-trading --swarm-show RUN_ID

# 取消运行
vibe-trading --swarm-cancel RUN_ID
```

### 4. Broker / 交易连接器管理

典型问题：

- 连接 Broker
- 查看账户 / 持仓 / 订单
- 查询报价 / K 线

支持的连接器：IBKR、Robinhood、Tiger、Alpaca、OKX、Binance、Futu、Longbridge、Dhan、Shoonya

命令：

```bash
# 列出可用连接器
vibe-trading connector list

# 选择并配置连接器
vibe-trading connector use ibkr-paper-local
vibe-trading connector configure ibkr-paper-local --yes

# 检查连接状态
vibe-trading connector check

# 查看账户、持仓、订单
vibe-trading connector account
vibe-trading connector positions
vibe-trading connector orders

# 查询报价
vibe-trading connector quote AAPL
vibe-trading connector quote 600519.SH --exchange SMART --currency CNY

# 查询历史 K 线
vibe-trading connector history AAPL --duration "30 D" --bar-size "1 day"

# 启动/停止连接器
vibe-trading connector start
vibe-trading connector stop

# 紧急停止/恢复
vibe-trading connector halt
vibe-trading connector resume

# 撤销授权
vibe-trading connector revoke
```

### 5. 查看运行记录

典型问题：

- 之前跑过的策略结果
- 查看某次运行的代码
- 导出 Pine Script

命令：

```bash
# 列出所有运行记录
vibe-trading list
# 或
vibe-trading --list

# 查看运行详情
vibe-trading show RUN_ID
vibe-trading --show RUN_ID

# 查看生成的策略代码
vibe-trading --code RUN_ID

# 导出 TradingView Pine Script
vibe-trading --pine RUN_ID

# 回放执行跟踪
vibe-trading --trace RUN_ID
```

### 6. 聊天与会话管理

典型问题：

- 进入交互式聊天
- 继续之前的会话

命令：

```bash
# 进入交互式聊天
vibe-trading chat
# 或
vibe-trading --chat

# 继续之前的会话
vibe-trading --session-chat SESSION_ID

# 列出所有会话
vibe-trading --sessions
```

### 7. 持久化记忆管理

典型问题：

- 记下某个策略参数
- 搜索之前保存的记忆
- 删除没用的记忆

命令：

```bash
# 列出所有记忆
vibe-trading memory list

# 按类型过滤
vibe-trading memory list --type user
vibe-trading memory list --type feedback
vibe-trading memory list --type project
vibe-trading memory list --type reference

# 搜索记忆
vibe-trading memory search "均线策略参数"
vibe-trading memory search "因子失效" --limit 10

# 查看记忆详情
vibe-trading memory show "ma_strategy_params"

# 删除记忆
vibe-trading memory forget "ma_strategy_params"
vibe-trading memory forget "old_memory" -y   # 跳过确认
```

### 8. 假设管理

典型问题：

- 列出研究假设
- 查看假设详情
- 标记假设为已拒绝

生命周期：exploring → testing → validated → rejected → monitoring

命令：

```bash
# 列出所有假设
vibe-trading hypothesis list

# 按状态过滤
vibe-trading hypothesis list --status validated
vibe-trading hypothesis list --status rejected
vibe-trading hypothesis list --status testing

# 查看假设详情
vibe-trading hypothesis show hyp_abcd1234ef56

# 标记为拒绝（带备注）
vibe-trading hypothesis invalidate hyp_abcd1234ef56 --note "因子失效，IC 不显著"
```

### 9. API 服务器管理

典型问题：

- 启动 Web 服务
- 启动开发模式

命令：

```bash
# 默认启动
vibe-trading serve

# 自定义端口
vibe-trading serve --port 8080

# 开发模式（含前端热重载）
vibe-trading serve --dev
```

### 10. 初始化配置

典型问题：

- 第一次使用需要配置
- 更换 LLM 提供商

命令：

```bash
# 交互式初始化
vibe-trading init
```

向导设置：LLM 提供商、API Key、基础 URL、Tushare Token（可选）

### 11. OAuth 提供商管理

```bash
# 登录 LLM OAuth 提供商
vibe-trading provider login openai-codex
```

***

## Quick reference: 快捷标志

很多常用操作可以直接通过顶层标志完成：

| 快捷标志 | 等价于 | 用途 |
|----------|--------|------|
| `--list` | `list` | 列出运行记录 |
| `--show RUN_ID` | `show RUN_ID` | 查看运行详情 |
| `--code RUN_ID` | — | 查看生成的策略代码 |
| `--pine RUN_ID` | — | 导出 TradingView Pine Script |
| `--trace RUN_ID` | — | 回放执行跟踪 |
| `--chat` | `chat` | 进入交互式聊天 |
| `--upload FILE` | — | 上传文件供 Agent 分析 |
| `--continue RUN_ID PROMPT` | — | 继续之前的运行 |
| `--skills` | — | 列出所有可用技能 |
| `--swarm-presets` | — | 列出所有 Swarm 团队预设 |
| `--swarm-run PRESET` | — | 运行 Swarm 团队 |
| `--swarm-list` | — | 列出 Swarm 运行记录 |
| `--session-chat SESSION_ID` | — | 继续之前的会话 |

***

## Quick reference: 数据源

| 数据源 | 市场 | 是否需要 Key |
|--------|------|:----------:|
| Tushare | A 股 | 可选（推荐） |
| AKShare | A 股 / 全球 | 否 |
| mootdx | A 股（通达信 TCP） | 否 |
| yfinance | 港 / 美 | 否 |
| OKX | 加密货币 | 否 |
| CCXT | 加密货币（100+ 交易所） | 否 |
| Futu | 港股 / A 股 | 是 |

***

## Quick reference: 内置 Alpha Zoo

| Zoo | 因子数量 | 说明 |
|-----|:-------:|------|
| `qlib158` | 154 | Qlib 因子集 |
| `alpha101` | 101 | WorldQuant 101 Alpha |
| `gtja191` | 191 | 国泰君安 191 因子 |
| `academic` | 6 | 学术因子集 |

***

## Quick reference: 支持的 Broker 连接器

| 连接器 | 类型 | 交易能力 |
|--------|:----:|:--------:|
| IBKR (TWS/IB Gateway) | 本地 | 纸质/只读 |
| Robinhood | MCP | 有界自主交易 |
| Tiger | SDK | 纸质下单 |
| Alpaca | SDK | 纸质下单 |
| OKX | SDK | 纸质下单 |
| Binance | SDK | 纸质下单 |
| Futu | SDK | 纸质下单 |
| Longbridge | SDK | 只读 |
| Dhan | SDK | 纸质/只读 |
| Shoonya | SDK | 纸质/只读 |

***

## Output contract

执行命令后，按以下结构向用户交付结果：

1. **一句话结论** — 命令是否成功执行，关键结果摘要
2. **命令与参数** — 实际运行的命令，方便用户复现
3. **关键结果** — 表格或关键数值
4. **解释** — 结果的含义与局限
5. **下一步建议** — 可继续深入的操作

### 示例

```
✅ 成功运行 Alpha 基准测试

**命令**: `vibe-trading alpha bench --zoo gtja191 --universe csi300 --period 2018-2025 --top 20`

**结果摘要**:
- 测试 Zoo: gtja191（191 个因子）
- 市场: 沪深 300
- 周期: 2018-2025
- Top-20 因子已保存

**下一步建议**:
- `vibe-trading alpha show gtja191_171` 查看排名第一的因子详情
- `vibe-trading alpha compare gtja191_171 gtja191_111` 对比因子
```

***

## Error handling

### 常见问题处理

| 问题 | 处理方式 |
|------|---------|
| `vibe-trading` 命令未找到 | 提示安装 `pip install vibe-trading-ai` |
| 未初始化 `.env` | 运行 `vibe-trading init` |
| 命令执行超时 | 建议使用 `--max-iter` 限制迭代次数 |
| Connector 连接失败 | 检查 Broker 服务是否运行，`vibe-trading connector check` |
| 因子加载错误 | 使用 `--include-load-errors` 查看详细错误 |

### 部分成功原则

如果命令部分成功，不要说"成功完成"。
应明确说：

- 哪些部分成功
- 哪些部分失败
- 失败的可能原因与修复建议
