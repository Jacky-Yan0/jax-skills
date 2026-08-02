#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成长股扫描脚本（双模式）:
  价值型(情形A): PEG < 1 且 PE-TTM 近5年分位 < 50%  —— 真便宜双重确认
  爆发型(情形B): 近2年每年净利/扣非增速>50% 且 营收>30%（业务扩张驱动爆发），
                 豁免分位，改用更严 PEG<0.5 + 绝对 PE-TTM<60 兜底
  模式: --mode value | burst | all（默认 all，任一通过即入选）

两阶段架构（尽量使用低频率限制接口）:
  阶段1: 全市场粗筛（仅 2~3 次低限制批量调用）
         - stock_basic      全市场股票列表（行业/上市日期）
         - daily_basic      最新交易日全市场估值快照（PE/PB/市值）
         过滤: 上市>3年、PE-TTM>0、PB>0、PE-TTM<150(--max-pe)、
               排除周期/金融行业黑名单、总市值>=200亿(--min-mv)
  阶段2: 候选池逐只精筛（对粗筛命中的股票，逐只调用，带延迟控制频率）
         - daily_basic(ts_code)  近5年历史估值序列 -> PE-TTM 分位数
         - fina_indicator(ts_code) 近3年年度财务 -> 增速均值 + 近2年逐年增速(爆发判定)
  输出: 命中清单(标注模式) + 详细筛选日志（每只: 选中/淘汰 + 原因）

用法:
    python scan_growth_a.py --outdir ./scan_result [--min-mv 200] [--max-pe 150]
    python scan_growth_a.py --mode burst --outdir ./scan_result   # 只扫爆发型
    python scan_growth_a.py --resume          # 复用上次缓存（中断后续跑）
    python scan_growth_a.py --list-only       # 只做阶段1粗筛
    python scan_growth_a.py --only-codes 300308.SZ,300750.SZ   # 指定候选精筛

日志: 每只候选打印 [阶段2] 选中/淘汰 + 模式 + 具体原因。
"""

import argparse
import json
import os
import sys
import time

import pandas as pd

try:
    import tushare as ts
except ImportError:
    print("缺少依赖 tushare，请先执行: pip install tushare pandas", file=sys.stderr)
    sys.exit(1)

# ---------- 配置 ----------
# 周期/金融行业黑名单（与 references/分类方法.md 排除项一致）
CYCLE_INDUSTRIES = {"煤炭", "钢铁", "有色金属", "化工", "石油", "基础化工", "建筑材料",
                    "交通运输", "航运", "船舶制造", "银行", "保险", "多元金融", "证券",
                    "房地产", "电力", "公用事业"}
# 阈值（与 references/成长股.md 一致）
MIN_LISTED_YEARS = 3          # 上市 >= 3 年
REV_YOY_MIN = 15.0            # 近3年营收增速均值 >= 15%
PROFIT_YOY_MIN = 20.0         # 近3年净利增速均值 >= 20%
DEDUCTED_MIN = 0.0            # 近3年扣非增速均值 > 0
PEG_MAX = 1.0                 # 情形A（价值）：PEG < 1
PE_PERCENTILE_MAX = 50.0      # 情形A（价值）：PE-TTM 近5年分位 < 50%
STAGE1_PE_MAX = 150.0         # 阶段1 统一 PE-TTM 上限：让 AI 爆发股（PE 70~150）
                              # 进入阶段2，由各模式判定（价值/爆发）严格把关
# 爆发型判定（情形B）——三维全过才判定：
#   近2年每年净利增速>50% + 近2年每年扣非增速>50% + 近2年每年营收增速>30%
BURST_PROFIT_YOY = 50.0       # 爆发型：净利增速下限/年
BURST_DEDUCTED_YOY = 50.0     # 爆发型：扣非增速下限/年
BURST_REV_YOY = 30.0          # 爆发型：营收增速下限/年
BURST_PEG_MAX = 0.5           # 爆发型：PEG < 0.5（更严，因豁免了分位）
BURST_PE_TTM_MAX = 60.0       # 爆发型：绝对 PE-TTM < 60（替代分位）
MIN_MV_YI = 200.0             # 总市值下限（亿元）：排除微盘/壳/退市风险区，留机构可操作空间
REQUEST_DELAY = 0.2           # 阶段2 逐只调用延迟（秒）。5000积分=500次/分钟，
                              # 每只2次调用，0.2s理论600次/分但含网络耗时实际约400-500，
                              # 配合自适应退避更稳妥。
HIST_YEARS = 5                # 历史分位窗口

CACHE_FILE = "scan_cache.json"  # 阶段2结果缓存（断点续跑）


def log(msg: str):
    print(msg, flush=True)


# 自适应退避：限频时动态延长延迟
_backoff_extra = 0.0  # 额外退避（秒）
_RETRY_SLEEP = 60     # 触发限频后暂停时长（秒）
_RETRY_LIMIT = 3      # 单次调用最大重试次数


def safe_call(pro, fn, label, *args, **kwargs):
    """包装接口调用：失败打印提示并返回 None；限频错误自动退避重试。"""
    for attempt in range(_RETRY_LIMIT + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            is_rate = ("频率" in msg or "频次" in msg or "超限" in msg)
            if is_rate and attempt < _RETRY_LIMIT:
                log(f"  [限频退避] {label} 触发频率限制，暂停 {_RETRY_SLEEP * (attempt + 1)}s 后重试...")
                time.sleep(_RETRY_SLEEP * (attempt + 1))
                continue
            log(f"  [警告] {label} 失败: {msg[:100]}")
            return None
    return None


# ---------- 阶段1: 全市场粗筛 ----------
def resolve_trade_date(pro, today: str) -> str:
    """找到最近一个交易日（含 today），避免周末/节假日取数失败。"""
    start = (pd.Timestamp(today) - pd.DateOffset(days=10)).strftime("%Y%m%d")
    cal = safe_call(pro, pro.trade_cal, "trade_cal", exchange="SSE",
                    start_date=start, end_date=today, fields="cal_date,is_open")
    if cal is None or cal.empty:
        return today
    opens = cal[cal["is_open"] == 1]["cal_date"].astype(str).tolist()
    return max(opens) if opens else today


def stage1_screen(pro, trade_date: str, min_mv: float, max_pe: float = STAGE1_PE_MAX):
    log(f"[阶段1] 全市场粗筛 trade_date={trade_date} ...")
    # 股票列表
    sb = safe_call(pro, pro.stock_basic, "stock_basic", exchange="", list_status="L",
                   fields="ts_code,name,industry,list_date")
    if sb is None or sb.empty:
        log("[阶段1] 股票列表获取失败，退出")
        sys.exit(3)
    log(f"  股票列表: {len(sb)} 只")
    # 最新估值快照
    db = safe_call(pro, pro.daily_basic, "daily_basic(全市场)", trade_date=trade_date,
                   fields="ts_code,pe_ttm,pb,total_mv")
    if db is None or db.empty:
        log("[阶段1] daily_basic 全市场快照失败，退出")
        sys.exit(3)
    log(f"  估值快照: {len(db)} 只")
    # 上市满 3 年
    cutoff = str(int(trade_date[:4]) - MIN_LISTED_YEARS) + trade_date[4:]
    sb = sb[sb["list_date"].astype(str) <= cutoff].copy()
    log(f"  上市>={MIN_LISTED_YEARS}年: {len(sb)} 只")
    # 合并估值
    m = sb.merge(db[["ts_code", "pe_ttm", "pb", "total_mv"]], on="ts_code", how="inner")
    # 过滤条件
    before = len(m)
    m = m[(m["pe_ttm"] > 0) & (m["pb"] > 0)]
    log(f"  PE-TTM>0 且 PB>0: {len(m)} 只（剔除 {before - len(m)}）")
    # PE-TTM 上限（砍掉微利超高估值）
    if max_pe and max_pe > 0:
        before = len(m)
        m = m[m["pe_ttm"] <= max_pe]
        log(f"  PE-TTM<={max_pe:.0f}: {len(m)} 只（剔除 {before - len(m)}）")
    # 行业黑名单
    m = m[~m["industry"].isin(CYCLE_INDUSTRIES)]
    log(f"  剔除周期/金融行业: {len(m)} 只")
    # 市值下限
    if min_mv and min_mv > 0:
        m = m[m["total_mv"] / 10000 >= min_mv]  # total_mv 单位万元
        log(f"  总市值>={min_mv:.0f}亿: {len(m)} 只")
    log(f"[阶段1] 粗筛完成，候选 {len(m)} 只")
    return m[["ts_code", "name", "industry", "list_date", "pe_ttm", "pb"]]


# ---------- 阶段2: 逐只精筛 ----------
def percentile_rank_5y(hist_df: pd.DataFrame, current: float) -> float | None:
    """当前值在近5年历史序列中的分位（只统计正值）。"""
    vals = hist_df["pe_ttm"].dropna()
    vals = vals[vals > 0]
    if len(vals) < 60:
        return None
    return round((vals <= current).sum() / len(vals) * 100, 1)


def avg_last_n(series: pd.Series, n: int = 3) -> float | None:
    """取最近 n 个非空值均值。"""
    vals = series.dropna()
    if len(vals) < 2:
        return None
    return float(vals[-n:].mean())


def is_burst_company(annual: pd.DataFrame) -> tuple[bool, str]:
    """
    爆发型判定：近2年【每年】净利增速>50% 且 扣非增速>50% 且 营收增速>30%（三维全过）。
    用"每年"不用"均值"：防止一年200%+一年0%的均值虚高。返回 (是否爆发, 原因)。
    """
    if len(annual) < 2:
        return False, "年度数据不足2年"
    last2 = annual.tail(2)
    cols = {"netprofit_yoy": "净利", "dt_netprofit_yoy": "扣非", "or_yoy": "营收"}
    thresholds = {"netprofit_yoy": BURST_PROFIT_YOY, "dt_netprofit_yoy": BURST_DEDUCTED_YOY,
                  "or_yoy": BURST_REV_YOY}
    details = []
    for col, name in cols.items():
        vals = last2[col].tolist()
        if any(v is None or pd.isna(v) for v in vals):
            return False, f"{name}增速数据缺失"
        if any(v <= thresholds[col] for v in vals):
            return False, f"近2年{name}增速 {[round(v,1) for v in vals]}% 未全过{thresholds[col]:.0f}%"
        details.append(f"{name}{[round(v,1) for v in vals]}%")
    return True, "；".join(details)


def stage2_inspect(pro, row, delay: float, mode: str = "all") -> dict:
    """
    对单只股票精筛（双模式）。row 为 namedtuple（itertuples）。
    mode: value=仅情形A | burst=仅情形B | all=两者任一通过即可
    返回 {pass, reason, mode, metrics}。
    """
    ts_code = row.ts_code
    # 历史估值序列 -> PE 分位（价值模式需要）
    pe_pct = None
    if mode in ("value", "all"):
        db = safe_call(pro, pro.daily_basic, f"daily_basic({ts_code})",
                       ts_code=ts_code, start_date=(pd.Timestamp.now() - pd.DateOffset(years=HIST_YEARS)).strftime("%Y%m%d"),
                       end_date=pd.Timestamp.now().strftime("%Y%m%d"), fields="trade_date,pe_ttm")
        time.sleep(delay)
        if db is None or db.empty:
            pe_pct = None
        else:
            pe_pct = percentile_rank_5y(db, float(row.pe_ttm))

    # 财务 -> 增速（两模式都需要）
    fi = safe_call(pro, pro.fina_indicator, f"fina_indicator({ts_code})",
                   ts_code=ts_code, start_date=(pd.Timestamp.now() - pd.DateOffset(years=4)).strftime("%Y%m%d"),
                   end_date=pd.Timestamp.now().strftime("%Y%m%d"),
                   fields="end_date,or_yoy,netprofit_yoy,dt_netprofit_yoy")
    time.sleep(delay)
    if fi is None or fi.empty:
        return {"pass": False, "reason": "无财务数据", "mode": None, "metrics": {"pe_pct": pe_pct}}
    annual = fi[fi["end_date"].astype(str).str.endswith("1231")].sort_values("end_date")
    rev_avg = avg_last_n(annual["or_yoy"])
    profit_avg = avg_last_n(annual["netprofit_yoy"])
    deducted_avg = avg_last_n(annual["dt_netprofit_yoy"])

    metrics = {"pe_pct": pe_pct, "pe_ttm": float(row.pe_ttm),
               "rev_avg": rev_avg, "profit_avg": profit_avg, "deducted_avg": deducted_avg}

    # 基础成长判定（两模式共同前提）
    base_fails = []
    if rev_avg is None or rev_avg < REV_YOY_MIN:
        base_fails.append(f"营收增速均值 {rev_avg if rev_avg is not None else 'NA'}% < {REV_YOY_MIN}%")
    if profit_avg is None or profit_avg < PROFIT_YOY_MIN:
        base_fails.append(f"净利增速均值 {profit_avg if profit_avg is not None else 'NA'}% < {PROFIT_YOY_MIN}%")
    if deducted_avg is None or deducted_avg <= DEDUCTED_MIN:
        base_fails.append(f"扣非增速均值 {deducted_avg if deducted_avg is not None else 'NA'}% <= {DEDUCTED_MIN}%")

    # ---- 情形B：爆发型（豁免分位，用更严 PEG + 绝对PE上限） ----
    if mode in ("burst", "all") and not base_fails:
        is_burst, burst_reason = is_burst_company(annual)
        if is_burst and profit_avg > 0:
            peg = float(row.pe_ttm) / profit_avg
            metrics["peg"] = round(peg, 2)
            metrics["is_burst"] = True
            burst_fails = []
            if peg >= BURST_PEG_MAX:
                burst_fails.append(f"PEG {peg:.2f} >= {BURST_PEG_MAX:.1f}")
            if float(row.pe_ttm) >= BURST_PE_TTM_MAX:
                burst_fails.append(f"PE-TTM {row.pe_ttm:.1f} >= {BURST_PE_TTM_MAX:.0f}")
            if not burst_fails:
                return {"pass": True, "reason": f"爆发型通过：{burst_reason}",
                        "mode": "burst", "metrics": metrics}
            return {"pass": False, "reason": f"爆发型：{burst_reason} 但 {'；'.join(burst_fails)}",
                    "mode": "burst", "metrics": metrics}

    # ---- 情形A：价值型（PEG<1 + 分位<50%） ----
    if mode in ("value", "all"):
        fails = list(base_fails)
        if profit_avg and profit_avg > 0:
            peg = float(row.pe_ttm) / profit_avg
            metrics["peg"] = round(peg, 2)
            if peg >= PEG_MAX:
                fails.append(f"PEG {peg:.2f} >= {PEG_MAX}")
        else:
            fails.append("PEG 不适用（增速<=0）")
        if pe_pct is None:
            fails.append("PE分位样本不足(<60交易日)")
        elif pe_pct >= PE_PERCENTILE_MAX:
            fails.append(f"PE分位 {pe_pct}% >= {PE_PERCENTILE_MAX}%")
        if not fails:
            return {"pass": True, "reason": "价值型全部通过", "mode": "value", "metrics": metrics}
        return {"pass": False, "reason": "；".join(fails), "mode": "value", "metrics": metrics}

    # mode=burst 且基础判定未过
    return {"pass": False, "reason": "；".join(base_fails) or "基础成长判定未过",
            "mode": mode, "metrics": metrics}


def main():
    parser = argparse.ArgumentParser(description="成长股扫描（双模式：价值型情形A + 爆发型情形B）")
    parser.add_argument("--outdir", default="./scan_result", help="输出目录")
    parser.add_argument("--min-mv", type=float, default=MIN_MV_YI, help="市值下限(亿元，默认200)")
    parser.add_argument("--max-pe", type=float, default=STAGE1_PE_MAX,
                        help=f"阶段1 PE-TTM上限(默认{STAGE1_PE_MAX:.0f})；传0=不设上限")
    parser.add_argument("--mode", choices=["value", "burst", "all"], default="all",
                        help="value=价值型(PEG<1+分位<50%) | burst=爆发型(PEG<0.5+PE<60) | all=两者任一")
    parser.add_argument("--limit", type=int, default=0, help="阶段2最多检查只数(0=不限)")
    parser.add_argument("--resume", action="store_true", help="复用上次缓存续跑")
    parser.add_argument("--list-only", action="store_true", help="只做阶段1粗筛")
    parser.add_argument("--only-codes", help="跳过阶段1，直接精筛指定代码(逗号分隔)")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="阶段2逐只调用延迟(秒)")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    token = os.getenv("TUSHARE_TOKEN") or ts.get_token()
    pro = ts.pro_api(token)
    trade_date = resolve_trade_date(pro, pd.Timestamp.now().strftime("%Y%m%d"))
    log(f"使用交易日: {trade_date}")
    cache_path = os.path.join(args.outdir, CACHE_FILE)
    cache = json.load(open(cache_path)) if args.resume and os.path.exists(cache_path) else {}

    # ---- 阶段1 ----
    # 阶段1 PE 上限统一（默认 150），可用 --max-pe 覆盖
    pe_cap = args.max_pe if args.max_pe and args.max_pe > 0 else 0
    log(f"阶段1 PE-TTM 上限: {pe_cap:.0f}（市值下限 {args.min_mv:.0f} 亿）")

    if args.only_codes:
        codes = [c.strip() for c in args.only_codes.split(",")]
        sb = safe_call(pro, pro.stock_basic, "stock_basic", exchange="", list_status="L",
                       fields="ts_code,name,industry,list_date")
        db = safe_call(pro, pro.daily_basic, "daily_basic(全市场)", trade_date=trade_date,
                       fields="ts_code,pe_ttm,pb,total_mv")
        cand = sb[sb["ts_code"].isin(codes)].merge(
            db[["ts_code", "pe_ttm", "pb", "total_mv"]], on="ts_code", how="inner")
        log(f"[阶段1] 跳过，直接精筛指定 {len(cand)} 只")
    elif args.list_only:
        stage1_screen(pro, trade_date, args.min_mv, pe_cap)
        return
    else:
        cand = stage1_screen(pro, trade_date, args.min_mv, pe_cap)

    # ---- 阶段2 ----
    log(f"[阶段2] 逐只精筛 {len(cand)} 只（延迟 {args.delay}s/次，模式 {args.mode}）")
    hits, reasons = [], {}
    for i, row in enumerate(cand.itertuples(), 1):
        tc = row.ts_code
        if tc in cache:  # 断点续跑
            res = cache[tc]
        else:
            res = stage2_inspect(pro, row, args.delay, args.mode)
            cache[tc] = res
        status = "✅选中" if res["pass"] else "❌淘汰"
        m = res["metrics"]
        mode_tag = f"[{res.get('mode')}]" if res.get("mode") else ""
        extra = ""
        if m:
            extra = (f"{mode_tag} | PE分位 {m.get('pe_pct')}% | 营收增速 {m.get('rev_avg') if m.get('rev_avg') is not None else 'NA'}%"
                     f" | 净利增速 {m.get('profit_avg') if m.get('profit_avg') is not None else 'NA'}%"
                     f" | PEG {m.get('peg', 'NA')}")
        log(f"  [{i}/{len(cand)}] {row.name}({tc}) {status} {extra}")
        if not res["pass"]:
            log(f"      ↳ 原因: {res['reason']}")
        if res["pass"]:
            hits.append({"ts_code": tc, "name": row.name, "industry": row.industry,
                         "mode": res.get("mode"), "pe_ttm": row.pe_ttm, **m})
        if args.limit and i >= args.limit:
            log(f"  [达到 --limit {args.limit}，停止]")
            break

    # 缓存落盘
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, default=str)

    # 结果
    log(f"\n===== 命中 {len(hits)} 只（模式 {args.mode}）=====")
    for h in sorted(hits, key=lambda x: (x.get("mode") != "value", x.get("peg", 999))):
        mode_tag = {"value": "价值", "burst": "爆发"}.get(h.get("mode"), h.get("mode"))
        print(f"  [{mode_tag}] {h['name']}({h['ts_code']}) {h['industry']} | PE-TTM {h['pe_ttm']}"
              f" | PEG {h.get('peg')} | PE分位 {h.get('pe_pct')}%")
    out = os.path.join(args.outdir, "hits.csv")
    if hits:
        pd.DataFrame(hits).to_csv(out, index=False, encoding="utf-8-sig")
        log(f"命中清单已保存: {out}")


if __name__ == "__main__":
    main()
