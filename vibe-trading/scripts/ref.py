#!/usr/bin/env python3
"""
Vibe-Trading Quick Reference Script
帮助快速查询 Vibe-Trading 命令与使用方式。
"""

import argparse
import json

REFERENCE = {
    "version": "0.1.9",
    "install": "pip install vibe-trading-ai",
    "init": "vibe-trading init",
    "commands": {
        "run": {
            "description": "运行一个提示/策略",
            "usage": "vibe-trading run -p <提示文本>",
            "options": {
                "-p, --prompt": "提示文本",
                "-f, --prompt-file": "从文件读取提示文本",
                "--max-iter": "最大 Agent 迭代次数",
                "--json": "输出 JSON 格式",
                "--no-rich": "禁用 Rich 格式化输出"
            },
            "examples": [
                'vibe-trading run -p "回测沪深300指数20日均线策略"',
                'vibe-trading run -f strategy.txt',
                'echo "分析 BTC 动量策略" | vibe-trading run'
            ]
        },
        "alpha": {
            "description": "Alpha Zoo 因子管理",
            "usage": "vibe-trading alpha <子命令> [选项]",
            "subcommands": {
                "list": "列出注册的 Alpha 因子",
                "show": "展示因子元数据和源码",
                "bench": "对因子 Zoo 做基准测试",
                "compare": "对比多个因子",
                "export-manifest": "导出注册清单为 JSON"
            },
            "zoos": {
                "qlib158": "154 个因子",
                "alpha101": "101 个因子",
                "gtja191": "191 个因子",
                "academic": "6 个因子"
            }
        },
        "connector": {
            "description": "交易连接器管理",
            "usage": "vibe-trading connector <子命令> [选项]",
            "subcommands": {
                "list": "列出可选连接器配置",
                "use": "选择默认连接器",
                "configure": "配置本地连接器",
                "check": "检查连接器就绪状态",
                "status": "显示连接器运行状态",
                "authorize": "授权远程 MCP 连接器",
                "account": "读取账户摘要",
                "positions": "读取当前持仓",
                "orders": "读取未成交订单",
                "quote": "读取实时报价",
                "history": "读取历史 K 线",
                "start": "启动连接器运行器",
                "stop": "停止连接器运行器",
                "halt": "触发紧急停止开关",
                "resume": "清除紧急停止开关",
                "revoke": "撤销 OAuth Token"
            }
        },
        "memory": {
            "description": "持久化记忆管理",
            "usage": "vibe-trading memory <子命令>",
            "subcommands": {
                "list": "列出记忆条目",
                "show": "查看单条记忆详情",
                "search": "搜索记忆",
                "forget": "删除记忆条目"
            }
        },
        "hypothesis": {
            "description": "假设注册表管理",
            "usage": "vibe-trading hypothesis <子命令>",
            "subcommands": {
                "list": "列出假设",
                "show": "查看假设详情",
                "invalidate": "标记假设为已拒绝"
            }
        },
        "swarm": {
            "description": "Swarm 多 Agent 交易团队",
            "usage": "vibe-trading --swarm-run PRESET",
            "presets": {
                "investment_committee": "多空辩论 → 风险评估",
                "quant_strategy_desk": "因子筛选 → 回测 → 风险审计",
                "crypto_trading_desk": "资金费率 + 清算 + 链上分析",
                "technical_analysis_panel": "多技术分析流派共识",
                "global_allocation_committee": "跨市场资产配置"
            }
        },
        "serve": {
            "description": "启动 API 服务器",
            "usage": "vibe-trading serve [--host HOST] [--port PORT] [--dev]",
            "defaults": {
                "host": "0.0.0.0",
                "port": 8899
            }
        },
        "list": {"description": "列出运行记录", "usage": "vibe-trading list"},
        "show": {"description": "查看运行详情", "usage": "vibe-trading show RUN_ID"},
        "chat": {"description": "交互式聊天模式", "usage": "vibe-trading chat"}
    }
}


def main():
    parser = argparse.ArgumentParser(description="Vibe-Trading 快速参考")
    parser.add_argument("topic", nargs="?", help="查询主题 (run/alpha/connector/memory/hypothesis/swarm/serve)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args()

    if args.json:
        print(json.dumps(REFERENCE, ensure_ascii=False, indent=2))
        return

    if args.topic:
        topic = args.topic.lower()
        if topic in REFERENCE["commands"]:
            info = REFERENCE["commands"][topic]
            print(f"=== {topic} ===\n")
            print(f"描述: {info['description']}")
            print(f"用法: {info['usage']}")
            if "options" in info:
                print("\n选项:")
                for opt, desc in info["options"].items():
                    print(f"  {opt:<20} {desc}")
            if "subcommands" in info:
                print("\n子命令:")
                for sub, desc in info["subcommands"].items():
                    print(f"  {sub:<20} {desc}")
            if "examples" in info:
                print("\n示例:")
                for ex in info["examples"]:
                    print(f"  $ {ex}")
            if "zoos" in info:
                print("\n内置 Zoo:")
                for z, c in info["zoos"].items():
                    print(f"  {z:<15} {c}")
            if "presets" in info:
                print("\nSwarm 预设:")
                for p, d in info["presets"].items():
                    print(f"  {p:<35} {d}")
        else:
            print(f"未知主题: {topic}")
            print(f"可用主题: {', '.join(REFERENCE['commands'].keys())}")
    else:
        print(f"Vibe-Trading 快速参考 v{REFERENCE['version']}")
        print(f"安装: {REFERENCE['install']}")
        print(f"初始化: {REFERENCE['init']}\n")
        print("可用主题:")
        for cmd, info in REFERENCE["commands"].items():
            print(f"  {cmd:<15} {info['description']}")
        print("\n使用: python3 ref.py <主题>")


if __name__ == "__main__":
    main()
