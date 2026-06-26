from fastapi import APIRouter, HTTPException
from models.database import (
    get_positions, get_position, update_position, delete_position,
    add_trade, get_trades, get_watchlist, add_to_watchlist, remove_from_watchlist,
)
from models.schemas import TradeRequest
from data.market import get_stock_quote, get_fund_quote

router = APIRouter(prefix="/api/trade", tags=["trade"])


@router.post("/execute")
async def execute_trade(req: TradeRequest):
    """执行模拟交易（买入/卖出）"""
    current = get_position(req.code)

    if req.action == "buy":
        # 买入：增加持仓
        new_shares = (current["shares"] + req.shares) if current else req.shares
        if current:
            total_cost = current["avg_cost"] * current["shares"] + req.price * req.shares
            new_avg_cost = total_cost / new_shares
        else:
            new_avg_cost = req.price
        update_position(req.code, req.name, req.type, new_shares, round(new_avg_cost, 4))

    elif req.action == "sell":
        if not current or current["shares"] < req.shares:
            raise HTTPException(status_code=400, detail="持仓不足，无法卖出")
        new_shares = current["shares"] - req.shares
        if new_shares <= 0.001:
            delete_position(req.code)
        else:
            update_position(req.code, req.name, req.type, new_shares, current["avg_cost"])

    else:
        raise HTTPException(status_code=400, detail="无效的交易动作")

    # 记录交易
    add_trade(req.code, req.name, req.type, req.action, req.shares, req.price, req.shares * req.price)

    return {"success": True, "message": f"{'买入' if req.action == 'buy' else '卖出'}成功"}


@router.get("/positions")
async def positions():
    """获取持仓列表（含实时市值和持仓监控数据）"""
    positions = get_positions()
    result = []
    for p in positions:
        code = p["code"]
        ptype = p["type"]

        # 自动识别ETF代码（51/15/16/13开头）
        is_etf = code.startswith(("51", "15", "16", "13")) or ptype == "etf"

        # 获取实时价格
        if is_etf:
            quote = get_fund_quote(code)
        elif ptype == "stock_hk":
            quote = get_stock_quote(code, category="stock_hk")
        else:
            quote = get_stock_quote(code)

        current_price = quote["price"] if quote else 0
        market_value = current_price * p["shares"]
        profit = market_value - p["avg_cost"] * p["shares"]
        profit_pct = (profit / (p["avg_cost"] * p["shares"]) * 100) if p["avg_cost"] > 0 else 0

        # 持仓监控：计算上涨空间和卖出信号
        monitor = _compute_position_monitor(code, p["name"], current_price, p["avg_cost"], is_etf)

        result.append({
            **p,
            "current_price": round(current_price, 4),
            "market_value": round(market_value, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 2),
            "monitor": monitor,
        })
    return {"positions": result}


def _compute_position_monitor(code: str, name: str, current_price: float, avg_cost: float, is_etf: bool) -> dict:
    """计算持仓监控数据：上涨空间、卖出信号、关键指标"""
    try:
        from data.market import get_stock_history
        from data.ai import _compute_indicators

        history = get_stock_history(code, days=60) if not is_etf else get_stock_history(code, days=30)
        if not history or len(history) < 10:
            return _default_monitor(current_price, avg_cost)

        closes = [d["close"] for d in history]
        indicators = _compute_indicators(history, current_price)

        # 计算上涨空间
        recent_high = max(d["high"] for d in history[-20:])
        boll_upper = indicators.get("boll_upper", 0)
        target_price = max(recent_high * 1.03, boll_upper * 1.01, avg_cost * 1.08) if boll_upper > 0 else recent_high * 1.03

        # 上涨空间百分比
        upside_pct = ((target_price - current_price) / current_price * 100) if current_price > 0 else 0

        # 卖出信号判断
        sell_signal = ""
        sell_reasons = []
        action = "持有"  # 持有/减仓/清仓

        # 止盈条件：当前价 >= 目标价 * 0.97
        if current_price >= target_price * 0.97:
            action = "止盈"
            sell_signal = "已达目标价，建议分批止盈"
            sell_reasons.append(f"当前价{current_price:.2f}接近目标价{target_price:.2f}")
        # 止损条件：当前价 <= 成本价 * 0.95
        elif current_price <= avg_cost * 0.95:
            action = "止损"
            sell_signal = "跌破成本线，建议谨慎"
            sell_reasons.append(f"当前价{current_price:.2f}低于成本{avg_cost:.2f}，亏损{((current_price-avg_cost)/avg_cost*100):.1f}%")
        # 回调预警：RSI > 75
        elif indicators.get("rsi", 0) > 75:
            action = "减仓"
            sell_signal = "RSI超买，建议分批减仓"
            sell_reasons.append(f"RSI指标{indicators['rsi']:.1f}超过75，处于超买区间")
        # 趋势转弱：MACD死叉
        elif indicators.get("macd", 0) < indicators.get("dea", 0) and indicators.get("dif", 0) < 0:
            action = "减仓"
            sell_signal = "MACD趋势转弱，建议减仓"
            sell_reasons.append("MACD指标显示短期趋势向下")
        # KDJ高位死叉
        elif indicators.get("k", 0) > 80 and indicators.get("d", 0) > 80 and indicators.get("j", 0) < indicators.get("k", 0):
            action = "减仓"
            sell_signal = "KDJ高位死叉，注意回调风险"
            sell_reasons.append(f"KDJ指标在高位，K={indicators['k']:.1f} D={indicators['d']:.1f}")

        # 持有多头理由
        hold_reasons = []
        if indicators.get("rsi", 0) < 40:
            hold_reasons.append(f"RSI={indicators['rsi']:.1f}偏低，存在反弹机会")
        if indicators.get("macd", 0) > indicators.get("dea", 0):
            hold_reasons.append("MACD金叉，趋势向上")
        if current_price < avg_cost:
            hold_reasons.append(f"仍低于成本价，安全边际较高")

        return {
            "target_price": round(target_price, 2),
            "upside_pct": round(upside_pct, 2),
            "current_price": round(current_price, 2),
            "avg_cost": round(avg_cost, 2),
            "action": action,
            "sell_signal": sell_signal,
            "sell_reasons": sell_reasons[:3],
            "hold_reasons": hold_reasons[:3],
            "indicators": {
                "rsi": round(indicators.get("rsi", 0), 1),
                "macd": round(indicators.get("macd", 0), 4),
                "kdj_k": round(indicators.get("k", 0), 1),
                "kdj_d": round(indicators.get("d", 0), 1),
            }
        }
    except Exception as e:
        print(f"持仓监控计算失败 {code}: {e}")
        return _default_monitor(current_price, avg_cost)


def _default_monitor(current_price: float, avg_cost: float) -> dict:
    """默认监控数据"""
    upside_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 and current_price > 0 else 0
    return {
        "target_price": None,
        "upside_pct": round(upside_pct, 2),
        "current_price": round(current_price, 2),
        "avg_cost": round(avg_cost, 2),
        "action": "持有",
        "sell_signal": "",
        "sell_reasons": [],
        "hold_reasons": [],
        "indicators": {}
    }


@router.get("/trades")
async def trades(limit: int = 50):
    return {"trades": get_trades(limit)}


@router.get("/watchlist")
async def watchlist():
    return {"watchlist": get_watchlist()}


@router.post("/watchlist/add")
async def watchlist_add(code: str, name: str, type: str = "stock"):
    add_to_watchlist(code, name, type)
    return {"success": True}


@router.post("/watchlist/remove")
async def watchlist_remove(code: str):
    remove_from_watchlist(code)
    return {"success": True}