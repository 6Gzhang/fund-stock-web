"""
基金股票分析软件 - 主入口
"""
import os
import threading
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from models.database import init_db
from routes.market import router as market_router
from routes.trade import router as trade_router
from routes.analysis import router as analysis_router

VERSION = "1.0.0"
VERSION_URL = "https://api.github.com/repos/6Gzhang/fund-stock-web/releases/latest"

app = FastAPI(title="基金股票分析软件", version=VERSION)

# 初始化数据库
init_db()

# 注册路由
app.include_router(market_router)
app.include_router(trade_router)
app.include_router(analysis_router)

# 静态文件
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")


@app.on_event("startup")
async def startup_prefetch():
    """启动时后台预加载数据到缓存"""
    def _prefetch():
        try:
            from data.market import _cached, _fetch_stock_spot, _fetch_etf_spot, _fetch_index_spot
            _cached("stock_spot", _fetch_stock_spot)
            _cached("etf_spot", _fetch_etf_spot)
            _cached("index_spot", _fetch_index_spot)
            print("数据预加载完成")
        except Exception as e:
            print(f"预加载失败: {e}")
    threading.Thread(target=_prefetch, daemon=True).start()


@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/api/version")
async def get_version():
    """获取当前版本信息"""
    return {"version": VERSION, "name": "fund-stock-web"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)