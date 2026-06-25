"""
市场数据获取模块 - 基于 AKShare（新浪 + 东方财富数据源）
"""
import akshare as ak
import pandas as pd
import time
import threading
from typing import Optional

# 简易内存缓存
_cache: dict = {}
_cache_lock = threading.Lock()
_fetch_events: dict = {}  # key -> threading.Event，用于等待拉取完成
_CACHE_TTL = 60  # 缓存有效期（秒）


def _cached(key: str, fetcher, ttl: int = _CACHE_TTL):
    """通用缓存装饰器（线程安全，避免重复拉取，等待进行中的拉取）"""
    now = time.time()

    # 检查缓存是否命中
    with _cache_lock:
        if key in _cache:
            data, ts = _cache[key]
            if now - ts < ttl:
                return data

    # 检查是否有正在进行的拉取，有则等待
    with _cache_lock:
        if key in _fetch_events:
            event = _fetch_events[key]
            is_my_event = False
        else:
            event = threading.Event()
            _fetch_events[key] = event
            is_my_event = True

    if not is_my_event:
        # 等待另一个线程完成拉取
        event.wait(timeout=30)
        with _cache_lock:
            if key in _cache:
                data, ts = _cache[key]
                return data
        # 等待超时或拉取失败，自己拉取
        return fetcher()
    else:
        # 由我来拉取
        try:
            data = fetcher()
            with _cache_lock:
                _cache[key] = (data, time.time())
            return data
        finally:
            event.set()


def _fetch_stock_spot():
    """拉取全量 A 股实时行情"""
    df = ak.stock_zh_a_spot()
    return df


def _fetch_etf_spot():
    """拉取全量 ETF 实时行情"""
    df = ak.fund_etf_spot_em()
    return df


def _fetch_index_spot():
    """拉取全量指数行情"""
    df = ak.stock_zh_index_spot_sina()
    return df


def search_stock(keyword: str) -> list[dict]:
    """搜索 A 股股票（新浪数据源，带缓存）"""
    try:
        df = _cached("stock_spot", _fetch_stock_spot)
        df = df[df["名称"].str.contains(keyword) | df["代码"].str.contains(keyword)]
        results = []
        for _, row in df.head(30).iterrows():
            results.append({
                "code": str(row["代码"]),
                "name": str(row["名称"]),
                "price": float(row["最新价"]),
                "change": float(row["涨跌额"]),
                "change_pct": float(row["涨跌幅"]),
                "type": "stock",
            })
        return results
    except Exception as e:
        print(f"搜索股票失败: {e}")
        return []


def get_stock_quote(code: str) -> Optional[dict]:
    """获取单只股票实时行情（新浪数据源，带缓存）"""
    try:
        df = _cached("stock_spot", _fetch_stock_spot)
        row = df[df["代码"] == code]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "code": str(r["代码"]),
            "name": str(r["名称"]),
            "price": float(r["最新价"]),
            "change": float(r["涨跌额"]),
            "change_pct": float(r["涨跌幅"]),
            "open": float(r["今开"]),
            "high": float(r["最高"]),
            "low": float(r["最低"]),
            "volume": float(r["成交量"]),
            "amount": float(r["成交额"]),
            "type": "stock",
        }
    except Exception as e:
        print(f"获取股票行情失败: {e}")
        return None


def _clean_code(code: str) -> str:
    """去掉 sh/sz 前缀，纯数字代码"""
    for prefix in ("sh", "sz", "bj"):
        if code.startswith(prefix):
            return code[len(prefix):]
    return code


def get_stock_history(code: str, period: str = "daily", days: int = 90) -> list[dict]:
    """获取股票历史 K 线数据"""
    code = _clean_code(code)
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period=period,
            start_date=(pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y%m%d"),
            end_date=pd.Timestamp.now().strftime("%Y%m%d"),
            adjust="qfq",
        )
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.iterrows():
            results.append({
                "date": str(row["日期"]),
                "open": float(row["开盘"]),
                "close": float(row["收盘"]),
                "high": float(row["最高"]),
                "low": float(row["最低"]),
                "volume": float(row["成交量"]),
                "amount": float(row.get("成交额", 0)),
            })
        return results
    except Exception as e:
        print(f"获取股票历史数据失败: {e}")
        return []


def search_fund(keyword: str) -> list[dict]:
    """搜索基金（ETF + 开放式基金）"""
    results = []
    # 搜索 ETF（东方财富数据源，带缓存）
    try:
        df = _cached("etf_spot", _fetch_etf_spot)
        df = df[df["名称"].str.contains(keyword) | df["代码"].str.contains(keyword)]
        for _, row in df.head(20).iterrows():
            results.append({
                "code": str(row["代码"]),
                "name": str(row["名称"]),
                "price": float(row["最新价"]),
                "change": float(row["涨跌额"]),
                "change_pct": float(row["涨跌幅"]),
                "type": "etf",
            })
    except Exception as e:
        print(f"搜索 ETF 失败: {e}")

    # 搜索开放式基金
    try:
        df_all = ak.fund_name_em()
        df_all = df_all[df_all["基金简称"].str.contains(keyword) | df_all["基金代码"].str.contains(keyword)]
        for _, row in df_all.head(20).iterrows():
            if not any(r["code"] == str(row["基金代码"]) for r in results):
                results.append({
                    "code": str(row["基金代码"]),
                    "name": str(row["基金简称"]),
                    "price": 0,
                    "change": 0,
                    "change_pct": 0,
                    "type": "fund",
                })
    except Exception as e:
        print(f"搜索开放式基金失败: {e}")

    return results


def get_fund_quote(code: str) -> Optional[dict]:
    """获取基金实时行情"""
    # 先尝试 ETF（东方财富数据源，带缓存）
    try:
        df = _cached("etf_spot", _fetch_etf_spot)
        row = df[df["代码"] == code]
        if not row.empty:
            r = row.iloc[0]
            return {
                "code": str(r["代码"]),
                "name": str(r["名称"]),
                "price": float(r["最新价"]),
                "change": float(r["涨跌额"]),
                "change_pct": float(r["涨跌幅"]),
                "open": float(r["今开"]),
                "high": float(r["最高"]),
                "low": float(r["最低"]),
                "volume": float(r["成交量"]),
                "amount": float(r["成交额"]),
                "type": "etf",
            }
    except Exception:
        pass

    # 尝试开放式基金净值
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            price = float(latest["单位净值"])
            prev_price = float(prev["单位净值"])
            return {
                "code": code,
                "name": code,
                "price": price,
                "change": round(price - prev_price, 4),
                "change_pct": round((price - prev_price) / prev_price * 100, 2) if prev_price else 0,
                "open": price,
                "high": price,
                "low": price,
                "volume": 0,
                "amount": 0,
                "type": "fund",
            }
    except Exception as e:
        print(f"获取基金净值失败: {e}")

    return None


def get_fund_history(code: str, days: int = 90) -> list[dict]:
    """获取基金历史净值走势"""
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.tail(days).iterrows():
            results.append({
                "date": str(row["净值日期"]),
                "open": float(row["单位净值"]),
                "close": float(row["单位净值"]),
                "high": float(row["单位净值"]),
                "low": float(row["单位净值"]),
                "volume": 0,
                "amount": 0,
            })
        return results
    except Exception as e:
        print(f"获取基金历史数据失败: {e}")
        return []


def get_market_index() -> dict:
    """获取主要市场指数（新浪数据源，带缓存）"""
    indices = {}
    try:
        df = _cached("index_spot", _fetch_index_spot)
        target_names = {"上证指数", "深证成指", "创业板指", "沪深300"}
        for _, row in df.iterrows():
            name = str(row["名称"])
            if name in target_names:
                indices[name] = {
                    "price": float(row["最新价"]),
                    "change_pct": float(row["涨跌幅"]),
                }
    except Exception as e:
        print(f"获取指数失败: {e}")
    return indices