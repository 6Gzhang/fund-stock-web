from fastapi import APIRouter, HTTPException, Query
from data.market import get_stock_quote, get_fund_quote, get_stock_history, get_fund_history, get_market_index
from data.ai import analyze_stock, is_ai_available

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/stock/{code}")
async def analyze(code: str, category: str = Query("stock")):
    """AI 智能分析单个标的"""
    # 获取行情
    if category in ("stock", "etf"):
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
        "ai_available": is_ai_available(),
    }


@router.get("/status")
async def status():
    """检查 AI 服务状态"""
    return {"ai_available": is_ai_available()}