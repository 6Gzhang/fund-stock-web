from fastapi import APIRouter, HTTPException, Query
from data.market import get_stock_quote, get_fund_quote, get_stock_history, get_fund_history, get_market_index, search_stock, search_fund, _cached, _fetch_stock_spot, _fetch_etf_spot
from data.ai import analyze_stock, is_ai_available, _advanced_technical_analysis, _compute_indicators
import threading

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_recommend_cache: dict = {"data": None, "ts": 0}
_recommend_lock = threading.Lock()
_RECOMMEND_TTL = 180  # 推荐缓存3分钟
_recommend_progress: dict = {"status": "idle", "total": 0, "done": 0, "message": ""}
_progress_lock = threading.Lock()


@router.get("/stock/{code}")
async def analyze(code: str, category: str = Query("stock")):
    """AI 智能分析单个标的"""
    if category in ("stock", "etf", "stock_hk"):
        quote = get_stock_quote(code)
        history = get_stock_history(code, days=90)
    else:
        quote = get_fund_quote(code)
        history = get_fund_history(code, days=90)

    if quote is None:
        raise HTTPException(status_code=404, detail="未找到该标的")

    market_indices = get_market_index()

    result = analyze_stock(
        code=code,
        name=quote["name"],
        price=quote["price"],
        change_pct=quote["change_pct"],
        history=history,
        market_indices=market_indices,
    )

    return {
        "code": code,
        "name": quote["name"],
        "price": quote["price"],
        "change_pct": quote["change_pct"],
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],
        "reasoning": result["reasoning"],
        "suggested_ratio": result["suggested_ratio"],
        "buy_reasons": result.get("buy_reasons", []),
        "sell_reasons": result.get("sell_reasons", []),
        "risk_level": result.get("risk_level", "medium"),
        "target_price": result.get("target_price"),
        "indicators": result.get("indicators", {}),
        "score_detail": result.get("score_detail", {}),
        "ai_available": result.get("ai_available", is_ai_available()),
    }


@router.get("/status")
async def status():
    """检查 AI 服务状态"""
    return {"ai_available": is_ai_available()}


@router.get("/recommendations/progress")
async def recommendations_progress():
    """获取推荐计算进度"""
    with _progress_lock:
        return dict(_recommend_progress)


@router.get("/recommendations")
async def get_recommendations(category: str = Query("all")):
    """智能推荐：筛选技术面评分最高的股票/基金"""
    import time
    now = time.time()

    with _recommend_lock:
        if _recommend_cache["data"] and now - _recommend_cache["ts"] < _RECOMMEND_TTL:
            data = _recommend_cache["data"]
            if category == "stock":
                return {"stocks": data.get("stocks", []), "funds": [], "updated_at": data.get("updated_at")}
            elif category == "fund":
                return {"stocks": [], "funds": data.get("funds", []), "updated_at": data.get("updated_at")}
            return data

    # 后台计算推荐
    def _compute():
        try:
            with _progress_lock:
                _recommend_progress["status"] = "loading"
                _recommend_progress["total"] = 100
                _recommend_progress["done"] = 0
                _recommend_progress["message"] = "正在获取市场数据..."

            market_indices = get_market_index()

            with _progress_lock:
                _recommend_progress["done"] = 10
                _recommend_progress["message"] = "正在分析股票..."

            stock_recs = _compute_stock_recommendations(market_indices)

            with _progress_lock:
                _recommend_progress["done"] = 70
                _recommend_progress["message"] = "正在分析基金..."

            fund_recs = _compute_fund_recommendations(market_indices)

            result = {
                "stocks": stock_recs,
                "funds": fund_recs,
                "updated_at": int(time.time()),
            }
            with _recommend_lock:
                _recommend_cache["data"] = result
                _recommend_cache["ts"] = time.time()

            with _progress_lock:
                _recommend_progress["status"] = "done"
                _recommend_progress["done"] = 100
                _recommend_progress["message"] = "推荐计算完成"
        except Exception as e:
            print(f"计算推荐失败: {e}")
            with _progress_lock:
                _recommend_progress["status"] = "error"
                _recommend_progress["message"] = str(e)

    threading.Thread(target=_compute, daemon=True).start()

    # 先返回缓存或空结果
    with _recommend_lock:
        data = _recommend_cache["data"]
        if data:
            if category == "stock":
                return {"stocks": data.get("stocks", []), "funds": [], "updated_at": data.get("updated_at")}
            elif category == "fund":
                return {"stocks": [], "funds": data.get("funds", []), "updated_at": data.get("updated_at")}
            return data

    return {"stocks": [], "funds": [], "updated_at": 0, "loading": True}


@router.post("/recommendations/refresh")
async def refresh_recommendations():
    """手动刷新推荐（清除缓存，立即重新计算）"""
    with _recommend_lock:
        _recommend_cache["data"] = None
        _recommend_cache["ts"] = 0

    import time
    def _compute():
        try:
            market_indices = get_market_index()
            stock_recs = _compute_stock_recommendations(market_indices)
            fund_recs = _compute_fund_recommendations(market_indices)
            result = {
                "stocks": stock_recs,
                "funds": fund_recs,
                "updated_at": int(time.time()),
            }
            with _recommend_lock:
                _recommend_cache["data"] = result
                _recommend_cache["ts"] = time.time()
        except Exception as e:
            print(f"计算推荐失败: {e}")

    threading.Thread(target=_compute, daemon=True).start()
    return {"status": "ok", "message": "正在重新计算推荐"}


def _compute_stock_recommendations(market_indices: dict) -> list:
    """计算 A 股推荐列表 - 多维度智能筛选（并发优化）"""
    import pandas as pd
    import concurrent.futures

    df = _cached("stock_spot", _fetch_stock_spot)
    if df is None or df.empty:
        return []

    filtered = df[
        (df["最新价"] > 2) &
        (df["最新价"] < 200) &
        (df["涨跌幅"] > -3) &
        (df["涨跌幅"] < 7) &
        (df["成交额"] > 50000000)
    ]

    if filtered.empty:
        return []

    def _compute_composite_score(row):
        """综合评分：涨幅(30%) + 量比(25%) + 振幅(15%) + 成交额排名(30%)"""
        try:
            change = float(row["涨跌幅"])
            amount = float(row["成交额"])
            high = float(row["最高"])
            low = float(row["最低"])
            pre_close = float(row["最新价"]) - float(row["涨跌额"])

            amp = ((high - low) / pre_close * 100) if pre_close > 0 else 0

            change_score = max(0, min(100, (change + 3) / 10 * 100))
            amount_rank = filtered["成交额"].rank(pct=True).loc[row.name] * 100
            amp_score = min(100, amp * 10)

            volume_ratio = 1.0
            if "量比" in row:
                try:
                    vr = float(row["量比"])
                    volume_ratio = min(3.0, max(0.5, vr))
                except Exception:
                    pass
            volume_score = min(100, volume_ratio * 50)

            composite = (
                change_score * 0.30 +
                volume_score * 0.25 +
                amp_score * 0.15 +
                amount_rank * 0.30
            )
            return composite
        except Exception:
            return 50.0

    filtered = filtered.copy()
    filtered["composite_score"] = filtered.apply(_compute_composite_score, axis=1)
    top_candidates = filtered.nlargest(30, "composite_score")  # 减少到30只，提高速度

    total_candidates = len(top_candidates)
    done_count = [0]

    def _analyze_one(row):
        """分析单只股票（用于并发）"""
        try:
            from data.market import get_stock_history
            code = str(row["代码"])
            name = str(row["名称"])
            price = float(row["最新价"])
            change_pct = float(row["涨跌幅"])

            history = get_stock_history(code, days=60)
            if not history or len(history) < 20:
                return None

            result = _advanced_technical_analysis(
                code, name, price, change_pct, history, market_indices
            )
            score_detail = result.get("score_detail", {})
            net_score = score_detail.get("net_score", 0)
            buy_score = score_detail.get("buy_score", 0)
            sell_score = score_detail.get("sell_score", 0)

            done_count[0] += 1
            with _progress_lock:
                _recommend_progress["done"] = 10 + int(60 * done_count[0] / total_candidates)

            if net_score >= 2 and result.get("recommendation") in ("buy", "hold"):
                indicators = result.get("indicators", {})
                target = result.get("target_price")
                upside_pct = ((target - price) / price * 100) if target and price > 0 else 0

                if net_score >= 4:
                    strength = "强势推荐"
                elif net_score >= 3:
                    strength = "推荐"
                else:
                    strength = "关注"

                return {
                    "code": code,
                    "name": name,
                    "price": price,
                    "change_pct": change_pct,
                    "score": net_score,
                    "buy_score": buy_score,
                    "sell_score": sell_score,
                    "confidence": result.get("confidence", 0),
                    "risk_level": result.get("risk_level", "medium"),
                    "target_price": target,
                    "upside_pct": round(upside_pct, 2),
                    "strength": strength,
                    "top_reason": result.get("buy_reasons", [""])[0] if result.get("buy_reasons") else "",
                    "buy_reasons": result.get("buy_reasons", [])[:4],
                    "sell_reasons": result.get("sell_reasons", [])[:2],
                    "indicators": indicators,
                    "type": "stock",
                    "recommendation": result.get("recommendation", "hold"),
                }
            return None
        except Exception:
            done_count[0] += 1
            return None

    # 并发分析（8线程）
    scored = []
    rows = [row for _, row in top_candidates.iterrows()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_analyze_one, row) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    scored.append(result)
            except Exception:
                continue

    scored.sort(key=lambda x: (x["score"], x["upside_pct"]), reverse=True)
    return scored[:10]


def _compute_fund_recommendations(market_indices: dict) -> list:
    """计算 ETF/基金推荐列表 - 多维度智能筛选（并发优化）"""
    import pandas as pd
    import concurrent.futures

    try:
        df = _cached("etf_spot", _fetch_etf_spot)
    except Exception:
        return []

    if df is None or df.empty:
        return []

    try:
        filtered = df[
            (df["最新价"] > 0.8) &
            (df["涨跌幅"] > -4) &
            (df["涨跌幅"] < 6) &
            (df["成交额"] > 10000000)
        ]
    except Exception:
        return []

    if filtered.empty:
        return []

    def _compute_etf_score(row):
        """ETF 综合评分"""
        try:
            change = float(row["涨跌幅"])
            amount = float(row["成交额"])
            change_score = max(0, min(100, (change + 4) / 10 * 100))
            amount_rank = filtered["成交额"].rank(pct=True).loc[row.name] * 100
            return change_score * 0.4 + amount_rank * 0.6
        except Exception:
            return 50.0

    filtered = filtered.copy()
    filtered["etf_score"] = filtered.apply(_compute_etf_score, axis=1)
    top_candidates = filtered.nlargest(20, "etf_score")  # 减少到20只

    total_candidates = len(top_candidates)
    done_count = [0]

    def _analyze_one(row):
        """分析单只ETF（用于并发）"""
        try:
            from data.market import get_stock_history
            code = str(row["代码"])
            name = str(row["名称"])
            price = float(row["最新价"])
            change_pct = float(row["涨跌幅"])

            history = get_stock_history(code, days=60)
            if not history or len(history) < 15:
                return None

            result = _advanced_technical_analysis(
                code, name, price, change_pct, history, market_indices
            )
            score_detail = result.get("score_detail", {})
            net_score = score_detail.get("net_score", 0)

            done_count[0] += 1
            with _progress_lock:
                _recommend_progress["done"] = 70 + int(30 * done_count[0] / total_candidates)

            if net_score >= 1:
                indicators = result.get("indicators", {})
                target = result.get("target_price")
                upside_pct = ((target - price) / price * 100) if target and price > 0 else 0

                if net_score >= 3:
                    strength = "强势推荐"
                elif net_score >= 2:
                    strength = "推荐"
                else:
                    strength = "关注"

                return {
                    "code": code,
                    "name": name,
                    "price": price,
                    "change_pct": change_pct,
                    "score": net_score,
                    "buy_score": score_detail.get("buy_score", 0),
                    "sell_score": score_detail.get("sell_score", 0),
                    "confidence": result.get("confidence", 0),
                    "risk_level": result.get("risk_level", "medium"),
                    "target_price": target,
                    "upside_pct": round(upside_pct, 2),
                    "strength": strength,
                    "top_reason": result.get("buy_reasons", [""])[0] if result.get("buy_reasons") else "",
                    "buy_reasons": result.get("buy_reasons", [])[:4],
                    "sell_reasons": result.get("sell_reasons", [])[:2],
                    "indicators": indicators,
                    "type": "etf",
                    "recommendation": result.get("recommendation", "hold"),
                }
            return None
        except Exception:
            done_count[0] += 1
            return None

    # 并发分析（8线程）
    scored = []
    rows = [row for _, row in top_candidates.iterrows()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_analyze_one, row) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    scored.append(result)
            except Exception:
                continue

    scored.sort(key=lambda x: (x["score"], x["upside_pct"]), reverse=True)
    return scored[:10]