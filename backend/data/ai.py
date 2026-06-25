"""
AI 智能分析模块 - 基于 OpenAI 兼容 API
"""
import os
import json
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
        return _fallback_analysis(code, name, price, change_pct, history)

    # 构建最近走势摘要
    recent = history[-20:] if len(history) > 20 else history
    trend_summary = "\n".join([
        f"{d['date']}: 开{d['open']:.2f} 高{d['high']:.2f} 低{d['low']:.2f} 收{d['close']:.2f}"
        for d in recent
    ])

    market_summary = "\n".join([
        f"{k}: {v['price']:.2f} (涨跌幅 {v['change_pct']:+.2f}%)" for k, v in market_indices.items()
    ]) if market_indices else "无市场指数数据"

    prompt = f"""你是一个专业的股票分析师。请分析以下股票并给出建议。

股票代码: {code}
股票名称: {name}
当前价格: {price:.2f}
今日涨跌幅: {change_pct:+.2f}%

大盘指数:
{market_summary}

最近20个交易日走势:
{trend_summary}

请以 JSON 格式回答，包含以下字段：
- recommendation: "buy"（买入）/ "sell"（卖出）/ "hold"（持有）
- confidence: 0-1之间的置信度
- reasoning: 简短的分析理由（100字以内）
- suggested_ratio: 建议仓位占比（0-1之间，表示在总资产中应占的比例）

只返回 JSON，不要包含其他内容。"""

    try:
        response = c.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        content = response.choices[0].message.content.strip()
        # 清理可能的 markdown 代码块标记
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        print(f"AI 分析失败: {e}")
        return _fallback_analysis(code, name, price, change_pct, history)


def _fallback_analysis(code: str, name: str, price: float, change_pct: float,
                       history: list[dict]) -> dict:
    """当 AI 不可用时的简易技术分析"""
    if not history or len(history) < 5:
        return {
            "recommendation": "hold",
            "confidence": 0.1,
            "reasoning": "数据不足，建议观望",
            "suggested_ratio": 0.0,
        }

    closes = [d["close"] for d in history]
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else ma5
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else ma5

    # 简单均线策略
    if price > ma5 > ma10:
        recommendation = "buy"
        confidence = 0.6
        reasoning = f"价格({price:.2f})站上5日均线({ma5:.2f})和10日均线({ma10:.2f})，短期趋势向好"
        suggested_ratio = 0.15
    elif price < ma5 < ma10:
        recommendation = "sell"
        confidence = 0.6
        reasoning = f"价格({price:.2f})跌破5日均线({ma5:.2f})和10日均线({ma10:.2f})，短期趋势走弱"
        suggested_ratio = 0.0
    else:
        recommendation = "hold"
        confidence = 0.4
        reasoning = f"价格({price:.2f})在5日线({ma5:.2f})和10日线({ma10:.2f})之间震荡，方向不明"
        suggested_ratio = 0.05

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "reasoning": reasoning,
        "suggested_ratio": suggested_ratio,
    }


def is_ai_available() -> bool:
    return bool(API_KEY)