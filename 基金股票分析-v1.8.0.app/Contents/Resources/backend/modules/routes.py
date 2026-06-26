"""
新模块API路由 - 独立于原有路由，不修改原代码
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional

router = APIRouter(prefix="/api/modules", tags=["new_modules"])

# ========== 模块1: 数据库管理 ==========

@router.get("/db/health")
async def db_health():
    """数据库健康检查"""
    from modules.db_manager import check_db_health
    return check_db_health()


@router.post("/db/backup")
async def db_backup():
    """一键备份数据库"""
    from modules.db_manager import backup_database
    return backup_database()


@router.get("/db/backups")
async def db_backups():
    """备份列表"""
    from modules.db_manager import list_backups
    return {"backups": list_backups()}


@router.post("/db/restore")
async def db_restore(backup_name: str = Body(..., embed=True)):
    """还原数据库"""
    from modules.db_manager import restore_database
    return restore_database(backup_name)


@router.post("/db/clean")
async def db_clean(days: int = Body(30, embed=True)):
    """清理旧数据"""
    from modules.db_manager import clean_old_data
    return clean_old_data(days)


@router.get("/stock/{code}/notes")
async def stock_notes(code: str):
    """获取个股备注"""
    from modules.db_manager import get_stock_notes
    return {"notes": get_stock_notes(code)}


@router.post("/stock/{code}/notes")
async def add_stock_note(code: str, note: str = Body(...), category: str = Body("general")):
    """添加个股备注"""
    from modules.db_manager import add_stock_note
    return {"success": add_stock_note(code, note, category)}


@router.delete("/stock/notes/{note_id}")
async def delete_stock_note(note_id: int):
    """删除个股备注"""
    from modules.db_manager import delete_stock_note
    return {"success": delete_stock_note(note_id)}


# ========== 模块2: 自动抓取 ==========

@router.get("/fetch/status")
async def fetch_status():
    """抓取状态"""
    from modules.auto_fetcher import get_fetch_status, get_today_stats
    return {"status": get_fetch_status(), "today": get_today_stats()}


@router.post("/fetch/history")
async def fetch_history(codes: list = Body(...), days: int = Body(730)):
    """批量补全历史数据"""
    from modules.auto_fetcher import fetch_batch_history
    return {"results": fetch_batch_history(codes, days)}


# ========== 模块3: 指标引擎 ==========

@router.post("/indicators/compute")
async def compute_indicators(history: list = Body(...)):
    """计算全部指标"""
    from modules.indicator_engine import compute_all_indicators
    return compute_all_indicators(history)


@router.post("/indicators/signals")
async def compute_signals(indicators: dict = Body(...), market: str = Body("A")):
    """生成买卖信号"""
    from modules.indicator_engine import generate_signals
    return generate_signals(indicators, market)


@router.post("/indicators/backtest")
async def run_backtest(history: list = Body(...), strategy: dict = Body(None), market: str = Body("A")):
    """回测"""
    from modules.indicator_engine import backtest
    return backtest(history, strategy or {}, market)


# ========== 模块4: 交易决策 ==========

@router.post("/decision/position")
async def calc_position(
    method: str = Body("fixed"),
    available_cash: float = Body(...),
    price: float = Body(...),
    market: str = Body("A"),
    ratio: float = Body(0.2),
    position_count: int = Body(5),
    win_prob: float = Body(0.5),
    avg_win: float = Body(0.1),
    avg_loss: float = Body(0.05),
):
    """仓位计算"""
    from modules.decision_engine import fixed_ratio, kelly_criterion, equal_weight
    
    if method == "fixed":
        return fixed_ratio(available_cash, price, ratio, market)
    elif method == "kelly":
        return kelly_criterion(win_prob, avg_win, avg_loss, available_cash, price, market)
    elif method == "equal":
        return equal_weight(available_cash, price, position_count, market)
    return {"error": "未知方法"}


@router.post("/decision/commission")
async def calc_commission(amount: float = Body(...), market: str = Body("A"), is_buy: bool = Body(True)):
    """手续费计算"""
    from modules.decision_engine import calc_commission
    return calc_commission(market, amount, 0, is_buy)


@router.post("/decision/card")
async def generate_card(
    code: str = Body(...), name: str = Body(...),
    current_price: float = Body(...), target_price: float = Body(None),
    buy_reasons: list = Body([]), sell_reasons: list = Body([]),
    risk_analysis: dict = Body({}), market: str = Body("A"),
    sector: str = Body("未知行业"),
):
    """生成决策卡片"""
    from modules.decision_engine import generate_decision_card
    return generate_decision_card(
        code, name, current_price, target_price,
        buy_reasons, sell_reasons, risk_analysis, market, sector
    )


# ========== 模块5: AI分析 ==========

@router.post("/ai/analyze")
async def ai_analyze(
    code: str = Body(...), name: str = Body(...),
    price: float = Body(...), change_pct: float = Body(0),
    history: list = Body([]), mode: str = Body("auto"),
):
    """AI单股分析"""
    from modules.ai_analyzer import analyze_stock_full
    return analyze_stock_full(code, name, price, change_pct, history, mode)


@router.post("/ai/batch")
async def ai_batch_analyze(stocks: list = Body(...), mode: str = Body("auto")):
    """AI批量分析"""
    from modules.ai_analyzer import batch_analyze, compare_scores
    results = batch_analyze(stocks, mode)
    comparison = compare_scores(results)
    return {"results": results, "comparison": comparison}


@router.post("/ai/portfolio-health")
async def ai_portfolio_health(positions: list = Body(...)):
    """持仓组合体检"""
    from modules.ai_analyzer import portfolio_health_check
    return portfolio_health_check(positions)


@router.get("/ai/status")
async def ai_status():
    """AI服务状态"""
    from modules.ai_analyzer import get_ai_status
    return get_ai_status()


@router.post("/ai/offline-mode")
async def ai_set_offline(enabled: bool = Body(True)):
    """设置离线模式"""
    from modules.ai_analyzer import set_offline_mode
    return set_offline_mode(enabled)


@router.get("/ai/usage")
async def ai_usage():
    """AI用量统计"""
    from modules.sim_executor import get_ai_usage
    return get_ai_usage()


@router.get("/ai/conversations")
async def ai_conversations(code: str = None, limit: int = 20):
    """AI对话历史"""
    from modules.ai_analyzer import get_conversations
    return {"conversations": get_conversations(code, limit)}


@router.post("/ai/risk-profile")
async def ai_update_risk_profile(**kwargs):
    """更新风险偏好"""
    from modules.ai_analyzer import update_risk_profile
    return update_risk_profile(**kwargs)


@router.get("/ai/risk-profile")
async def ai_get_risk_profile():
    """获取风险偏好"""
    from modules.ai_analyzer import get_risk_profile
    return get_risk_profile()


# ========== 模块7: 模拟执行 ==========

@router.get("/sim/accounts")
async def sim_accounts():
    """虚拟账户列表"""
    from modules.sim_executor import get_accounts
    return get_accounts()


@router.post("/sim/accounts")
async def sim_add_account(name: str = Body(...), initial_cash: float = Body(100000)):
    """添加虚拟账户"""
    from modules.sim_executor import add_account
    return add_account(name, initial_cash)


@router.post("/sim/accounts/switch")
async def sim_switch_account(account_id: str = Body(...)):
    """切换账户"""
    from modules.sim_executor import switch_account
    return switch_account(account_id)


@router.post("/sim/orders")
async def sim_place_order(
    account_id: str = Body(...), code: str = Body(...), name: str = Body(...),
    price: float = Body(...), shares: float = Body(...),
    order_type: str = Body("market"), limit_price: float = Body(None),
    action: str = Body("buy"), market: str = Body("A"),
):
    """模拟委托"""
    from modules.sim_executor import place_order
    return place_order(account_id, code, name, price, shares, order_type, limit_price, action, market)


@router.post("/sim/orders/cancel")
async def sim_cancel_order(order_id: str = Body(...)):
    """撤单"""
    from modules.sim_executor import cancel_order
    return cancel_order(order_id)


@router.get("/sim/orders")
async def sim_orders(account_id: str = None, status: str = None):
    """订单列表"""
    from modules.sim_executor import get_orders
    return {"orders": get_orders(account_id, status)}


@router.post("/sim/import-csv")
async def sim_import_csv(file_path: str = Body(...), account_id: str = Body("default")):
    """CSV导入持仓"""
    from modules.sim_executor import import_positions_from_csv
    return import_positions_from_csv(file_path, account_id)


@router.post("/sim/reviews")
async def sim_save_review(review_type: str = Body(...), content: str = Body(...), period: str = Body("daily")):
    """保存AI复盘"""
    from modules.sim_executor import save_review
    return save_review(review_type, content, period)


@router.get("/sim/reviews")
async def sim_get_reviews(period: str = None, limit: int = 10):
    """获取复盘记录"""
    from modules.sim_executor import get_reviews
    return {"reviews": get_reviews(period, limit)}


# ========== 模块7: 配置管理 ==========

@router.get("/config")
async def get_config():
    """获取配置"""
    from modules.sim_executor import get_module_config
    return get_module_config()


@router.post("/config")
async def update_config(**kwargs):
    """更新配置"""
    from modules.sim_executor import update_module_config
    return update_module_config(**kwargs)


@router.post("/config/keywords/block")
async def block_keyword(keyword: str = Body(...)):
    """屏蔽关键词"""
    from modules.sim_executor import add_blocked_keyword
    return {"blocked_keywords": add_blocked_keyword(keyword)}


@router.post("/config/migrate")
async def migrate_data(new_path: str = Body(...)):
    """数据迁移"""
    from modules.sim_executor import migrate_data
    return migrate_data(new_path)


# ========== 模块8: 启动自检 ==========

@router.get("/startup/check")
async def startup_check():
    """开机自检"""
    from modules.startup_checker import run_startup_check, get_latest_check
    return {"latest": get_latest_check(), "new": run_startup_check()}


@router.get("/startup/memory")
async def memory_check():
    """内存监控"""
    from modules.startup_checker import check_memory_usage, check_data_redundancy
    return {"memory": check_memory_usage(), "data": check_data_redundancy()}


@router.get("/startup/ai-fallback")
async def ai_fallback_check():
    """AI降级检查"""
    from modules.startup_checker import ensure_ai_fallback
    return ensure_ai_fallback()


@router.post("/toggle")
async def toggle_modules(enabled: bool = Body(True)):
    """新增功能总开关"""
    from modules.startup_checker import toggle_modules
    return toggle_modules(enabled)


@router.get("/toggle")
async def get_toggle():
    """获取开关状态"""
    from modules.startup_checker import is_module_enabled
    return {"enabled": is_module_enabled()}


# ========== 模块6: 前端可视化数据 ==========

@router.get("/visual/dashboard")
async def visual_dashboard():
    """资产总仪表盘数据"""
    from modules.db_manager import check_db_health
    from modules.startup_checker import check_memory_usage
    
    db_health = check_db_health()
    memory = check_memory_usage()
    
    return {
        "db_health": db_health,
        "memory": memory,
        "module_status": {
            "db_manager": True,
            "auto_fetcher": True,
            "indicator_engine": True,
            "decision_engine": True,
            "ai_analyzer": True,
            "sim_executor": True,
            "startup_checker": True,
        },
    }


@router.get("/visual/support-resistance")
async def support_resistance(code: str, history: list = Query(None)):
    """计算支撑压力线"""
    if not history:
        from data.market import get_stock_history
        history = get_stock_history(code, days=90)
    
    if not history:
        return {"error": "无数据"}
    
    closes = [float(h["close"]) if isinstance(h, dict) else float(h[2]) for h in history]
    if len(closes) < 20:
        return {"error": "数据不足"}
    
    # 简单支撑压力计算
    highs = [float(h["high"]) if isinstance(h, dict) else float(h[3]) for h in history]
    lows = [float(h["low"]) if isinstance(h, dict) else float(h[4]) for h in history]
    
    current = closes[-1]
    support = min(lows[-20:])  # 20日最低点作为支撑
    resistance = max(highs[-20:])  # 20日最高点作为压力
    
    return {
        "code": code,
        "current_price": current,
        "support": round(support, 3),
        "resistance": round(resistance, 3),
        "support_distance_pct": round((current - support) / current * 100, 2),
        "resistance_distance_pct": round((resistance - current) / current * 100, 2),
    }


@router.get("/visual/breakeven")
async def breakeven_calc(entry_price: float, shares: float, current_price: float = None):
    """亏损回本计算"""
    if not current_price or current_price >= entry_price:
        return {"message": "当前未亏损或已回本"}
    
    loss_pct = (entry_price - current_price) / entry_price * 100
    # 需要涨多少才能回本
    need_rise = (entry_price - current_price) / current_price * 100
    
    # 补仓计算
    results = []
    for add_ratio in [0.25, 0.5, 1.0, 2.0]:
        add_shares = shares * add_ratio
        total_shares = shares + add_shares
        total_cost = shares * entry_price + add_shares * current_price
        new_avg_cost = total_cost / total_shares
        results.append({
            "add_ratio": f"{add_ratio*100:.0f}%",
            "add_shares": add_shares,
            "new_avg_cost": round(new_avg_cost, 3),
            "need_rise_to_breakeven": round((new_avg_cost - current_price) / current_price * 100, 2) if current_price > 0 else 0,
        })
    
    return {
        "entry_price": entry_price,
        "current_price": current_price,
        "loss_pct": round(loss_pct, 2),
        "need_rise_pct": round(need_rise, 2),
        "dilution_options": results,
    }


@router.get("/visual/heatmap")
async def monthly_heatmap(year: int = None, month: int = None):
    """月度盈亏热力日历"""
    from datetime import datetime
    if not year:
        year = datetime.now().year
    if not month:
        month = datetime.now().month
    
    import calendar
    cal = calendar.monthcalendar(year, month)
    
    # 模拟数据（实际应从交易记录中获取）
    return {
        "year": year,
        "month": month,
        "calendar": cal,
        "message": "热力日历数据需要从实际交易记录中生成",
    }