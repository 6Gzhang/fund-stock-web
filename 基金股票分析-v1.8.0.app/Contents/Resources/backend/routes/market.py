from fastapi import APIRouter, HTTPException, Query
import pandas as pd
from data.market import search_stock, search_fund, get_stock_quote, get_fund_quote, get_stock_history, get_fund_history, get_market_index, _cached, _fetch_stock_spot, _fetch_etf_spot, _fetch_hk_spot

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/list/stocks")
async def list_stocks(
    category: str = Query("all"),  # all/stock/etf/hk
    page: int = Query(1),
    page_size: int = Query(50),  # 每页数量
    sort_by: str = Query("change_pct"),  # change_pct/price/volume
    order: str = Query("desc"),  # desc/asc
):
    """获取股票列表（分页，支持A股/ETF/港股）"""
    results = []
    
    # 获取数据（使用阻塞模式确保数据加载完成）
    if category in ("all", "stock"):
        df = _cached("stock_spot", _fetch_stock_spot, wait=True)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                results.append({
                    "code": str(row["代码"]),
                    "name": str(row["名称"]),
                    "price": float(row["最新价"]) if pd.notna(row["最新价"]) else 0,
                    "change": float(row["涨跌额"]) if pd.notna(row["涨跌额"]) else 0,
                    "change_pct": float(row["涨跌幅"]) if pd.notna(row["涨跌幅"]) else 0,
                    "volume": float(row["成交量"]) if pd.notna(row["成交量"]) else 0,
                    "amount": float(row["成交额"]) if pd.notna(row["成交额"]) else 0,
                    "type": "stock",
                })
    
    if category in ("all", "etf"):
        df = _cached("etf_spot", _fetch_etf_spot, wait=True)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                results.append({
                    "code": str(row["代码"]),
                    "name": str(row["名称"]),
                    "price": float(row["最新价"]) if pd.notna(row["最新价"]) else 0,
                    "change": float(row["涨跌额"]) if pd.notna(row["涨跌额"]) else 0,
                    "change_pct": float(row["涨跌幅"]) if pd.notna(row["涨跌幅"]) else 0,
                    "volume": float(row["成交量"]) if pd.notna(row["成交量"]) else 0,
                    "amount": float(row["成交额"]) if pd.notna(row["成交额"]) else 0,
                    "type": "etf",
                })
    
    if category in ("all", "hk"):
        hk_list = _cached("hk_spot", _fetch_hk_spot, ttl=180, wait=True)
        if hk_list:
            for item in hk_list:
                results.append({
                    "code": "hk" + str(item.get("code", "")),
                    "name": str(item.get("name", "")),
                    "price": float(item.get("price", 0) or 0),
                    "change": float(item.get("change", 0) or 0),
                    "change_pct": float(item.get("change_pct", 0) or 0),
                    "volume": float(item.get("volume", 0) or 0),
                    "amount": float(item.get("amount", 0) or 0),
                    "type": "stock_hk",
                })
    
    # 排序
    reverse = (order == "desc")
    if sort_by == "change_pct":
        results.sort(key=lambda x: x["change_pct"], reverse=reverse)
    elif sort_by == "price":
        results.sort(key=lambda x: x["price"], reverse=reverse)
    elif sort_by == "volume" or sort_by == "amount":
        results.sort(key=lambda x: x["amount"], reverse=reverse)
    
    # 分页
    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = results[start:end]
    
    return {
        "items": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


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