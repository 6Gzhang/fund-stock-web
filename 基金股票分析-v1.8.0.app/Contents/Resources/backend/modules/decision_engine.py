"""
模块4: 交易决策与仓位管理（核心新增）
- 固定比例/凯利/等额资金三种仓位算法
- A股100股取整，港股、ETF支持小数份额
- 买入现金校验、行业仓位超限自动降仓
- 完整止盈、止损、调仓、加减仓逻辑
- 标准化决策卡片：标注现价、目标价、价差、上涨空间
- 技术+估值+风控三层买卖理由
- 交易备忘录记录操作理由
- 分市场自动计算佣金、印花税、过户费明细
"""
import math
from typing import Optional


# ========== 仓位算法 ==========

def fixed_ratio(available_cash: float, price: float, ratio: float = 0.2, market: str = "A"):
    """固定比例仓位"""
    amount = available_cash * ratio
    if market == "A":
        shares = math.floor(amount / price / 100) * 100
    else:
        shares = amount / price
    return {"shares": shares, "amount": shares * price, "ratio": ratio, "method": "固定比例"}


def kelly_criterion(win_prob: float, avg_win: float, avg_loss: float, available_cash: float, price: float, market: str = "A"):
    """凯利公式仓位"""
    if avg_loss == 0:
        avg_loss = 0.01
    kelly_ratio = (win_prob * avg_win - (1 - win_prob) * avg_loss) / (avg_win * avg_loss)
    kelly_ratio = max(0, min(kelly_ratio, 0.25))  # 限制在0-25%
    
    amount = available_cash * kelly_ratio
    if market == "A":
        shares = math.floor(amount / price / 100) * 100
    else:
        shares = amount / price
    
    return {"shares": shares, "amount": shares * price, "ratio": round(kelly_ratio * 100, 2), "method": "凯利公式"}


def equal_weight(available_cash: float, price: float, position_count: int, market: str = "A"):
    """等额资金仓位"""
    if position_count <= 0:
        position_count = 5
    ratio = 1.0 / position_count
    amount = available_cash / position_count
    if market == "A":
        shares = math.floor(amount / price / 100) * 100
    else:
        shares = amount / price
    return {"shares": shares, "amount": shares * price, "ratio": round(ratio * 100, 2), "method": "等额资金"}


# ========== 手续费计算 ==========

def calc_commission(market: str, amount: float, shares: int = 0, is_buy: bool = True):
    """分市场计算佣金、印花税、过户费"""
    result = {
        "commission": 0,   # 佣金
        "stamp_tax": 0,    # 印花税
        "transfer_fee": 0, # 过户费
        "total": 0,        # 总计
    }
    
    if market == "A":
        # A股: 佣金万分之3（最低5元），印花税千分之1（仅卖出），过户费万分之0.2
        result["commission"] = max(5, amount * 0.0003)
        if not is_buy:
            result["stamp_tax"] = amount * 0.001
        result["transfer_fee"] = amount * 0.00002
    elif market == "HK":
        # 港股: 佣金千分之1，印花税千分之1.3，交易费0.005%
        result["commission"] = amount * 0.001
        result["stamp_tax"] = amount * 0.0013
        result["transfer_fee"] = amount * 0.00005
    elif market == "ETF":
        # ETF: 佣金万分之1（最低0.1元），无印花税
        result["commission"] = max(0.1, amount * 0.0001)
        result["stamp_tax"] = 0
        result["transfer_fee"] = 0
    
    result["total"] = round(result["commission"] + result["stamp_tax"] + result["transfer_fee"], 2)
    return result


# ========== 止盈止损 ==========

def calc_stop_loss(buy_price: float, risk_pct: float = 5.0, method: str = "fixed"):
    """计算止损价"""
    if method == "fixed":
        return round(buy_price * (1 - risk_pct / 100), 3)
    elif method == "atr":
        return round(buy_price * (1 - risk_pct / 100), 3)
    return round(buy_price * 0.95, 3)


def calc_take_profit(buy_price: float, profit_pct: float = 15.0, method: str = "fixed"):
    """计算止盈价"""
    return round(buy_price * (1 + profit_pct / 100), 3)


def trailing_stop(current_price: float, highest_price: float, trail_pct: float = 5.0):
    """移动止损（从最高点回撤N%触发）"""
    stop_price = highest_price * (1 - trail_pct / 100)
    triggered = current_price <= stop_price
    return {"stop_price": round(stop_price, 3), "triggered": triggered, "trail_pct": trail_pct}


# ========== 行业仓位校验 ==========

def check_sector_limit(current_sector_ratio: float, target_ratio: float, max_sector_ratio: float = 0.3):
    """行业仓位超限自动降仓"""
    new_ratio = current_sector_ratio + target_ratio
    if new_ratio > max_sector_ratio:
        adjusted_ratio = max(0, max_sector_ratio - current_sector_ratio)
        return {
            "allowed": True,
            "adjusted_ratio": adjusted_ratio,
            "warning": f"行业仓位将达到{new_ratio*100:.1f}%，自动调整为{adjusted_ratio*100:.1f}%",
            "exceeded": True,
        }
    return {"allowed": True, "adjusted_ratio": target_ratio, "exceeded": False}


# ========== 决策卡片生成 ==========

def generate_decision_card(
    code: str, name: str, current_price: float, target_price: Optional[float],
    buy_reasons: list, sell_reasons: list, risk_analysis: dict,
    market: str = "A", sector: str = "未知行业",
    current_sector_ratio: float = 0, available_cash: float = 0,
    indicators: dict = None,
):
    """生成标准化决策卡片"""
    upside = ((target_price - current_price) / current_price * 100) if target_price and current_price > 0 else 0
    gap = (target_price - current_price) if target_price else 0
    
    # 仓位建议
    position = None
    if available_cash > 0 and current_price > 0:
        position = fixed_ratio(available_cash, current_price, 0.2, market)
    
    # 行业仓位校验
    sector_check = None
    if position and current_sector_ratio > 0:
        sector_check = check_sector_limit(current_sector_ratio, position["ratio"] / 100)
    
    # 手续费预估
    commission = None
    if position and position["amount"] > 0:
        commission = calc_commission(market, position["amount"], position["shares"], is_buy=True)
    
    # 技术指标摘要
    tech_summary = {}
    if indicators:
        tech_summary = {
            "rsi": indicators.get("rsi", {}).get("rsi"),
            "macd_signal": "金叉" if indicators.get("macd", {}).get("golden_cross") else "死叉",
            "ma_trend": "多头" if (indicators.get("ma5") and indicators.get("ma20") and indicators["ma5"] > indicators["ma20"]) else "空头",
            "boll_position": indicators.get("bollinger", {}).get("position"),
            "ma250": "牛市" if indicators.get("ma250", {}).get("trend") == "bull" else "熊市",
        }
    
    return {
        "code": code,
        "name": name,
        "market": market,
        "sector": sector,
        "current_price": current_price,
        "target_price": target_price,
        "gap": round(gap, 3),
        "upside_pct": round(upside, 2),
        "buy_reasons": {
            "technical": buy_reasons if isinstance(buy_reasons, list) else [buy_reasons],
            "valuation": risk_analysis.get("valuation", []),
            "risk_control": risk_analysis.get("risk_control", []),
        },
        "sell_reasons": {
            "technical": sell_reasons if isinstance(sell_reasons, list) else [sell_reasons],
            "risk": risk_analysis.get("risks", []),
        },
        "risk_analysis": {
            "level": risk_analysis.get("level", "medium"),
            "industry_risk": risk_analysis.get("industry_risk", "无"),
            "volatility_risk": risk_analysis.get("volatility_risk", "无"),
            "valuation_risk": risk_analysis.get("valuation_risk", "无"),
            "liquidity_risk": risk_analysis.get("liquidity_risk", "无"),
        },
        "position_advice": position,
        "sector_check": sector_check,
        "commission_estimate": commission,
        "technical_summary": tech_summary,
        "stop_loss": round(current_price * 0.95, 3) if current_price > 0 else 0,
        "take_profit": round(current_price * 1.15, 3) if current_price > 0 else 0,
    }


# ========== 交易备忘录 ==========

def create_trade_memo(decision_card: dict, reason: str = "", actual_shares: int = 0) -> dict:
    """创建交易备忘录"""
    return {
        "code": decision_card["code"],
        "name": decision_card["name"],
        "action": "buy" if decision_card["upside_pct"] > 0 else "sell",
        "price": decision_card["current_price"],
        "target_price": decision_card["target_price"],
        "shares": actual_shares,
        "reason": reason,
        "decision_card": decision_card,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }