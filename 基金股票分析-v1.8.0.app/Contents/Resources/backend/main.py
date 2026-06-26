"""
基金股票分析软件 - 主入口
"""
import os
import time
import threading
import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from models.database import init_db
from routes.market import router as market_router
from routes.trade import router as trade_router
from routes.analysis import router as analysis_router
from modules.routes import router as modules_router
from modules.startup_checker import run_startup_check, ensure_ai_fallback, init_module as init_startup
from modules.db_manager import init_module_db
from modules.sim_executor import init_module as init_sim

VERSION = "1.8.0"
VERSION_URL = "https://api.github.com/repos/6Gzhang/fund-stock-web/releases/latest"
RELEASE_URL = "https://github.com/6Gzhang/fund-stock-web/releases/latest"

# 版本检查缓存
_latest_version_cache: dict = {"data": None, "ts": 0}
_VERSION_CHECK_TTL = 300  # 5分钟缓存

# 数据加载状态
_data_loading_status: dict = {
    "stock_spot": "pending",  # pending / loading / done / error
    "etf_spot": "pending",
    "hk_spot": "pending",
    "index_spot": "pending",
    "fund_name": "pending",
}
_data_status_lock = threading.Lock()

app = FastAPI(title="基金股票分析软件", version=VERSION)

# 初始化数据库
init_db()

# 注册路由
app.include_router(market_router)
app.include_router(trade_router)
app.include_router(analysis_router)
app.include_router(modules_router)

try:
    from routes.chat import router as chat_router
    app.include_router(chat_router)
except Exception as e:
    print(f"加载chat路由失败: {e}")

# 静态文件
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")


@app.on_event("startup")
async def startup_prefetch():
    """启动时后台预加载数据到缓存"""
    def _prefetch_item(key, fetcher):
        with _data_status_lock:
            _data_loading_status[key] = "loading"
        try:
            from data.market import _cached
            _cached(key, fetcher)
            with _data_status_lock:
                _data_loading_status[key] = "done"
            print(f"数据预加载完成: {key}")
        except Exception as e:
            with _data_status_lock:
                _data_loading_status[key] = "error"
            print(f"预加载失败 {key}: {e}")

    def _prefetch():
        from data.market import _fetch_stock_spot, _fetch_etf_spot, _fetch_index_spot, _fetch_hk_spot
        import akshare as ak
        threads = [
            threading.Thread(target=_prefetch_item, args=("stock_spot", _fetch_stock_spot)),
            threading.Thread(target=_prefetch_item, args=("etf_spot", _fetch_etf_spot)),
            threading.Thread(target=_prefetch_item, args=("index_spot", _fetch_index_spot)),
            threading.Thread(target=_prefetch_item, args=("hk_spot", _fetch_hk_spot)),
            threading.Thread(target=_prefetch_item, args=("fund_name", lambda: ak.fund_name_em())),
        ]
        for t in threads:
            t.daemon = True
            t.start()
        for t in threads:
            t.join()
        print("所有数据预加载完成")

    threading.Thread(target=_prefetch, daemon=True).start()

    # 初始化新模块
    try:
        init_module_db()
        init_sim()
        init_startup()
        print("[主程序] 新模块初始化完成")
    except Exception as e:
        print(f"[主程序] 新模块初始化失败: {e}")

    # 后台运行开机自检
    def _delayed_startup_check():
        time.sleep(3)
        try:
            run_startup_check()
            ensure_ai_fallback()
        except Exception as e:
            print(f"[主程序] 开机自检失败: {e}")
    
    threading.Thread(target=_delayed_startup_check, daemon=True).start()


@app.get("/api/data-status")
async def get_data_status():
    """获取数据加载状态"""
    with _data_status_lock:
        return dict(_data_loading_status)


@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/api/version")
async def get_version():
    """获取版本信息（含更新检查）"""
    result = {
        "version": VERSION,
        "name": "fund-stock-web",
        "hasUpdate": False,
        "latestVersion": VERSION,
        "downloadUrl": RELEASE_URL,
        "releaseNotes": None,
    }

    # 检查缓存
    now = time.time()
    if _latest_version_cache["data"] and (now - _latest_version_cache["ts"]) < _VERSION_CHECK_TTL:
        cached = _latest_version_cache["data"]
        return {**result, **cached}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(VERSION_URL, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                latest = data.get("tag_name", "v1.0.0").lstrip("v")
                result["latestVersion"] = latest
                result["releaseNotes"] = data.get("body", "")
                result["downloadUrl"] = data.get("html_url", RELEASE_URL)

                # 比较版本号
                if _compare_versions(latest, VERSION) > 0:
                    result["hasUpdate"] = True

                _latest_version_cache["data"] = {
                    "hasUpdate": result["hasUpdate"],
                    "latestVersion": latest,
                    "downloadUrl": result["downloadUrl"],
                    "releaseNotes": result["releaseNotes"],
                }
                _latest_version_cache["ts"] = now
    except Exception as e:
        print(f"版本检查失败: {e}")

    return result


def _compare_versions(v1: str, v2: str) -> int:
    """比较版本号，返回 1 (v1>v2), -1 (v1<v2), 0 (相等)"""
    try:
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
        for a, b in zip(parts1, parts2):
            if a > b:
                return 1
            if a < b:
                return -1
        return len(parts1) - len(parts2)
    except Exception:
        return 0


if __name__ == "__main__":
    import uvicorn
    import os
    reload = os.environ.get("RELOAD", "0") == "1"
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=reload)