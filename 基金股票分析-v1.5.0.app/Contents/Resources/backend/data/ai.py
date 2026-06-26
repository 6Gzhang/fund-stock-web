"""
AI 智能分析模块 - 基于 OpenAI 兼容 API + 多维度技术分析
"""
import os
import json
import math
from openai import OpenAI

# 从环境变量读取 API 配置
API_KEY = os.environ.get("OPENAI_API_KEY", "")
API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
MODEL = os.environ.get("AI_MODEL", "gpt-4o-mini")

client = None


def get_client():
    global client
    if client is None and API_KEY:
        client = OpenAI(api_key=API_KEY, base_url=API_BASE)
    return client


def analyze_stock(code: str, name: str, price: float, change_pct: float,
                  history: list[dict], market_indices: dict) -> dict:
    """
    使用 AI 分析股票，给出买入/卖出/持有建议
    """
    c = get_client()
    if c is None:
        return _advanced_technical_analysis(code, name, price, change_pct, history, market_indices)

    # 构建最近走势摘要
    recent = history[-20:] if len(history) > 20 else history
    trend_summary = "\n".join([
        f"{d['date']}: 开{d['open']:.2f} 高{d['high']:.2f} 低{d['low']:.2f} 收{d['close']:.2f} 量{d['volume']:.0f}"
        for d in recent
    ])

    market_summary = "\n".join([
        f"{k}: {v['price']:.2f} (涨跌幅 {v['change_pct']:+.2f}%)" for k, v in market_indices.items()
    ]) if market_indices else "无市场指数数据"

    # 先获取技术指标摘要
    tech = _compute_indicators(history, price)

    prompt = f"""你是一个资深股票分析师，请从技术面、资金面、市场情绪多维度分析以下股票。

股票代码: {code}
股票名称: {name}
当前价格: {price:.2f}
今日涨跌幅: {change_pct:+.2f}%

技术指标速览:
- MA5(5日均线): {tech['ma5']:.2f}
- MA10(10日均线): {tech['ma10']:.2f}
- MA20(20日均线): {tech['ma20']:.2f}
- MACD: {tech['macd']:.4f} (DIF: {tech['dif']:.4f}, DEA: {tech['dea']:.4f})
- RSI(14): {tech['rsi']:.1f}
- KDJ: K={tech['k']:.1f}, D={tech['d']:.1f}, J={tech['j']:.1f}
- 布林带: 上轨{tech['boll_upper']:.2f}, 中轨{tech['boll_mid']:.2f}, 下轨{tech['boll_lower']:.2f}
- 近5日成交量趋势: {tech['vol_trend']}
- 近5日涨跌比: {tech['up_down_ratio']:.2f}

大盘指数:
{market_summary}

最近20个交易日走势:
{trend_summary}

请以 JSON 格式回答，必须包含以下字段：
- recommendation: "buy"（买入）/ "sell"（卖出）/ "hold"（持有）
- confidence: 0-1之间的置信度
- reasoning: 详细分析理由（200-400字），必须包含：
  1) 技术面分析（均线、MACD、RSI等指标信号）
  2) 资金面分析（成交量变化、资金流向判断）
  3) 市场环境分析（大盘走势对比）
  4) 综合结论与操作建议
- suggested_ratio: 建议仓位占比（0-1之间）
- buy_reasons: 列出3-5条买入理由（如果推荐买入）或风险提示（如果推荐卖出/持有）
- sell_reasons: 列出3-5条卖出理由或需要警惕的信号
- risk_level: 风险等级，可选 "low"（低风险）/ "medium"（中风险）/ "high"（高风险）
- target_price: 短期目标价格（如果是buy，给上涨目标；如果是sell，给下跌目标；hold给null）

只返回 JSON，不要包含其他内容。"""

    try:
        response = c.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        ai_result = json.loads(content)
        # 合并技术指标
        ai_result["indicators"] = tech
        ai_result["ai_available"] = True
        return ai_result
    except Exception as e:
        print(f"AI 分析失败，回退技术分析: {e}")
        return _advanced_technical_analysis(code, name, price, change_pct, history, market_indices)


def _compute_indicators(history: list[dict], price: float) -> dict:
    """计算多维度技术指标"""
    if not history or len(history) < 5:
        return {
            "ma5": price, "ma10": price, "ma20": price,
            "macd": 0, "dif": 0, "dea": 0,
            "rsi": 50, "k": 50, "d": 50, "j": 50,
            "boll_upper": price * 1.05, "boll_mid": price, "boll_lower": price * 0.95,
            "vol_trend": "数据不足", "up_down_ratio": 1.0,
        }

    closes = [d["close"] for d in history]
    highs = [d["high"] for d in history]
    lows = [d["low"] for d in history]
    volumes = [d["volume"] for d in history]

    # 均线
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else ma5
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else ma5

    # EMA for MACD
    def ema(data, n):
        if len(data) < n:
            return sum(data) / len(data)
        k = 2 / (n + 1)
        result = sum(data[:n]) / n
        for x in data[n:]:
            result = x * k + result * (1 - k)
        return result

    dif = ema(closes, 12) - ema(closes, 26) if len(closes) >= 26 else 0
    dea = ema([dif] * 9, 9) if dif else 0
    macd = 2 * (dif - dea)

    # RSI(14)
    rsi = _compute_rsi(closes, 14)

    # KDJ
    k, d, j = _compute_kdj(highs, lows, closes, 9)

    # 布林带
    if len(closes) >= 20:
        boll_mid = ma20
        std = (sum((c - boll_mid) ** 2 for c in closes[-20:]) / 20) ** 0.5
        boll_upper = boll_mid + 2 * std
        boll_lower = boll_mid - 2 * std
    else:
        boll_mid = ma5
        boll_upper = boll_mid * 1.05
        boll_lower = boll_mid * 0.95

    # 成交量趋势
    if len(volumes) >= 5:
        vol_avg_5 = sum(volumes[-5:]) / 5
        vol_avg_10 = sum(volumes[-10:]) / 10 if len(volumes) >= 10 else vol_avg_5
        if vol_avg_5 > vol_avg_10 * 1.5:
            vol_trend = "放量"
        elif vol_avg_5 < vol_avg_10 * 0.5:
            vol_trend = "缩量"
        else:
            vol_trend = "持平"
    else:
        vol_trend = "数据不足"

    # 涨跌比
    up_count = sum(1 for i in range(1, min(len(closes), 6)) if closes[-i] > closes[-i-1])
    down_count = sum(1 for i in range(1, min(len(closes), 6)) if closes[-i] < closes[-i-1])
    up_down_ratio = up_count / down_count if down_count > 0 else up_count

    return {
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "macd": round(macd, 4),
        "dif": round(dif, 4),
        "dea": round(dea, 4),
        "rsi": round(rsi, 1),
        "k": round(k, 1),
        "d": round(d, 1),
        "j": round(j, 1),
        "boll_upper": round(boll_upper, 2),
        "boll_mid": round(boll_mid, 2),
        "boll_lower": round(boll_lower, 2),
        "vol_trend": vol_trend,
        "up_down_ratio": round(up_down_ratio, 2),
    }


def _compute_rsi(closes: list, n: int = 14) -> float:
    if len(closes) < n + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains[-n:]) / n
    avg_loss = sum(losses[-n:]) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _compute_kdj(highs: list, lows: list, closes: list, n: int = 9):
    if len(closes) < n:
        return 50.0, 50.0, 50.0
    k_values, d_values = [], []
    for i in range(n - 1, len(closes)):
        h = max(highs[i-n+1:i+1])
        l = min(lows[i-n+1:i+1])
        rsv = ((closes[i] - l) / (h - l)) * 100 if h != l else 50
        prev_k = k_values[-1] if k_values else 50
        prev_d = d_values[-1] if d_values else 50
        k = prev_k * 2/3 + rsv * 1/3
        d = prev_d * 2/3 + k * 1/3
        k_values.append(k)
        d_values.append(d)
    latest_k = k_values[-1]
    latest_d = d_values[-1]
    latest_j = 3 * latest_k - 2 * latest_d
    return latest_k, latest_d, latest_j


def _advanced_technical_analysis(code: str, name: str, price: float, change_pct: float,
                                  history: list[dict], market_indices: dict) -> dict:
    """多维度技术分析（无 AI 时的完整回退方案）"""
    if not history or len(history) < 5:
        return {
            "recommendation": "hold",
            "confidence": 0.1,
            "reasoning": "数据不足，无法进行有效分析，建议观望等待更多数据。",
            "suggested_ratio": 0.0,
            "buy_reasons": ["暂无足够数据支持买入判断"],
            "sell_reasons": ["暂无足够数据支持卖出判断"],
            "risk_level": "high",
            "target_price": None,
            "indicators": _compute_indicators(history, price),
            "ai_available": False,
        }

    tech = _compute_indicators(history, price)
    closes = [d["close"] for d in history]
    volumes = [d["volume"] for d in history]

    buy_reasons = []
    sell_reasons = []
    buy_score = 0
    sell_score = 0

    # === 均线分析 ===
    if price > tech["ma5"] > tech["ma10"] > tech["ma20"]:
        buy_reasons.append(f"多头排列：价格({price:.2f})站上MA5({tech['ma5']:.2f})、MA10({tech['ma10']:.2f})、MA20({tech['ma20']:.2f})，均线发散向上，上升趋势明确")
        buy_score += 3
    elif price > tech["ma5"] > tech["ma10"]:
        buy_reasons.append(f"短期均线金叉：价格站上5日线({tech['ma5']:.2f})和10日线({tech['ma10']:.2f})，短线偏多")
        buy_score += 2
    elif price < tech["ma5"] < tech["ma10"] < tech["ma20"]:
        sell_reasons.append(f"空头排列：价格({price:.2f})跌破MA5({tech['ma5']:.2f})、MA10({tech['ma10']:.2f})、MA20({tech['ma20']:.2f})，均线发散向下，下降趋势明显")
        sell_score += 3
    elif price < tech["ma5"] < tech["ma10"]:
        sell_reasons.append(f"短期均线死叉：价格跌破5日线({tech['ma5']:.2f})和10日线({tech['ma10']:.2f})，短线偏空")
        sell_score += 2

    # 价格与MA20的关系
    if price > tech["ma20"]:
        buy_reasons.append(f"价格站上20日均线({tech['ma20']:.2f})，中期趋势向好")
        buy_score += 1
    else:
        sell_reasons.append(f"价格低于20日均线({tech['ma20']:.2f})，中期趋势偏弱")
        sell_score += 1

    # === MACD 分析 ===
    if tech["macd"] > 0 and tech["dif"] > tech["dea"]:
        buy_reasons.append(f"MACD金叉运行中(DIF={tech['dif']:.4f}>DEA={tech['dea']:.4f})，MACD柱({tech['macd']:.4f})为正，多头动能持续")
        buy_score += 2
    elif tech["macd"] > 0:
        buy_reasons.append(f"MACD柱({tech['macd']:.4f})为正但DIF({tech['dif']:.4f})回落，多头动能减弱")
        buy_score += 1
        sell_reasons.append(f"MACD红柱缩短，DIF({tech['dif']:.4f})向DEA({tech['dea']:.4f})靠拢，关注是否形成死叉")
        sell_score += 1
    elif tech["macd"] < 0 and tech["dif"] < tech["dea"]:
        sell_reasons.append(f"MACD死叉运行中(DIF={tech['dif']:.4f}<DEA={tech['dea']:.4f})，MACD柱({tech['macd']:.4f})为负，空头动能持续")
        sell_score += 2
    elif tech["macd"] < 0:
        sell_reasons.append(f"MACD绿柱缩短，DIF({tech['dif']:.4f})向上修复，可能出现金叉")
        buy_reasons.append(f"MACD绿柱收敛，DIF({tech['dif']:.4f})拐头向上，关注金叉信号")
        buy_score += 1
        sell_score += 1

    # === RSI 分析 ===
    if tech["rsi"] < 30:
        buy_reasons.append(f"RSI({tech['rsi']:.1f})处于超卖区(<30)，短线存在技术性反弹需求")
        buy_score += 2
    elif tech["rsi"] < 40:
        buy_reasons.append(f"RSI({tech['rsi']:.1f})偏低，股价处于相对低位区域")
        buy_score += 1
    elif tech["rsi"] > 70:
        sell_reasons.append(f"RSI({tech['rsi']:.1f})处于超买区(>70)，短线回调风险较大")
        sell_score += 2
    elif tech["rsi"] > 60:
        sell_reasons.append(f"RSI({tech['rsi']:.1f})偏高，接近超买区域")
        sell_score += 1

    # === KDJ 分析 ===
    if tech["j"] < 0:
        buy_reasons.append(f"KDJ指标J值({tech['j']:.1f})进入负值超卖区，K({tech['k']:.1f})、D({tech['d']:.1f})低位，反弹概率大")
        buy_score += 2
    elif tech["j"] > 100:
        sell_reasons.append(f"KDJ指标J值({tech['j']:.1f})超过100超买区，K({tech['k']:.1f})、D({tech['d']:.1f})高位，短期有回调压力")
        sell_score += 2

    if tech["k"] > tech["d"]:
        buy_reasons.append(f"KDJ金叉：K值({tech['k']:.1f})上穿D值({tech['d']:.1f})，短线买入信号")
        buy_score += 1
    else:
        sell_reasons.append(f"KDJ死叉：K值({tech['k']:.1f})下穿D值({tech['d']:.1f})，短线卖出信号")
        sell_score += 1

    # === 布林带分析 ===
    if price < tech["boll_lower"]:
        buy_reasons.append(f"价格({price:.2f})跌破布林带下轨({tech['boll_lower']:.2f})，处于超跌状态，反弹概率较高")
        buy_score += 2
    elif price > tech["boll_upper"]:
        sell_reasons.append(f"价格({price:.2f})突破布林带上轨({tech['boll_upper']:.2f})，处于超买状态，注意回调风险")
        sell_score += 2
    elif price < tech["boll_mid"]:
        sell_reasons.append(f"价格({price:.2f})低于布林带中轨({tech['boll_mid']:.2f})，短期偏弱")
        sell_score += 1
    else:
        buy_reasons.append(f"价格({price:.2f})在布林带中轨({tech['boll_mid']:.2f})上方运行，短期偏强")
        buy_score += 1

    # === 成交量分析 ===
    vol_avg_5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 1
    vol_avg_10 = sum(volumes[-10:]) / 10 if len(volumes) >= 10 else vol_avg_5
    if tech["vol_trend"] == "放量":
        if tech["up_down_ratio"] > 1.5:
            buy_reasons.append(f"近5日放量上涨(涨跌比{tech['up_down_ratio']:.1f})，资金积极入场，量价配合良好")
            buy_score += 2
        elif tech["up_down_ratio"] < 0.7:
            sell_reasons.append(f"近5日放量下跌(涨跌比{tech['up_down_ratio']:.1f})，资金加速出逃，量价背离")
            sell_score += 2
    elif tech["vol_trend"] == "缩量":
        if tech["up_down_ratio"] > 1.5:
            buy_reasons.append(f"近5日缩量上涨(涨跌比{tech['up_down_ratio']:.1f})，上行动力不足，注意追高风险")
            sell_score += 1
        elif tech["up_down_ratio"] < 0.7:
            sell_reasons.append(f"近5日缩量下跌(涨跌比{tech['up_down_ratio']:.1f})，卖压减轻但买盘不积极")
            buy_score += 1

    # === 今日涨跌幅分析 ===
    if change_pct > 5:
        sell_reasons.append(f"今日涨幅{change_pct:+.2f}%较大，短线获利盘抛压增加，追高需谨慎")
        sell_score += 1
    elif change_pct < -5:
        buy_reasons.append(f"今日跌幅{change_pct:+.2f}%较大，恐慌性抛售后可能出现超跌反弹")
        buy_score += 1

    # === 大盘对比 ===
    market_avg = 0
    market_count = 0
    for v in market_indices.values():
        market_avg += v["change_pct"]
        market_count += 1
    if market_count > 0:
        market_avg /= market_count
        if change_pct > market_avg + 1:
            buy_reasons.append(f"今日涨幅{change_pct:+.2f}%跑赢大盘均值({market_avg:+.2f}%)，个股表现强势")
            buy_score += 1
        elif change_pct < market_avg - 1:
            sell_reasons.append(f"今日涨幅{change_pct:+.2f}%跑输大盘均值({market_avg:+.2f}%)，个股表现弱势")
            sell_score += 1

    # === 综合判断 ===
    total_score = buy_score - sell_score

    if total_score >= 4:
        recommendation = "buy"
        confidence = min(0.95, 0.5 + total_score * 0.06)
        suggested_ratio = min(0.3, 0.05 + total_score * 0.03)
        risk_level = "low" if total_score >= 6 else "medium"
        # 目标价：基于布林带上轨或近期高点
        recent_high = max(d["high"] for d in history[-20:])
        target_price = round(max(recent_high, tech["boll_upper"]), 2)
    elif total_score >= 0:
        recommendation = "hold"
        confidence = 0.4 + total_score * 0.05
        suggested_ratio = max(0.0, 0.05 + total_score * 0.01)
        risk_level = "medium"
        target_price = None
    elif total_score >= -3:
        recommendation = "hold"
        confidence = 0.3 - total_score * 0.03
        suggested_ratio = 0.03
        risk_level = "medium"
        target_price = None
    else:
        recommendation = "sell"
        confidence = min(0.95, 0.5 - total_score * 0.06)
        suggested_ratio = 0.0
        risk_level = "high" if total_score <= -6 else "medium"
        # 下跌目标：基于布林带下轨或近期低点
        recent_low = min(d["low"] for d in history[-20:])
        target_price = round(min(recent_low, tech["boll_lower"]), 2)

    # 构建综合理由
    rec_label = {"buy": "买入", "sell": "卖出", "hold": "持有"}
    risk_label = {"low": "低风险", "medium": "中风险", "high": "高风险"}
    indicator_detail = (
        f"【技术指标】MA5:{tech['ma5']:.2f} MA10:{tech['ma10']:.2f} MA20:{tech['ma20']:.2f} | "
        f"MACD:{tech['macd']:.4f} RSI:{tech['rsi']:.1f} | "
        f"KDJ(K:{tech['k']:.1f} D:{tech['d']:.1f} J:{tech['j']:.1f}) | "
        f"布林带(上:{tech['boll_upper']:.2f} 中:{tech['boll_mid']:.2f} 下:{tech['boll_lower']:.2f})"
    )

    reasons_text = "；".join(buy_reasons[:3]) if recommendation == "buy" else "；".join(sell_reasons[:3])
    reasoning = (
        f"{indicator_detail}\n\n"
        f"【综合评分】买入信号{buy_score}分 vs 卖出信号{sell_score}分，净得分{total_score}分\n"
        f"【操作建议】{rec_label[recommendation]}（置信度{confidence*100:.0f}%，风险等级：{risk_label[risk_level]}）\n"
        f"【主要依据】{reasons_text}"
    )

    return {
        "recommendation": recommendation,
        "confidence": round(confidence, 2),
        "reasoning": reasoning,
        "suggested_ratio": round(suggested_ratio, 2),
        "buy_reasons": buy_reasons[:5] if buy_reasons else ["暂无明确买入信号"],
        "sell_reasons": sell_reasons[:5] if sell_reasons else ["暂无明确卖出信号"],
        "risk_level": risk_level,
        "target_price": target_price,
        "indicators": tech,
        "ai_available": False,
        "score_detail": {"buy_score": buy_score, "sell_score": sell_score, "net_score": total_score},
    }


def is_ai_available() -> bool:
    return bool(API_KEY)