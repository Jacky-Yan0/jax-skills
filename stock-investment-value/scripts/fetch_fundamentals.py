#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成长股投资价值评估 —— 基本面数据拉取脚本（自包含，优先使用）

所有数字均来自 tushare 真实接口。脚本只计算客观指标（增速、PEG、分位数、
现金流质量等），不做任何"值不值得买"的主观判断；主观打分由评估框架完成。

用法:
    python fetch_fundamentals.py 300750.SZ [--outdir ./output]
    python fetch_fundamentals.py --name 宁德时代 [--outdir ./output]
    python fetch_fundamentals.py 300750.SZ --years 5 --outdir ./output

可选参数:
    --token XXX    tushare token（默认读环境变量 TUSHARE_TOKEN，再回退 ts.get_token()）
    --years N      历史估值序列年数（默认 5，用于算分位数）
    --outdir DIR   输出目录（默认 ./output）
    --no-score     不自动生成 score.json（默认执行完后自动调用 score_stock.py 打分）

输出文件（outdir 下）:
    basic.json             公司基本信息（名称/行业/上市日期）
    valuation.json         最新估值快照 + 近 N 年历史估值序列（pe_ttm/pb 等）
    fina_indicator.json    财务指标（年度 + 最新报告期）
    income.json            利润表（全部报告期：年报+季报，end_date 升序）
    cashflow.json          现金流量表（年度）
    dividend.json          分红送配历史
    daily.json             近 1 年日线行情（波动率/流动性）
    forecast.json          业绩预告历史（含净利变动区间与报告期覆盖）
    report_rc.json         券商研报一致预期（原始记录 + 聚合结果）
    derived_metrics.json   衍生指标（增速、PEG、估值分位数、现金流质量等）
                          —— 评估打分卡的数据来源

增速分母获取优先级（PEG 用，逐级回退并显式标注，见 references/通用指标与公式.md）:
    1. 一致预期增速（report_rc 券商研报聚合，前瞻）
    2. 业绩预告中值（forecast，仅当预告报告期不早于最新财报报告期）
    3. TTM 净利同比（income 单季滚动 12 个月，现实锚）
    4. 最新报告期累计同比 netprofit_yoy（标注报告期如 2026Q1）
    5. 近 3 年净利增速均值（兜底）
    口径与覆盖期写入 derived_metrics.json 的 growth_basis/growth_period/growth_note；
    同时输出 consensus_growth 与 ttm_profit_yoy 供"预期 vs 现实"对照。

失败处理: 单个接口失败不影响整体，对应文件内容为空并在终端提示；
任何缺失数据一律标记为 "数据不可得"，禁止用假设值补齐。
"""

import argparse
import json
import os
import subprocess
import sys

import pandas as pd

try:
    import tushare as ts
except ImportError:
    print("缺少依赖 tushare，请先执行: pip install tushare pandas", file=sys.stderr)
    sys.exit(1)


def init_pro(token: str | None):
    """初始化 tushare pro 接口。"""
    token = token or os.getenv("TUSHARE_TOKEN") or ts.get_token()
    if not token:
        print(
            "未找到 TUSHARE_TOKEN。请设置环境变量 TUSHARE_TOKEN，"
            "或用 --token 传入（注册: https://tushare.pro/register）",
            file=sys.stderr,
        )
        sys.exit(2)
    return ts.pro_api(token)


def safe_call(fn, *args, label: str, **kwargs):
    """包装单接口调用，失败打印提示并返回 None。"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        print(f"[警告] {label} 获取失败（数据不可得）: {e}", file=sys.stderr)
        return None


def to_records(df: pd.DataFrame | None) -> list:
    if df is None or df.empty:
        return []
    return df.where(pd.notna(df), None).to_dict(orient="records")


def fetch_basic(pro, ts_code: str, name: str | None):
    """公司基本信息；支持按名称反查代码。"""
    if name:
        df = safe_call(pro.stock_basic, name=name, list_status="L",
                       fields="ts_code,symbol,name,area,industry,market,list_date",
                       label="stock_basic(按名称)")
        if df is None or df.empty:
            df = safe_call(pro.stock_basic, name=name,
                           fields="ts_code,symbol,name,area,industry,market,list_date",
                           label="stock_basic(按名称,全部状态)")
        if df is None or df.empty:
            print(f"[错误] 未找到名称包含 '{name}' 的上市公司（数据不可得）", file=sys.stderr)
            sys.exit(3)
        row = df.iloc[0]
        return ts_code or row["ts_code"], row.to_dict()
    df = safe_call(pro.stock_basic, ts_code=ts_code,
                   fields="ts_code,symbol,name,area,industry,market,list_date",
                   label="stock_basic")
    if df is None or df.empty:
        print(f"[错误] 未找到 {ts_code} 的基本信息（数据不可得）", file=sys.stderr)
        sys.exit(3)
    return ts_code, df.iloc[0].to_dict()


def fetch_valuation(pro, ts_code: str, years: int):
    """最新估值 + 近 N 年历史估值序列（daily_basic）。"""
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime("%Y%m%d")
    fields = "ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv,circ_mv,turnover_rate"
    df = safe_call(pro.daily_basic, ts_code=ts_code, start_date=start, end_date=today,
                   fields=fields, label="daily_basic(历史估值)")
    if df is None or df.empty:
        return {"latest": {}, "history": []}
    df = df.sort_values("trade_date")
    latest = df.iloc[-1].where(pd.notna(df.iloc[-1]), None).to_dict()
    return {"latest": latest, "history": to_records(df)}


def fetch_fina_indicator(pro, ts_code: str, years: int):
    """财务指标：年度（end_date 以 1231 结尾）+ 最新报告期。"""
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime("%Y%m%d")
    fields = ("ts_code,ann_date,end_date,eps,roe,roe_waa,roa,grossprofit_margin,"
              "netprofit_margin,debt_to_assets,or_yoy,netprofit_yoy,dt_netprofit_yoy,ocfps")
    df = safe_call(pro.fina_indicator, ts_code=ts_code, start_date=start, end_date=today,
                   fields=fields, label="fina_indicator")
    if df is None or df.empty:
        return {"annual": [], "latest": {}}
    df = df.sort_values("end_date")
    annual = df[df["end_date"].astype(str).str.endswith("1231")].copy()
    latest = df.iloc[-1].where(pd.notna(df.iloc[-1]), None).to_dict()
    return {"annual": to_records(annual), "latest": latest}


def fetch_forecast(pro, ts_code: str):
    """业绩预告：按 ann_date 升序返回（JSON 按日期排序），同报告期+公告日去重（tushare 会重复返回）。"""
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=5)).strftime("%Y%m%d")  # 预告数据量小，放宽到 5 年保留完整历史
    fields = "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max"
    df = safe_call(pro.forecast, ts_code=ts_code, start_date=start, end_date=today,
                   fields=fields, label="forecast(业绩预告)")
    if df is None or df.empty:
        return []
    df = df.drop_duplicates(subset=["ann_date", "end_date"])  # tushare 会重复返回同一预告
    df = df.sort_values("ann_date")
    return to_records(df)


def fetch_report_rc(pro, ts_code: str):
    """
    券商研报一致预期（report_rc）。返回 dict：
    {
      "records": [...],          # 原始记录（仅保留关键字段）
      "forward_year": int|None,  # 一致预期对应预测年度
      "forward_np": float|None,  # 一致预期净利(万元)
      "n_orgs": int,             # 参与聚合的机构数
      "note": str
    }
    聚合规则：近 90 天研报，同机构取最新一份，每机构取最小未来年度(Q4)预测，
    至少 2 家机构才构成一致预期。频率限制 1 次/分钟，失败静默回退。
    """
    empty = {"records": [], "forward_year": None, "forward_np": None, "n_orgs": 0,
             "note": "report_rc 数据不可得（权限不足/频率受限/无研报覆盖）"}
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=2)).strftime("%Y%m%d")
    fields = "ts_code,report_date,org_name,quarter,np,eps,pe,rating"
    df = safe_call(pro.report_rc, ts_code=ts_code, start_date=start, end_date=today,
                   fields=fields, label="report_rc(券商一致预期)")
    if df is None or df.empty:
        return empty

    df = df.dropna(subset=["quarter", "np"])  # 只保留有年度预测与净利预测的行
    if df.empty:
        return empty

    # JSON 统一按 report_date 升序
    records = sorted(to_records(df), key=lambda r: str(r.get("report_date", "")))

    # 时间窗口：只取最近 90 天的研报（避免旧研报稀释），同机构取最新一份
    cutoff = (pd.Timestamp.now() - pd.DateOffset(days=90)).strftime("%Y%m%d")
    windowed = [r for r in records if str(r.get("report_date", "")) >= cutoff]
    if not windowed:
        empty["records"] = records
        empty["note"] = "近 90 天无研报覆盖"
        return empty

    # 每个机构只保留 report_date 最新的一份研报
    by_org = {}
    for r in windowed:
        org = r.get("org_name") or "unknown"
        cur = by_org.get(org)
        if cur is None or str(r["report_date"]) > str(cur["report_date"]):
            by_org[org] = r
    latest_reports = list(by_org.values())

    # 解析 quarter 中的年份（如 2026Q4 -> 2026）；只取 Q4（全年预测）
    def q_year(q):
        try:
            return int(str(q)[:4])
        except (ValueError, TypeError):
            return None

    this_year = pd.Timestamp.now().year
    per_org = {}  # org -> (forward_year, np)：该机构对未来最近年度的预测
    for r in latest_reports:
        y = q_year(r.get("quarter"))
        if y is None or not str(r.get("quarter")).endswith("Q4"):
            continue
        if y < this_year:
            continue
        org = r.get("org_name") or "unknown"
        # 同一研报含多年预测（2026/2027/2028），取最小的未来年度
        if org not in per_org or y < per_org[org][0]:
            per_org[org] = (y, r.get("np"))

    if not per_org:
        empty["records"] = records
        empty["note"] = "研报无未来年度(Q4)净利预测"
        return empty

    # 一致预期：各机构对同一 forward_year 的 np 取均值（单位：万元）
    forward_year = min(y for y, _ in per_org.values())
    nps = [v for y, v in per_org.values() if y == forward_year and v is not None and v > 0]
    if len(nps) < 2:  # 至少 2 家机构才叫"一致"
        empty["records"] = records
        empty["note"] = f"近90天预测 {forward_year} 的机构数不足 2 家（{len(nps)}），不构成一致预期"
        return empty

    forward_np = sum(nps) / len(nps)

    return {
        "records": sorted(records, key=lambda r: str(r.get("report_date", ""))),
        "forward_year": forward_year,
        "forward_np": round(forward_np, 0),
        "n_orgs": len(nps),
        "note": f"近90天 {len(nps)} 家机构一致预期净利({forward_year})均值 {forward_np/1e4:.0f} 亿元",
    }


def fetch_income(pro, ts_code: str, years: int):
    """利润表（全部报告期：年报+季报）：按 end_date 升序，同一报告期按 ann_date 取最新（去重）。"""
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime("%Y%m%d")
    fields = "ts_code,ann_date,end_date,total_revenue,revenue,operate_profit,total_profit,n_income,n_income_attr_p"
    df = safe_call(pro.income, ts_code=ts_code, start_date=start, end_date=today,
                   fields=fields, label="income")
    if df is None or df.empty:
        return []
    df = (df.sort_values(["end_date", "ann_date"])
            .drop_duplicates("end_date", keep="last")
            .sort_values("end_date"))
    return to_records(df)


def fetch_income_quarterly(pro, ts_code: str, years: int):
    """
    单季合并利润表（report_type='2'），用于 TTM 计算。
    同一 end_date 可能有多条（重述），按 ann_date 取最新。
    """
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime("%Y%m%d")
    fields = "ts_code,ann_date,end_date,n_income_attr_p"
    df = safe_call(pro.income, ts_code=ts_code, start_date=start, end_date=today,
                   report_type="2", fields=fields, label="income(单季, TTM计算)")
    if df is None or df.empty:
        return []
    df = df.sort_values(["end_date", "ann_date"]).drop_duplicates("end_date", keep="last")
    df = df.sort_values("end_date")
    return to_records(df)


def fetch_cashflow(pro, ts_code: str, years: int):
    """现金流量表（年度）：按 end_date 升序，同一报告期按 ann_date 取最新（去重）。"""
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=years)).strftime("%Y%m%d")
    fields = "ts_code,ann_date,end_date,n_cashflow_act,c_fr_sale_sg"
    df = safe_call(pro.cashflow, ts_code=ts_code, start_date=start, end_date=today,
                   fields=fields, label="cashflow")
    if df is None or df.empty:
        return []
    annual = df[df["end_date"].astype(str).str.endswith("1231")]
    annual = (annual.sort_values(["end_date", "ann_date"])
                    .drop_duplicates("end_date", keep="last")
                    .sort_values("end_date"))
    return to_records(annual)


def fetch_dividend(pro, ts_code: str):
    """分红送配历史：按 end_date 升序。"""
    fields = "ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date"
    df = safe_call(pro.dividend, ts_code=ts_code, fields=fields, label="dividend")
    if df is None or df.empty:
        return []
    df = df.sort_values("end_date")
    return to_records(df)


def fetch_daily(pro, ts_code: str):
    """近 1 年日线行情（波动率/流动性）。"""
    today = pd.Timestamp.now().strftime("%Y%m%d")
    start = (pd.Timestamp.now() - pd.DateOffset(years=1)).strftime("%Y%m%d")
    df = safe_call(pro.daily, ts_code=ts_code, start_date=start, end_date=today,
                   fields="trade_date,close,vol,amount", label="daily(近1年)")
    if df is None or df.empty:
        return []
    df = df.sort_values("trade_date")
    return to_records(df)


def mean_of_last_n(records: list, key: str, n: int = 3) -> float | None:
    """取最近 n 个非空值的均值（用于年度增速）。"""
    vals = [r.get(key) for r in records if r.get(key) is not None]
    if len(vals) < 2:
        return None
    return sum(vals[-n:]) / len(vals[-n:])


def percentile_rank(history: list, current: float | None, key: str) -> float | None:
    """当前值在历史序列中的分位数（0-100）。只统计正数（PE 亏损期为负无意义）。"""
    if current is None or pd.isna(current) or current <= 0:
        return None
    vals = [r[key] for r in history if r.get(key) is not None and r[key] > 0]
    if len(vals) < 60:  # 样本不足（如次新股），标记为不可得
        return None
    return round(sum(1 for v in vals if v <= current) / len(vals) * 100, 1)


def report_period_label(end_date: str | None) -> str:
    """把 end_date(YYYYMMDD) 转成人类可读的报告期描述，如 '2026Q1（1-3月累计）'。"""
    if not end_date:
        return "报告期未知"
    s = str(end_date)
    month = int(s[4:6])
    months = {3: "1-3月", 6: "1-6月", 9: "1-9月", 12: "全年"}
    label = months.get(month, f"前{month}月")
    quarter = {3: "Q1", 6: "H1", 9: "Q3", 12: "FY"}.get(month, "")
    return f"{s[:4]}{quarter}（{label}累计）"


_QUARTER_END_DAY = {3: 31, 6: 30, 9: 30, 12: 31}


def _quarter_windows(end_date: str):
    """以 end_date(YYYYMMDD) 为截止的 4 个季度 end_date，及去年同期的 4 个季度。"""
    y, m = int(end_date[:4]), int(end_date[4:6])
    cur, prev = [], []
    cy, cm = y, m
    for _ in range(4):
        cur.append(f"{cy}{cm:02d}{_QUARTER_END_DAY[cm]}")
        cm = cm - 3 if cm > 3 else 12
        if cm == 12:
            cy -= 1
    py, pm = y - 1, m
    for _ in range(4):
        prev.append(f"{py}{pm:02d}{_QUARTER_END_DAY[pm]}")
        pm = pm - 3 if pm > 3 else 12
        if pm == 12:
            py -= 1
    return cur, prev


def compute_ttm_profit_yoy(quarterly: list) -> dict:
    """
    TTM 净利同比：最新 4 个单季之和 ÷ 去年同期 4 个单季之和 − 1。
    返回 {ttm_profit_yoy, ttm_window, prev_window, note}；数据不足返回 None。
    """
    empty = {"ttm_profit_yoy": None, "ttm_window": [], "prev_window": [],
             "note": "单季数据不足 8 个季度（次新股常见），TTM 同比不可得"}
    if not quarterly:
        return empty
    q = {str(r["end_date"]): r.get("n_income_attr_p") for r in quarterly}
    latest = max(q)
    cur_w, prev_w = _quarter_windows(latest)
    cur = sum(q[k] for k in cur_w if k in q)
    prev = sum(q[k] for k in prev_w if k in q)
    # 窗口必须完整（4+4 个季度都在）
    if not all(k in q for k in cur_w) or not all(k in q for k in prev_w):
        return empty
    if prev <= 0:
        return {"ttm_profit_yoy": None, "ttm_window": cur_w, "prev_window": prev_w,
                "note": "去年同期 TTM 净利 ≤ 0，同比无意义"}
    return {
        "ttm_profit_yoy": round((cur / prev - 1) * 100, 2),
        "ttm_window": cur_w,
        "prev_window": prev_w,
        "note": f"TTM({cur_w[0][:4]}年{int(cur_w[0][4:6])}月截止) {cur/1e8:.1f}亿 vs "
                f"去年同期 {prev/1e8:.1f}亿",
    }


def compute_consensus_growth(consensus: dict, annual_income: list) -> dict:
    """
    一致预期增速 = 一致预期净利(forward_year) ÷ 前一年实际年报净利 − 1。
    annual_income: income.json 年度记录（n_income_attr_p 单位：元）。
    返回 {consensus_growth, forward_year, forward_np(亿元), base_np(亿元), note}。
    """
    if not consensus or not consensus.get("forward_np"):
        return {"consensus_growth": None, "forward_year": None,
                "forward_np": None, "base_np": None,
                "note": consensus.get("note", "一致预期不可得") if consensus else "一致预期不可得"}
    fy = consensus["forward_year"]
    base_year = f"{fy - 1}1231"
    base_rec = next((r for r in annual_income if str(r.get("end_date")) == base_year
                     and r.get("n_income_attr_p")), None)
    if base_rec is None:
        return {"consensus_growth": None, "forward_year": fy,
                "forward_np": consensus["forward_np"] / 1e4,
                "base_np": None,
                "note": f"缺少基准年度 {fy - 1} 实际年报净利，一致预期增速不可得"}
    forward_wan = consensus["forward_np"]
    base_wan = base_rec["n_income_attr_p"] / 1e4  # 元 -> 万元
    return {
        "consensus_growth": round((forward_wan / base_wan - 1) * 100, 2),
        "forward_year": fy,
        "forward_np": round(forward_wan / 1e4, 1),  # 亿元
        "base_np": round(base_wan / 1e4, 1),        # 亿元
        "n_orgs": consensus.get("n_orgs"),
        "note": f"一致预期净利({fy}) {forward_wan/1e4:.0f}亿 vs 实际年报({fy-1}) {base_wan/1e4:.0f}亿",
    }


def pick_growth_proxy(consensus: dict, fina_latest: dict, forecast: list,
                      ttm: dict, annual_avg3: float | None) -> dict:
    """
    选择用于 PEG 的增速分母（混合 PEG，逐级回退，显式标注口径与覆盖期）：

    1. 一致预期增速（report_rc 券商研报聚合，前瞻）—— 最贴近 Lynch 原意
    2. 业绩预告中值（p_change_min/max 均值）
       —— 仅当预告的报告期( end_date ) 不早于最新已披露财报的报告期时采用，
          否则视为过期预告（如只有上年年报预告而最新财报已到今年Q1）。
    3. TTM 净利同比（income 单季滚动 12 个月，现实锚）
    4. fina_indicator 最新报告期累计同比（netprofit_yoy）
       —— 标注报告期（如 2026Q1（1-3月累计）），季节性强弱一目了然。
    5. 近 3 年净利增速均值（兜底）。

    返回 dict：{growth, period_label, basis, note, trace}
    trace 为分级计算日志（供终端展示降级原因）。
    """
    trace = []

    def log(level: str, status: str, detail: str):
        trace.append({"level": level, "status": status, "detail": detail})

    # 1) 一致预期增速
    cg = consensus.get("consensus_growth") if consensus else None
    if cg is not None and cg > 0:
        log("1.一致预期", "采用",
            f"{cg}%（{consensus.get('n_orgs')} 家机构预测 {consensus.get('forward_year')} 年）")
        return {
            "growth": cg,
            "period_label": f"{consensus.get('forward_year')}年度",
            "basis": "consensus",
            "note": f"券商一致预期净利增速（{consensus.get('n_orgs')} 家机构，"
                    f"预测 {consensus.get('forward_year')} 年）；{consensus.get('note')}",
            "trace": trace,
        }
    log("1.一致预期", "降级",
        (consensus or {}).get("note", "report_rc 数据不可得"))

    latest_eps_date = fina_latest.get("end_date")

    # 2) 业绩预告
    if forecast:
        newest = max(forecast, key=lambda r: str(r.get("ann_date", "")))  # 已按 ann_date 升序，取最新
        fc_end, fc_ann = newest.get("end_date"), newest.get("ann_date")
        pmin, pmax = newest.get("p_change_min"), newest.get("p_change_max")
        # 预告报告期不早于最新财报报告期 且 区间可用
        if pmin is not None and pmax is not None and fc_end:
            stale = latest_eps_date and str(fc_end) < str(latest_eps_date)
            if not stale:
                mid = round((pmin + pmax) / 2, 2)
                log("2.业绩预告", "采用",
                    f"净利变动 {pmin}%~{pmax}% 取中值 {mid}%（公告 {fc_ann}）")
                return {
                    "growth": mid,
                    "period_label": report_period_label(fc_end),
                    "basis": "forecast",
                    "note": f"业绩预告净利变动区间 {pmin}%~{pmax}%，取中值；公告日 {fc_ann}",
                    "trace": trace,
                }
            log("2.业绩预告", "降级", f"预告报告期 {fc_end} 早于最新财报 {latest_eps_date}（已过期）")
        else:
            log("2.业绩预告", "降级", "预告无净利变动区间（p_change 缺失）")
    else:
        log("2.业绩预告", "降级", "无业绩预告数据")

    # 3) TTM 净利同比
    ttm_growth = ttm.get("ttm_profit_yoy") if ttm else None
    if ttm_growth is not None and ttm_growth > 0:
        log("3.TTM净利同比", "采用", f"{ttm_growth}%（{ttm.get('note')}）")
        return {
            "growth": ttm_growth,
            "period_label": "滚动12个月(TTM)",
            "basis": "ttm",
            "note": f"TTM 净利同比（{ttm.get('note')}）",
            "trace": trace,
        }
    log("3.TTM净利同比", "降级", (ttm or {}).get("note", "TTM 数据不可得"))

    # 4) 最新报告期累计同比
    latest_yoy = fina_latest.get("netprofit_yoy")
    if latest_yoy is not None and latest_eps_date:
        log("4.最新报告期累计同比", "采用",
            f"{latest_yoy}%（报告期 {report_period_label(latest_eps_date)}）")
        return {
            "growth": latest_yoy,
            "period_label": report_period_label(latest_eps_date),
            "basis": "latest_period",
            "note": f"最新报告期累计净利同比；报告期 {report_period_label(latest_eps_date)}",
            "trace": trace,
        }
    log("4.最新报告期累计同比", "降级", "最新报告期 netprofit_yoy 缺失")

    # 5) 3 年均值兜底
    if annual_avg3 is not None:
        log("5.近3年均值(兜底)", "采用", f"{annual_avg3}%")
        return {
            "growth": annual_avg3,
            "period_label": "近3个年度",
            "basis": "hist_avg3",
            "note": "以近3年净利增速均值为代理（无一致预期/预告/TTM/最新报告期数据）",
            "trace": trace,
        }
    log("5.近3年均值(兜底)", "不可得", "年度增速数据缺失")

    return {"growth": None, "period_label": None, "basis": "unavailable",
            "note": "增速数据不可得，PEG 不适用", "trace": trace}


def compute_derived(valuation, fina, income, cashflow, daily, forecast, consensus_raw, ttm):
    """由真实数据计算衍生指标（供打分卡引用）。"""
    d = {}
    latest_v = valuation.get("latest") or {}

    # ---- 估值快照 ----
    d["pe_ttm"] = latest_v.get("pe_ttm")
    d["pe"] = latest_v.get("pe")
    d["pb"] = latest_v.get("pb")
    d["ps_ttm"] = latest_v.get("ps_ttm")
    d["dv_ttm"] = latest_v.get("dv_ttm")  # 股息率 %
    d["total_mv_yi"] = (latest_v.get("total_mv") or 0) / 10000 if latest_v.get("total_mv") else None  # 万元->亿元
    d["trade_date"] = latest_v.get("trade_date")

    # ---- 历史估值分位数（近 N 年） ----
    hist = valuation.get("history") or []
    d["pe_ttm_percentile_5y"] = percentile_rank(hist, d["pe_ttm"], "pe_ttm")
    d["pb_percentile_5y"] = percentile_rank(hist, d["pb"], "pb")

    # ---- 成长性（年度增速均值，最近 3 年） ----
    annual = fina.get("annual") or []
    d["rev_yoy_avg3"] = mean_of_last_n(annual, "or_yoy")
    d["profit_yoy_avg3"] = mean_of_last_n(annual, "netprofit_yoy")
    d["deducted_yoy_avg3"] = mean_of_last_n(annual, "dt_netprofit_yoy")
    rev_yoy_hist = [r.get("or_yoy") for r in annual if r.get("or_yoy") is not None]
    d["rev_positive_years"] = sum(1 for v in rev_yoy_hist[-3:] if v > 0) if rev_yoy_hist else 0

    # ---- 一致预期增速（前瞻，PEG 首选分母） ----
    consensus = compute_consensus_growth(consensus_raw, income)
    d["consensus_growth"] = consensus["consensus_growth"]
    d["consensus_forward_year"] = consensus["forward_year"]
    d["consensus_forward_np"] = consensus["forward_np"]
    d["consensus_base_np"] = consensus["base_np"]
    d["consensus_note"] = consensus["note"]
    d["consensus_n_orgs"] = (consensus_raw or {}).get("n_orgs")

    # ---- 对照口径：TTM 实际增速（"预期 vs 现实"） ----
    d["ttm_profit_yoy"] = ttm.get("ttm_profit_yoy") if ttm else None
    d["ttm_note"] = ttm.get("note") if ttm else "TTM 数据不可得"

    # ---- 增速分母（供 PEG，5 级回退：一致预期→预告→TTM→累计同比→3年均值） ----
    proxy = pick_growth_proxy(consensus, fina.get("latest") or {}, forecast,
                              ttm, d["profit_yoy_avg3"])
    d["growth_proxy"] = proxy["growth"]
    d["growth_period"] = proxy["period_label"]
    d["growth_basis"] = proxy["basis"]
    d["growth_note"] = proxy["note"]
    d["growth_trace"] = proxy["trace"]  # 分级计算日志（降级原因），供终端展示
    # 参考口径：最新报告期同比 与 3年均值（敏感性对比）
    d["profit_yoy_latest"] = (fina.get("latest") or {}).get("netprofit_yoy")
    d["profit_yoy_latest_period"] = report_period_label((fina.get("latest") or {}).get("end_date"))

    # ---- PEG（增速代理 > 0 且 PE-TTM > 0 才计算） ----
    growth_proxy = d["growth_proxy"]
    if growth_proxy is not None and growth_proxy > 0 and d["pe_ttm"] and d["pe_ttm"] > 0:
        d["peg"] = round(d["pe_ttm"] / growth_proxy, 2)
        d["peg_note"] = f"PEG 增速代理：{d['growth_basis']}（{d['growth_period']}）— {d['growth_note']}"
    else:
        d["peg"] = None
        d["peg_note"] = f"增速为负/缺失或 PE 非正，PEG 不适用（增速代理：{d['growth_basis']}，{d['growth_note']}）"

    # ---- 盈利质量 ----
    fin_latest = fina.get("latest") or {}
    d["gross_margin"] = fin_latest.get("grossprofit_margin")
    d["net_margin"] = fin_latest.get("netprofit_margin")
    d["roe_waa"] = fin_latest.get("roe_waa")
    d["debt_to_assets"] = fin_latest.get("debt_to_assets")
    # 经营现金流/归母净利润（最近年度：双方都用最新年报，口径一致）
    annual_income = [r for r in income if str(r.get("end_date", "")).endswith("1231")]
    if cashflow and annual_income:
        latest_yr = annual_income[-1]  # 最新年报（income 已按 end_date 升序）
        cf_act = latest_yr.get("n_income_attr_p")
        ocf = next((r.get("n_cashflow_act") for r in reversed(cashflow)
                    if r.get("end_date") == latest_yr.get("end_date")), None)
        if ocf is None and cashflow:
            ocf = cashflow[-1].get("n_cashflow_act")
        if cf_act and ocf and cf_act > 0:
            d["ocf_to_np"] = round(ocf / cf_act, 2)
        else:
            d["ocf_to_np"] = None

    # ---- 流动性/波动 ----
    if daily:
        closes = pd.Series([r["close"] for r in daily if r.get("close") is not None])
        amounts = pd.Series([r["amount"] for r in daily if r.get("amount") is not None])
        if len(closes) > 30:
            ret = closes.pct_change().dropna()
            d["volatility_annual"] = round(float(ret.std() * (252 ** 0.5) * 100), 1)  # %
        else:
            d["volatility_annual"] = None
        d["avg_daily_amount_yi"] = round(float(amounts.mean()) * 1000 / 1e8, 2) if len(amounts) else None  # 千元->亿元
    else:
        d["volatility_annual"] = None
        d["avg_daily_amount_yi"] = None

    # ---- 分红 ----
    d["div_years_cash"] = None  # 由 dividend 数据在 main 中填充

    return d


def clean_nan(obj):
    """递归把 float('nan') 替换为 None，保证 JSON 合法。"""
    if isinstance(obj, float) and obj != obj:  # NaN != NaN
        return None
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj


def write_json(path: str, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean_nan(obj), f, ensure_ascii=False, indent=2, default=str)


# 衍生指标中文标签（终端摘要用）：字段名 -> 中文名（英文缩写）
METRIC_LABELS = {
    "pe_ttm": "市盈率TTM (PE-TTM)",
    "pe": "市盈率静态 (PE)",
    "pb": "市净率 (PB)",
    "ps_ttm": "市销率TTM (PS-TTM)",
    "dv_ttm": "股息率TTM (Dividend Yield)",
    "total_mv_yi": "总市值 (Total MV, 亿元)",
    "trade_date": "数据截止日 (Trade Date)",
    "pe_ttm_percentile_5y": "PE-TTM近5年分位 (PE-TTM Percentile)",
    "pb_percentile_5y": "PB近5年分位 (PB Percentile)",
    "rev_yoy_avg3": "近3年营收增速均值 (Revenue YoY Avg3)",
    "profit_yoy_avg3": "近3年净利增速均值 (Profit YoY Avg3)",
    "deducted_yoy_avg3": "近3年扣非增速均值 (Deducted YoY Avg3)",
    "rev_positive_years": "近3年营收正增长年数 (Positive Growth Years)",
    "consensus_growth": "一致预期增速 (Consensus Growth)",
    "consensus_forward_year": "一致预期预测年度 (Forward Year)",
    "consensus_forward_np": "一致预期净利 (Consensus NP, 亿元)",
    "consensus_base_np": "基准年净利 (Base NP, 亿元)",
    "consensus_n_orgs": "覆盖机构数 (Coverage Orgs)",
    "consensus_note": "一致预期说明 (Consensus Note)",
    "ttm_profit_yoy": "TTM净利同比 (TTM Profit YoY)",
    "ttm_note": "TTM说明 (TTM Note)",
    "growth_proxy": "PEG增速分母 (Growth Proxy)",
    "growth_period": "增速覆盖期 (Growth Period)",
    "growth_basis": "增速口径 (Growth Basis)",
    "growth_note": "增速说明 (Growth Note)",
    "profit_yoy_latest": "最新报告期净利同比 (Latest Profit YoY)",
    "profit_yoy_latest_period": "最新报告期 (Latest Period)",
    "peg": "PEG (混合PEG)",
    "peg_note": "PEG说明 (PEG Note)",
    "gross_margin": "毛利率 (Gross Margin)",
    "net_margin": "净利率 (Net Margin)",
    "roe_waa": "加权ROE (ROE)",
    "debt_to_assets": "资产负债率 (Debt/Assets)",
    "ocf_to_np": "经营现金流/归母净利 (OCF/NP)",
    "volatility_annual": "年化波动率 (Annualized Vol)",
    "avg_daily_amount_yi": "日均成交额 (Avg Daily Amount, 亿元)",
    "div_years_cash": "现金分红年数 (Cash Div Years)",
    "div_latest_cash_div": "最新现金分红 (Latest Cash Div)",
}


def run_score(outdir: str):
    """调用 score_stock.py 自动打分，生成 <outdir>/score.json（仅读本地 JSON，无网络调用）。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "score_stock.py")
    if not os.path.exists(script):
        print("[提示] scripts/score_stock.py 不存在，跳过自动打分")
        return
    try:
        r = subprocess.run([sys.executable, script, "--dir", outdir, "--short"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            print(r.stdout, end="")
        else:
            print(f"[警告] 自动打分失败: {(r.stderr or r.stdout)[:200]}")
    except Exception as e:
        print(f"[警告] 自动打分异常: {e}")


def main():
    parser = argparse.ArgumentParser(description="成长股基本面数据拉取（tushare）")
    parser.add_argument("ts_code", nargs="?", help="股票代码，如 300750.SZ")
    parser.add_argument("--name", help="股票名称，如 宁德时代（与 ts_code 二选一）")
    parser.add_argument("--token", help="tushare token（默认读环境变量 TUSHARE_TOKEN）")
    parser.add_argument("--years", type=int, default=5, help="历史估值序列年数（默认 5）")
    parser.add_argument("--outdir", default="./output", help="输出目录（默认 ./output）")
    parser.add_argument("--no-score", action="store_true", help="不自动生成 score.json")
    args = parser.parse_args()

    if not args.ts_code and not args.name:
        parser.error("必须提供 ts_code 或 --name")

    pro = init_pro(args.token)
    os.makedirs(args.outdir, exist_ok=True)

    ts_code, basic = fetch_basic(pro, args.ts_code, args.name)
    print(f"标的: {basic.get('name')}（{ts_code}） 行业: {basic.get('industry')} "
          f"上市: {basic.get('list_date')}")

    valuation = fetch_valuation(pro, ts_code, args.years)
    fina = fetch_fina_indicator(pro, ts_code, args.years)
    income = fetch_income(pro, ts_code, args.years)
    cashflow = fetch_cashflow(pro, ts_code, args.years)
    dividend = fetch_dividend(pro, ts_code)
    daily = fetch_daily(pro, ts_code)
    forecast = fetch_forecast(pro, ts_code)
    consensus = fetch_report_rc(pro, ts_code)
    quarterly = fetch_income_quarterly(pro, ts_code, args.years)
    ttm = compute_ttm_profit_yoy(quarterly)

    derived = compute_derived(valuation, fina, income, cashflow, daily,
                              forecast, consensus, ttm)
    if dividend:
        cash_years = sum(1 for r in dividend if (r.get("cash_div") or 0) > 0)
        derived["div_years_cash"] = cash_years
        derived["div_latest_cash_div"] = dividend[0].get("cash_div")

    files = {
        "basic.json": basic,
        "valuation.json": valuation,
        "fina_indicator.json": fina,
        "income.json": income,
        "cashflow.json": cashflow,
        "dividend.json": dividend,
        "daily.json": daily,
        "forecast.json": forecast,
        "report_rc.json": consensus,
        "derived_metrics.json": derived,
    }
    for name, obj in files.items():
        write_json(os.path.join(args.outdir, name), obj)

    derived = clean_nan(derived)
    d = derived  # 简写

    # ========== 第一部分：计算日志（过程信息） ==========
    print("\n--- 计算日志 ---")

    # 增速分母分级
    print("[PEG 增速分母] 5 级优先级链计算：")
    for step in d.get("growth_trace", []):
        mark = {"采用": "✓", "降级": "✗", "不可得": "✗"}.get(step["status"], "·")
        print(f"  {mark} {step['level']}：{step['detail']}")

    # 一致预期聚合过程
    if d.get("consensus_n_orgs"):
        print(f"[一致预期] {d['consensus_n_orgs']} 家机构，"
              f"预测{d.get('consensus_forward_year')}年净利 {d.get('consensus_forward_np')} 亿"
              f" vs 基准年 {d.get('consensus_base_np')} 亿")

    # TTM 窗口
    if d.get("ttm_note"):
        print(f"[TTM] {d['ttm_note']}")

    # ========== 第二部分：指标报表（精简、分组、去重） ==========
    print("\n=== 指标报表 ===")
    groups = [
        ("估值", ["pe_ttm", "pb", "ps_ttm", "dv_ttm", "total_mv_yi",
                  "pe_ttm_percentile_5y", "pb_percentile_5y"]),
        ("成长性", ["rev_yoy_avg3", "profit_yoy_avg3", "deducted_yoy_avg3",
                    "rev_positive_years", "profit_yoy_latest"]),
        ("PEG", ["peg"]),
        ("盈利质量", ["gross_margin", "net_margin", "roe_waa", "ocf_to_np", "debt_to_assets"]),
        ("流动性与波动", ["avg_daily_amount_yi", "volatility_annual"]),
        ("分红", ["div_years_cash", "div_latest_cash_div"]),
    ]
    for group, keys in groups:
        print(f"【{group}】")
        for k in keys:
            v = d.get(k)
            label = METRIC_LABELS.get(k, k)
            print(f"  {label}: {v if v is not None else '数据不可得'}")
        if group == "PEG" and d.get("peg") is not None:
            print(f"  → 增速分母：{d.get('growth_basis')}（{d.get('growth_period')}），"
                  f"增速 {d.get('growth_proxy')}%")
    print(f"\n输出目录: {os.path.abspath(args.outdir)}")

    # 自动打分（生成 score.json）
    if not args.no_score:
        print("\n--- 自动打分（score_stock.py）---")
        run_score(args.outdir)


if __name__ == "__main__":
    main()
