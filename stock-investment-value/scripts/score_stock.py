#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成长股打分脚本 —— 读取 fetch_fundamentals.py 输出目录，按 references/成长股.md 打分卡评分。

输入: 目录内
    derived_metrics.json   衍生指标（必读）
    fina_indicator.json    财务指标（用于取"最新年度"ROE/毛利率）
    cashflow.json          现金流量表（用于排雷项：连续2年经营现金流为负）

输出: score.json —— 各维度分数，每项含 {key, name, score, remark}
      remark 记录判断依据（真实数值 + 阈值 + 结论），全部锚定真实数据，不虚构。

用法:
    python score_stock.py --dir ./中际旭创
    python score_stock.py --dir ./中际旭创 --out ./中际旭创/score.json
    python score_stock.py --dir ./宁德时代 --short   # 只打印摘要

评分规则与阈值以 references/成长股.md 为准，不得临场改动。
"""

import argparse
import json
import os
import sys

# 维度常量（scores 每项的所属维度标识）
DIM_GROWTH = "成长性"
DIM_QUALITY = "盈利质量"
DIM_VALUATION = "估值吸引力"
DIM_HEALTH = "财务健康"
DIM_LIQUIDITY = "流动性与规模"


def load_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------- 分段打分工具 ----------
def tier(score: float, tiers: list, value, label: str, dimen: str) -> dict:
    """
    分段打分。tiers: [(下限, 得分, 结论), ...] 从高到低，取第一个命中。
    value=None -> 不可得，0 分并标注。
    返回 {key, name, dimen, score, remark}
    """
    if value is None:
        return {"key": label, "name": label, "dimen": dimen, "score": 0,
                "remark": "数据不可得，按 0 分计"}
    for lo, s, conclusion in tiers:
        if value >= lo:
            return {"key": label, "name": label, "dimen": dimen, "score": s,
                    "remark": f"数值 {value:.1f}，{conclusion}"}
    return {"key": label, "name": label, "dimen": dimen, "score": 0,
            "remark": f"数值 {value:.1f}，低于全部阈值"}


# ---------- 各维度打分 ----------
def score_growth(d: dict) -> list:
    """成长性（30 分）：营收/净利/持续年数/扣非"""
    items = []
    items.append(tier(10, [(20, 10, "≥20%"), (10, 7, "10–20%"), (0, 4, "0–10%")],
                      d.get("rev_yoy_avg3"), "rev_yoy_avg3", DIM_GROWTH))
    items[-1]["name"] = "近3年营收增速均值"
    items[-1]["remark"] = f"营收增速均值 {d['rev_yoy_avg3']:.1f}%，" + items[-1]["remark"].split("，", 1)[1] if d.get("rev_yoy_avg3") is not None else items[-1]["remark"]

    items.append(tier(10, [(25, 10, "≥25%"), (10, 7, "10–25%"), (0, 4, "0–10%")],
                      d.get("profit_yoy_avg3"), "profit_yoy_avg3", DIM_GROWTH))
    items[-1]["name"] = "近3年净利增速均值"
    if d.get("profit_yoy_avg3") is not None:
        items[-1]["remark"] = f"净利增速均值 {d['profit_yoy_avg3']:.1f}%，" + items[-1]["remark"].split("，", 1)[1]

    years = d.get("rev_positive_years")
    if years is None:
        items.append({"key": "rev_positive_years", "name": "近3年营收正增长年数", "dimen": DIM_GROWTH,
                      "score": 0, "remark": "数据不可得，按 0 分计"})
    else:
        s = {3: 5, 2: 3, 1: 1}.get(years, 0)
        items.append({"key": "rev_positive_years", "name": "近3年营收正增长年数", "dimen": DIM_GROWTH,
                      "score": s, "remark": f"正增长 {years} 年，得分 {s}"})

    items.append(tier(5, [(10, 5, "≥10%"), (0, 3, "0–10%")],
                      d.get("deducted_yoy_avg3"), "deducted_yoy_avg3", DIM_GROWTH))
    items[-1]["name"] = "近3年扣非增速均值"
    if d.get("deducted_yoy_avg3") is not None:
        items[-1]["remark"] = f"扣非增速均值 {d['deducted_yoy_avg3']:.1f}%，" + items[-1]["remark"].split("，", 1)[1]
    return items


def score_quality(d: dict, fina: dict) -> list:
    """盈利质量（20 分）：毛利率 / 现金流 / ROE（最新年度口径）"""
    items = []
    # 毛利率：derived 里是 latest 报告期；打分卡用最新报告期即可，但备注用年度值更稳妥
    gm = d.get("gross_margin")
    items.append(tier(5, [(40, 5, "≥40%"), (25, 3, "25–40%"), (10, 1, "10–25%")],
                      gm, "gross_margin", DIM_QUALITY))
    items[-1]["name"] = "毛利率"
    if gm is not None:
        items[-1]["remark"] = f"毛利率 {gm:.1f}%（最新报告期），" + items[-1]["remark"].split("，", 1)[1]

    ocf = d.get("ocf_to_np")
    items.append(tier(10, [(1, 10, "≥1（利润有真金白银）"), (0.5, 6, "0.5–1"), (0, 3, "0–0.5")],
                      ocf, "ocf_to_np", DIM_QUALITY))
    items[-1]["name"] = "经营现金流/归母净利"
    if ocf is not None:
        items[-1]["remark"] = f"经营现金流/净利 {ocf:.2f}，" + items[-1]["remark"].split("，", 1)[1]

    # ROE 用最新年度（fina_indicator annual 最后一条 1231）
    roe = None
    roe_end = None
    annual = (fina or {}).get("annual") or []
    for r in reversed(annual):
        if str(r.get("end_date", "")).endswith("1231"):
            roe = r.get("roe_waa")
            roe_end = r.get("end_date")
            break
    items.append(tier(5, [(15, 5, "≥15%"), (8, 3, "8–15%")], roe, "roe_waa", DIM_QUALITY))
    items[-1]["name"] = "加权ROE（最新年度）"
    if roe is not None:
        items[-1]["remark"] = f"年度 ROE {roe:.1f}%（{roe_end}），" + items[-1]["remark"].split("，", 1)[1]
    return items


def score_valuation(d: dict) -> list:
    """估值吸引力（30 分）：PEG + PE分位；一致预期 vs TTM 差距大时 PEG 降档"""
    items = []
    peg = d.get("peg")
    peg_note = d.get("peg_note", "")
    if peg is None:
        items.append({"key": "peg", "name": "PEG（混合PEG）", "dimen": DIM_VALUATION, "score": 0,
                      "remark": f"PEG 不适用：{peg_note}"})
    else:
        s = 15 if peg < 1 else (10 if peg < 1.5 else (5 if peg < 2 else 0))
        remark = f"PEG {peg:.2f}，{'<1 低估' if peg < 1 else ('1–1.5 合理' if peg < 1.5 else ('1.5–2 偏高' if peg < 2 else '>2 高估'))}"
        # 一致预期 vs TTM 差距 >15pp → 降一档（15→10）
        cg, ttmg = d.get("consensus_growth"), d.get("ttm_profit_yoy")
        if s == 15 and cg is not None and ttmg is not None and abs(cg - ttmg) > 15:
            s = 10
            remark += f"；一致预期({cg:.0f}%) vs TTM({ttmg:.0f}%) 差距>15pp，降一档"
        items.append({"key": "peg", "name": "PEG（混合PEG）", "dimen": DIM_VALUATION, "score": s,
                      "remark": remark + f"；口径 {d.get('growth_basis')}（{d.get('growth_period')}）"})

    pct = d.get("pe_ttm_percentile_5y")
    if pct is None:
        items.append({"key": "pe_ttm_percentile_5y", "name": "PE-TTM近5年分位", "dimen": DIM_VALUATION, "score": 0,
                      "remark": "分位数据不可得（样本<60交易日），按 0 分计"})
    else:
        s = 15 if pct < 25 else (10 if pct < 50 else (5 if pct < 75 else 0))
        label = "<25% 历史低位" if pct < 25 else ("25–50% 中低位" if pct < 50 else ("50–75% 中高位" if pct < 75 else ">75% 历史高位"))
        items.append({"key": "pe_ttm_percentile_5y", "name": "PE-TTM近5年分位", "dimen": DIM_VALUATION, "score": s,
                      "remark": f"分位 {pct:.1f}%（{label}）"})
    return items


def score_financial_health(d: dict, cashflow: list) -> tuple:
    """财务健康（15 分）：资产负债率 + 排雷项（扣分制）"""
    items = []
    debt = d.get("debt_to_assets")
    items.append(tier(10, [(80, 0, ">80%"), (60, 3, "60–80%"), (40, 6, "40–60%"), (0, 10, "<40%")],
                      debt, "debt_to_assets", DIM_HEALTH))
    items[-1]["name"] = "资产负债率"
    if debt is not None:
        items[-1]["remark"] = f"资产负债率 {debt:.1f}%，" + items[-1]["remark"].split("，", 1)[1]

    # 排雷：经营现金流连续 2 年为负（每项 2.5，最多扣 5）
    mine_score, mine_notes = 5, []
    annual_cf = [r for r in (cashflow or []) if str(r.get("end_date", "")).endswith("1231")]
    ocf_vals = [r.get("n_cashflow_act") for r in annual_cf if r.get("n_cashflow_act") is not None]
    if len(ocf_vals) >= 2 and ocf_vals[-1] < 0 and ocf_vals[-2] < 0:
        mine_score -= 2.5
        mine_notes.append("经营现金流连续2年为负，扣2.5分")
    if len(ocf_vals) >= 3 and all(v < 0 for v in ocf_vals[-3:]):
        mine_score -= 2.5
        mine_notes.append("经营现金流连续3年为负，再扣2.5分")
    mine_score = max(mine_score, 0)
    remark = "；".join(mine_notes) if mine_notes else "未触发排雷项"
    items.append({"key": "mine_check", "name": "排雷项", "dimen": DIM_HEALTH, "score": mine_score, "remark": remark})
    return items


def score_liquidity(d: dict) -> list:
    """流动性与规模（5 分）"""
    items = []
    amt = d.get("avg_daily_amount_yi")
    items.append(tier(3, [(1, 3, "≥1亿"), (0.3, 2, "0.3–1亿")], amt, "avg_daily_amount_yi", DIM_LIQUIDITY))
    items[-1]["name"] = "日均成交额"
    if amt is not None:
        items[-1]["remark"] = f"日均成交额 {amt:.1f}亿，" + items[-1]["remark"].split("，", 1)[1]

    mv = d.get("total_mv_yi")
    items.append(tier(2, [(100, 2, "≥100亿"), (30, 1, "30–100亿")], mv, "total_mv_yi", DIM_LIQUIDITY))
    items[-1]["name"] = "总市值"
    if mv is not None:
        items[-1]["remark"] = f"总市值 {mv:.0f}亿，" + items[-1]["remark"].split("，", 1)[1]
    return items


def main():
    parser = argparse.ArgumentParser(description="成长股打分（按 references/成长股.md）")
    parser.add_argument("--dir", required=True, help="fetch_fundamentals.py 输出目录")
    parser.add_argument("--out", default=None, help="输出 JSON 路径（默认 <dir>/score.json）")
    parser.add_argument("--short", action="store_true", help="只打印摘要")
    args = parser.parse_args()

    d = load_json(os.path.join(args.dir, "derived_metrics.json"))
    if d is None:
        print(f"[错误] {args.dir}/derived_metrics.json 不存在", file=sys.stderr)
        sys.exit(2)
    fina = load_json(os.path.join(args.dir, "fina_indicator.json"))
    cashflow = load_json(os.path.join(args.dir, "cashflow.json"))
    basic = load_json(os.path.join(args.dir, "basic.json")) or {}

    # ---- 各维度打分 ----
    g = score_growth(d)
    q = score_quality(d, fina)
    v = score_valuation(d)
    h = score_financial_health(d, cashflow or [])
    l = score_liquidity(d)

    all_scores = g + q + v + h + l
    dims = {
        "成长性": {"max": 30, "items": g},
        "盈利质量": {"max": 20, "items": q},
        "估值吸引力": {"max": 30, "items": v},
        "财务健康": {"max": 15, "items": h},
        "流动性与规模": {"max": 5, "items": l},
    }
    total = sum(s["score"] for s in all_scores)

    # ---- 评级与降档 ----
    flags = []
    if d.get("pe_ttm_percentile_5y") is None:
        flags.append("PE分位不可得（样本不足），综合评级自动降一档")
    rating, emoji = ("低估/优质", "🟢") if total >= 75 else (
        ("合理", "🟡") if total >= 60 else (("谨慎", "🟠") if total >= 45 else ("回避", "🔴")))
    if flags and rating == "低估/优质":
        rating, emoji = "合理", "🟡"
        flags.append("（已执行降档）")

    result = {
        "ts_code": basic.get("ts_code") or d.get("trade_date"),
        "name": basic.get("name"),
        "industry": basic.get("industry"),
        "trade_date": d.get("trade_date"),
        "total_score": round(total, 1),
        "max_score": 100,
        "rating": rating,
        "rating_emoji": emoji,
        "dimensions": {k: {"score": round(sum(i["score"] for i in vv["items"]), 1), "max": vv["max"]}
                       for k, vv in dims.items()},
        "scores": all_scores,
        "flags": flags,
        "disclaimer": "本评分仅为数据分析，不构成投资建议。所有分数锚定 tushare 真实数据，缺失按 0 分计。",
    }

    out_path = args.out or os.path.join(args.dir, "score.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- 输出 ----
    if args.short:
        print(f"{emoji} {basic.get('name')}（{basic.get('ts_code')}）综合 {total:.0f}/100 → {rating}")
        for k, vv in dims.items():
            print(f"  {k}: {sum(i['score'] for i in vv['items']):.0f}/{vv['max']}")
        for fl in flags:
            print(f"  ⚠ {fl}")
    else:
        print(f"\n{emoji} {basic.get('name')}（{basic.get('ts_code')}）综合 {total:.0f}/100 → {rating}")
        print("=" * 50)
        for k, vv in dims.items():
            print(f"\n【{k}】{sum(i['score'] for i in vv['items']):.0f}/{vv['max']}")
            for s in vv["items"]:
                print(f"  {s['key']} [{s['name']}] {s['score']}分 — {s['remark']}")
        for fl in flags:
            print(f"\n⚠ {fl}")
        print(f"\n免责声明：{result['disclaimer']}")
        print(f"已保存: {out_path}")


if __name__ == "__main__":
    main()
