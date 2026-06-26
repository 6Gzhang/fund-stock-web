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
    """获取持仓列表（含实时市值）"""
    positions = get_positions()
    result = []
    for p in positions:
        # 获取实时价格
        if p["type"] in ("stock", "etf", "stock_hk"):
            quote = get_stock_quote(p["code"])
        else:
            quote = get_fund_quote(p["code"])

        current_price = quote["price"] if quote else 0
        market_value = current_price * p["shares"]
        profit = market_value - p["avg_cost"] * p["shares"]
        profit_pct = (profit / (p["avg_cost"] * p["shares"]) * 100) if p["avg_cost"] > 0 else 0

        result.append({
            **p,
            "current_price": round(current_price, 4),
            "market_value": round(market_value, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 2),
        })
    return {"positions": result}


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