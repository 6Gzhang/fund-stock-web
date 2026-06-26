from fastapi import APIRouter, HTTPException, Query
from data.market import search_stock, search_fund, get_stock_quote, get_fund_quote, get_stock_history, get_fund_history, get_market_index

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/search")
async def search(keyword: str = Query(...), category: str = Query("all")):
    results = []
    if category in ("all", "stock"):
        results.extend(search_stock(keyword))
    if category in ("all", "fund", "etf"):
        results.extend(search_fund(keyword))
    return {"results": results}


@router.get("/quote/{code}")
async def quote(code: str, category: str = Query("stock")):
    if category in ("stock", "stock_hk"):
        data = get_stock_quote(code)
    elif category in ("fund", "etf"):
        data = get_fund_quote(code)
    else:
        raise HTTPException(status_code=400, detail="无效的类别")

    if data is None:
        raise HTTPException(status_code=404, detail="未找到该标的")

    return data


@router.get("/history/{code}")
async def history(code: str, category: str = Query("stock"), days: int = Query(90)):
    if category in ("stock", "etf", "stock_hk"):
        data = get_stock_history(code, days=days)
    elif category == "fund":
        data = get_fund_history(code, days=days)
    else:
        data = get_stock_history(code, days=days)

    return {"history": data}


@router.get("/market-index")
async def market_index():
    return get_market_index()