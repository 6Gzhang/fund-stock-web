"""
模块5: AI智能综合分析
- 主力模型：硅基流动云端免费Qwen2.5-7B
- 备用兜底模型：DeepSeek
- 单只股票支撑压力、估值、趋势诊断
- 持仓组合体检、行业风险统计
- 3-10只标的横向打分对比
- 本地保存个人风险偏好、历史对话归档
- 精简/详细分析报告一键切换
- 统一完整风险提示模板
- 长期持有与动态调仓收益对比
- 硅基接口断开自动切换纯本地指标离线模式
"""
import os
import json
import time
import threading
import hashlib
from datetime import datetime
from typing import Optional

MODULE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(MODULE_DIR, "Data")
AI_CACHE_DIR = os.path.join(DATA_DIR, "ai_cache")
os.makedirs(AI_CACHE_DIR, exist_ok=True)

# AI配置
AI_CONFIG = {
    "primary": {
        "name": "siliconflow",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "api_base": "https://api.siliconflow.cn/v1/chat/completions",
        "api_key": "",  # 从环境变量或配置读取
        "free": True,
    },
    "fallback": {
        "name": "deepseek",
        "model": "deepseek-chat",
        "api_base": "https://api.deepseek.com/v1/chat/completions",
        "api_key": "",
        "free": False,
    },
    "active": "primary",
    "offline_mode": False,
}

# 风险偏好
RISK_PROFILE = {
    "max_single_position": 0.3,  # 单只最大仓位
    "max_sector_exposure": 0.5,  # 单行业最大仓位
    "stop_loss_pct": 5.0,        # 止损比例
    "take_profit_pct": 15.0,     # 止盈比例
    "max_drawdown_tolerance": 20.0,  # 最大回撤容忍
    "preferred_holding_period": "medium",  # short/medium/long
}

# 对话归档
_conversation_archive = []
_conversation_lock = threading.Lock()


def _cache_key(*args) -> str:
    """生成缓存key"""
    raw = "|".join(str(a) for a in args)
    return hashlib.md5(raw.encode()).hexdigest()


def _load_cache(cache_key: str):
    """加载缓存"""
    cache_file = os.path.join(AI_CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file) as f:
                data = json.load(f)
                if time.time() - data.get("ts", 0) < 3600:  # 1小时缓存
                    return data.get("result")
        except Exception:
            pass
    return None


def _save_cache(cache_key: str, result: dict):
    """保存缓存"""
    cache_file = os.path.join(AI_CACHE_DIR, f"{cache_key}.json")
    with open(cache_file, "w") as f:
        json.dump({"ts": time.time(), "result": result}, f, ensure_ascii=False)


def _call_ai_api(prompt: str, use_fallback: bool = False) -> Optional[str]:
    """调用AI API（主/备自动切换）"""
    config = AI_CONFIG["fallback"] if use_fallback else AI_CONFIG["primary"]
    
    # 优先级：配置 > 环境变量
    api_key = config["api_key"]
    if not api_key:
        if use_fallback:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        else:
            api_key = os.environ.get("SILICONFLOW_API_KEY", "")
    
    # 也从通用配置文件读
    if not api_key:
        try:
            from modules.sim_executor import get_module_config
            cfg = get_module_config()
            if use_fallback:
                api_key = cfg.get("deepseek_api_key", "")
            else:
                api_key = cfg.get("siliconflow_api_key", "")
        except Exception:
            pass
    
    if not api_key:
        return None
    
    try:
        import urllib.request
        import urllib.error
        
        data = json.dumps({
            "model": config["model"],
            "messages": [
                {"role": "system", "content": "你是一个专业的股票分析助手，请用中文回答，给出简洁专业的分析。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
        }).encode("utf-8")
        
        req = urllib.request.Request(
            config["api_base"],
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        print(f"[模块5] AI API调用失败: {e}")
        return None


def _offline_analysis(code: str, name: str, price: float, change_pct: float, indicators: dict) -> dict:
    """离线模式：纯本地指标分析"""
    from modules.indicator_engine import compute_all_indicators, generate_signals
    
    signals = generate_signals(indicators)
    
    buy_reasons = []
    sell_reasons = []
    
    if signals["level"] in ("strong_buy", "buy"):
        buy_reasons = [s["reason"] for s in signals.get("buy", [])]
    elif signals["level"] in ("strong_sell", "sell"):
        sell_reasons = [s["reason"] for s in signals.get("sell", [])]
    
    return {
        "code": code,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "recommendation": signals["level"],
        "confidence": min(90, abs(signals["net_score"]) * 20),
        "buy_reasons": buy_reasons,
        "sell_reasons": sell_reasons,
        "target_price": round(price * 1.1, 2) if signals["net_score"] > 0 else round(price * 0.95, 2),
        "risk_level": "low" if signals["net_score"] > 3 else "medium" if signals["net_score"] > 0 else "high",
        "risk_detail": {
            "industry_risk": "低" if signals["net_score"] > 2 else "中",
            "valuation_risk": "中",
            "volatility_risk": "中" if indicators.get("volatility", 0) < 3 else "高",
            "liquidity_risk": "低",
        },
        "analysis_mode": "offline",
        "indicators": indicators,
    }


def _online_analysis(code: str, name: str, price: float, change_pct: float, indicators: dict) -> dict:
    """在线AI分析"""
    # 构建提示词
    prompt = f"""分析股票：{name}({code})，当前价格{price}，今日涨跌幅{change_pct:+.2f}%。

技术指标摘要：
- RSI: {indicators.get('rsi', {}).get('rsi', 'N/A')}
- MACD: {'金叉' if indicators.get('macd', {}).get('golden_cross') else '死叉'}
- KDJ: K={indicators.get('kdj', {}).get('k')}, D={indicators.get('kdj', {}).get('d')}, J={indicators.get('kdj', {}).get('j')}
- 布林带位置: {indicators.get('bollinger', {}).get('position', 'N/A')}%
- 250日均线: {indicators.get('ma250', {}).get('trend', 'unknown')}

请分析并返回JSON格式：
{{
    "recommendation": "buy/hold/sell",
    "confidence": 0-100,
    "buy_reasons": ["理由1", "理由2"],
    "sell_reasons": ["理由1", "理由2"],
    "target_price": 数字,
    "risk_level": "low/medium/high",
    "support_level": "支撑位",
    "resistance_level": "压力位",
    "trend_analysis": "趋势分析",
    "valuation_opinion": "估值看法",
    "short_term_outlook": "短期展望",
    "medium_term_outlook": "中期展望"
}}"""
    
    # 尝试主力模型
    response = _call_ai_api(prompt, use_fallback=False)
    if not response:
        # 尝试备用模型
        response = _call_ai_api(prompt, use_fallback=True)
    
    if response:
        try:
            # 尝试解析JSON
            import re
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                ai_result = json.loads(json_match.group())
                ai_result["code"] = code
                ai_result["name"] = name
                ai_result["price"] = price
                ai_result["change_pct"] = change_pct
                ai_result["analysis_mode"] = "ai_online"
                ai_result["raw_response"] = response
                ai_result["indicators"] = indicators
                return ai_result
        except Exception as e:
            print(f"[模块5] AI响应解析失败: {e}")
    
    # 降级到离线模式
    return _offline_analysis(code, name, price, change_pct, indicators)


def analyze_stock_full(code: str, name: str, price: float, change_pct: float, history: list, mode: str = "auto") -> dict:
    """
    完整AI分析（自动选择在线/离线模式）
    mode: auto(自动)/online(强制在线)/offline(强制离线)
    """
    from modules.indicator_engine import compute_all_indicators
    
    cache_key = _cache_key("full", code, price, len(history))
    cached = _load_cache(cache_key)
    if cached:
        return cached
    
    indicators = compute_all_indicators(history)
    
    if mode == "offline" or AI_CONFIG["offline_mode"]:
        result = _offline_analysis(code, name, price, change_pct, indicators)
    elif mode == "online":
        result = _online_analysis(code, name, price, change_pct, indicators)
    else:
        # auto模式：先尝试在线，失败则离线
        result = _online_analysis(code, name, price, change_pct, indicators)
        if result.get("analysis_mode") == "offline":
            result["analysis_mode"] = "offline_fallback"
    
    _save_cache(cache_key, result)
    return result


def batch_analyze(stocks: list, mode: str = "auto", max_workers: int = 5) -> list:
    """批量分析（3-10只标的横向对比）"""
    import concurrent.futures
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for s in stocks:
            future = executor.submit(
                analyze_stock_full,
                s["code"], s["name"], s["price"], s["change_pct"], s.get("history", []), mode
            )
            futures[future] = s
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                s = futures[future]
                results.append({"code": s["code"], "name": s["name"], "error": str(e)})
    
    # 横向对比排序
    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return results


def compare_scores(results: list) -> dict:
    """横向打分对比"""
    if not results:
        return {}
    
    scored = [r for r in results if "recommendation" in r]
    if not scored:
        return {}
    
    buy_count = sum(1 for r in scored if r["recommendation"] in ("buy", "strong_buy"))
    hold_count = sum(1 for r in scored if r["recommendation"] == "hold")
    sell_count = sum(1 for r in scored if r["recommendation"] in ("sell", "strong_sell"))
    
    best = max(scored, key=lambda x: x.get("confidence", 0))
    worst = min(scored, key=lambda x: x.get("confidence", 0))
    
    return {
        "total": len(scored),
        "buy_count": buy_count,
        "hold_count": hold_count,
        "sell_count": sell_count,
        "best_pick": {"code": best["code"], "name": best["name"], "confidence": best["confidence"]},
        "worst_pick": {"code": worst["code"], "name": worst["name"], "confidence": worst["confidence"]},
        "avg_confidence": round(sum(r.get("confidence", 0) for r in scored) / len(scored), 1),
        "market_sentiment": "偏多" if buy_count > sell_count else "偏空" if sell_count > buy_count else "中性",
    }


def portfolio_health_check(positions: list) -> dict:
    """持仓组合体检"""
    if not positions:
        return {"status": "empty", "message": "无持仓"}
    
    total_value = sum(p.get("market_value", 0) for p in positions)
    total_cost = sum(p.get("cost", 0) for p in positions)
    total_pnl = total_value - total_cost
    
    sectors = {}
    for p in positions:
        sector = p.get("sector", "未知")
        sectors[sector] = sectors.get(sector, 0) + p.get("market_value", 0)
    
    # 行业集中度风险
    sector_ratios = {k: round(v / total_value * 100, 1) for k, v in sectors.items()} if total_value > 0 else {}
    high_concentration = {k: v for k, v in sector_ratios.items() if v > 30}
    
    # 盈亏分析
    winners = [p for p in positions if p.get("pnl", 0) > 0]
    losers = [p for p in positions if p.get("pnl", 0) <= 0]
    
    return {
        "status": "healthy" if total_pnl > 0 else "warning",
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
        "position_count": len(positions),
        "winner_count": len(winners),
        "loser_count": len(losers),
        "sector_exposure": sector_ratios,
        "high_concentration_warning": high_concentration,
        "risk_level": "high" if len(high_concentration) > 0 else "medium" if len(losers) > len(winners) else "low",
    }


def compare_hold_vs_trade(hold_return: float, trade_return: float, period: str = "1年") -> dict:
    """长期持有 vs 动态调仓收益对比"""
    diff = trade_return - hold_return
    return {
        "period": period,
        "hold_return": round(hold_return, 2),
        "trade_return": round(trade_return, 2),
        "difference": round(diff, 2),
        "winner": "动态调仓" if diff > 0 else "长期持有" if diff < 0 else "持平",
        "suggestion": "动态调仓优于长期持有" if diff > 3 else "长期持有更稳健" if diff < -3 else "两者差异不大",
    }


def save_conversation(code: str, name: str, question: str, answer: str):
    """保存对话历史"""
    with _conversation_lock:
        _conversation_archive.append({
            "code": code,
            "name": name,
            "question": question,
            "answer": answer,
            "timestamp": datetime.now().isoformat(),
        })
        # 只保留最近100条
        if len(_conversation_archive) > 100:
            _conversation_archive.pop(0)


def get_conversations(code: str = None, limit: int = 20):
    """获取对话历史"""
    with _conversation_lock:
        if code:
            return [c for c in _conversation_archive if c["code"] == code][-limit:]
        return _conversation_archive[-limit:]


def update_risk_profile(**kwargs):
    """更新风险偏好"""
    for k, v in kwargs.items():
        if k in RISK_PROFILE:
            RISK_PROFILE[k] = v
    return dict(RISK_PROFILE)


def get_risk_profile():
    """获取风险偏好"""
    return dict(RISK_PROFILE)


def set_offline_mode(enabled: bool):
    """设置离线模式"""
    AI_CONFIG["offline_mode"] = enabled
    return {"offline_mode": enabled}


def get_ai_status():
    """获取AI服务状态"""
    return {
        "active_model": AI_CONFIG["active"],
        "offline_mode": AI_CONFIG["offline_mode"],
        "primary_available": bool(AI_CONFIG["primary"]["api_key"] or os.environ.get("SILICONFLOW_API_KEY")),
        "fallback_available": bool(AI_CONFIG["fallback"]["api_key"] or os.environ.get("DEEPSEEK_API_KEY")),
        "conversation_count": len(_conversation_archive),
    }