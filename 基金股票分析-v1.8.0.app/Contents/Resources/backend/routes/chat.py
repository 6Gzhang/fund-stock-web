"""
AI 聊天接口 - 智能对话 + 股票/基金上下文分析
"""
import re
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from data.ai import chat_with_ai, is_ai_available
from data.market import get_stock_quote, get_fund_quote, get_stock_history, get_fund_history, search_stock, get_market_index
from data.sector import get_sector_for_stock, get_sector_for_etf

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 对话历史存储（内存），最多保留 20 轮
_chat_history: list = []
_MAX_HISTORY = 20


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
    context: dict = {}


class ChatResponse(BaseModel):
    """聊天响应模型"""
    reply: str
    ai_available: bool
    timestamp: int


def _extract_codes(message: str) -> dict:
    """
    从消息中提取股票/基金代码

    返回:
        {
            "stock_codes": [A股代码、港股代码],
            "fund_codes": [基金代码],
            "is_etf": bool  # 是否识别到ETF
        }
    """
    stock_codes = []
    fund_codes = []
    is_etf = False

    # 港股代码（hk开头 + 5位数字）
    hk_pattern = re.findall(r'hk\d{5}', message.lower())
    stock_codes.extend(hk_pattern)

    # 6位数字股票代码（A股）
    a_stock_pattern = re.findall(r'\b\d{6}\b', message)
    for code in a_stock_pattern:
        # 简单判断：6开头是沪市主板/科创板，0/3开头是深市
        if code[0] in ('6', '0', '3'):
            if code not in stock_codes:
                stock_codes.append(code)
        else:
            # 其他开头可能是基金，加入基金列表
            if code not in fund_codes:
                fund_codes.append(code)

    # 4位数字（可能是港股不带hk前缀）
    hk_short_pattern = re.findall(r'(?<!\d)\d{4,5}(?!\d)', message)
    for code in hk_short_pattern:
        if len(code) <= 5 and code not in stock_codes:
            hk_code = "hk" + code.zfill(5)
            if hk_code not in stock_codes:
                stock_codes.append(hk_code)

    # 关键词搜索（如果没有直接识别到代码，尝试通过名称搜索）
    if not stock_codes and not fund_codes:
        # 去掉常见的无意义词，提取可能的股票名称
        clean_msg = re.sub(r'[，。！？、；：""''（）\s,.!?;:\'\"()]+', ' ', message).strip()
        words = clean_msg.split()
        for word in words:
            if len(word) >= 2 and len(word) <= 8:
                results = search_stock(word)
                if results:
                    top = results[0]
                    code = top["code"]
                    if code not in stock_codes:
                        stock_codes.append(code)
                    if top.get("type") == "etf":
                        is_etf = True
                    break

    return {
        "stock_codes": stock_codes[:3],  # 最多取3只
        "fund_codes": fund_codes[:3],
        "is_etf": is_etf,
    }


def _analyze_trend(history: list) -> dict:
    """
    分析K线数据趋势

    返回:
        {
            "high": 最高价,
            "low": 最低价,
            "avg": 平均价,
            "trend": "上涨"/"下跌"/"震荡",
            "change_pct": 区间涨跌幅
        }
    """
    if not history or len(history) < 5:
        return {
            "high": 0, "low": 0, "avg": 0,
            "trend": "数据不足",
            "change_pct": 0
        }

    closes = [d["close"] for d in history]
    highs = [d["high"] for d in history]
    lows = [d["low"] for d in history]

    high_price = max(highs)
    low_price = min(lows)
    avg_price = sum(closes) / len(closes)

    # 区间涨跌幅
    first_close = closes[0]
    last_close = closes[-1]
    change_pct = (last_close - first_close) / first_close * 100 if first_close > 0 else 0

    # 趋势判断
    if change_pct > 5:
        trend = "上涨趋势"
    elif change_pct < -5:
        trend = "下跌趋势"
    else:
        # 判断震荡：计算波动率
        returns = []
        for i in range(1, len(closes)):
            if closes[i-1] > 0:
                returns.append(abs((closes[i] - closes[i-1]) / closes[i-1]))
        volatility = sum(returns) / len(returns) * 100 if returns else 0
        if volatility > 2:
            trend = "宽幅震荡"
        else:
            trend = "窄幅震荡"

    return {
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "avg": round(avg_price, 2),
        "trend": trend,
        "change_pct": round(change_pct, 2),
    }


def build_context_prompt(message: str) -> str:
    """
    构建上下文提示词

    从消息中提取股票/基金代码，自动获取行情、K线、行业分类等数据，
    结合大盘指数，构建详细的上下文prompt。

    参数:
        message: 用户消息

    返回:
        上下文提示字符串
    """
    context_parts = []

    # 1. 获取大盘指数
    try:
        market_indices = get_market_index()
        if market_indices:
            context_parts.append("【当前大盘环境】")
            for name, data in market_indices.items():
                context_parts.append(
                    f"  {name}: {data['price']:.2f} 点 (涨跌幅 {data['change_pct']:+.2f}%)"
                )
            context_parts.append("")
    except Exception as e:
        print(f"获取大盘指数失败: {e}")

    # 2. 提取股票/基金代码
    codes_info = _extract_codes(message)
    stock_codes = codes_info["stock_codes"]
    fund_codes = codes_info["fund_codes"]

    # 3. 获取股票行情和K线
    if stock_codes:
        context_parts.append("【相关股票信息】")
        for code in stock_codes:
            try:
                quote = get_stock_quote(code)
                if quote:
                    name = quote.get("name", code)
                    price = quote.get("price", 0)
                    change = quote.get("change", 0)
                    change_pct = quote.get("change_pct", 0)
                    volume = quote.get("volume", 0)
                    amount = quote.get("amount", 0)

                    context_parts.append(f"  股票: {name} ({code})")
                    context_parts.append(
                        f"    现价: {price:.2f}  涨跌: {change:+.2f} ({change_pct:+.2f}%)"
                    )
                    context_parts.append(
                        f"    成交量: {volume/10000:.0f}万  成交额: {amount/100000000:.2f}亿"
                    )

                    # 获取K线数据（最近30天）
                    try:
                        history = get_stock_history(code, days=30)
                        if history:
                            trend_info = _analyze_trend(history)
                            context_parts.append(
                                f"    近30日走势: 最高{trend_info['high']:.2f} / "
                                f"最低{trend_info['low']:.2f} / "
                                f"均价{trend_info['avg']:.2f}"
                            )
                            context_parts.append(
                                f"    区间涨跌幅: {trend_info['change_pct']:+.2f}%  "
                                f"趋势判断: {trend_info['trend']}"
                            )
                    except Exception as e:
                        print(f"获取股票K线失败 {code}: {e}")

                    # 获取行业分类
                    try:
                        sectors = get_sector_for_stock(code, name)
                        if sectors:
                            context_parts.append(f"    所属行业: {'、'.join(sectors)}")
                    except Exception as e:
                        print(f"获取行业分类失败 {code}: {e}")

                    # 风险提示
                    if change_pct > 7 or change_pct < -7:
                        context_parts.append("    ⚠️ 注意：今日波动较大，请注意风险！")
                    if price < 2 and change_pct < -5:
                        context_parts.append("    ⚠️ 风险提示：低价股，注意退市风险！")

                    context_parts.append("")
            except Exception as e:
                print(f"获取股票行情失败 {code}: {e}")

    # 4. 获取基金/ETF行情
    if fund_codes or codes_info["is_etf"]:
        all_fund_codes = fund_codes.copy()
        if codes_info["is_etf"] and not all_fund_codes:
            # 如果识别到ETF但没有代码，从股票代码中补充
            all_fund_codes.extend([c for c in stock_codes if len(c) == 6])

        if all_fund_codes:
            context_parts.append("【相关基金/ETF信息】")
            for code in all_fund_codes:
                try:
                    quote = get_fund_quote(code)
                    if quote:
                        name = quote.get("name", code)
                        price = quote.get("price", 0)
                        change = quote.get("change", 0)
                        change_pct = quote.get("change_pct", 0)
                        fund_type = quote.get("type", "fund")

                        context_parts.append(f"  基金: {name} ({code})")
                        context_parts.append(
                            f"    净值/价格: {price:.4f}  涨跌: {change:+.4f} ({change_pct:+.2f}%)"
                        )
                        context_parts.append(f"    类型: {fund_type}")

                        # 获取历史走势
                        try:
                            history = get_fund_history(code, days=30)
                            if history:
                                trend_info = _analyze_trend(history)
                                context_parts.append(
                                    f"    近30日走势: 最高{trend_info['high']:.4f} / "
                                    f"最低{trend_info['low']:.4f} / "
                                    f"均价{trend_info['avg']:.4f}"
                                )
                                context_parts.append(
                                    f"    区间涨跌幅: {trend_info['change_pct']:+.2f}%  "
                                    f"趋势判断: {trend_info['trend']}"
                                )
                        except Exception as e:
                            print(f"获取基金历史失败 {code}: {e}")

                        # ETF行业分类
                        if fund_type == "etf":
                            try:
                                sectors = get_sector_for_etf(code, name)
                                if sectors:
                                    context_parts.append(f"    跟踪行业: {'、'.join(sectors)}")
                            except Exception as e:
                                print(f"获取ETF行业失败 {code}: {e}")

                        context_parts.append("")
                except Exception as e:
                    print(f"获取基金行情失败 {code}: {e}")

    if not context_parts:
        return ""

    return "\n".join(context_parts)


def _get_system_prompt() -> str:
    """生成系统提示词"""
    return (
        "你是一位专业的金融投资顾问，精通股票、基金、ETF等投资品种的分析。"
        "请用中文回答用户的问题，回答要专业、客观、有深度。\n\n"
        "回答原则：\n"
        "1. 基于提供的市场数据进行分析，不要编造数据\n"
        "2. 给出分析结论时要说明理由和依据\n"
        "3. 涉及投资建议时，要提示风险，说明仅供参考\n"
        "4. 对于个股分析，要结合大盘环境、行业板块、技术面等多维度\n"
        "5. 语言简洁明了，重点突出\n\n"
        "注意：你的回答不构成任何投资建议，投资有风险，入市需谨慎。"
    )


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    发送消息给AI，返回回复

    自动识别消息中的股票/基金代码，获取实时行情和历史数据作为上下文。
    """
    ai_available = is_ai_available()

    if not ai_available:
        return ChatResponse(
            reply=(
                "抱歉，AI 服务暂不可用。\n\n"
                "可能原因：\n"
                "1. 未配置 API Key\n"
                "2. 网络连接问题\n\n"
                "请在系统设置中配置硅基流动或 DeepSeek 的 API Key 后再试。"
            ),
            ai_available=False,
            timestamp=int(time.time())
        )

    try:
        # 构建上下文
        context_prompt = build_context_prompt(request.message)

        # 构建带上下文的用户消息
        user_message = request.message
        if context_prompt:
            user_message = f"以下是当前市场上下文数据，供你参考分析：\n\n{context_prompt}\n\n用户问题：{request.message}"

        # 构建系统提示词（加上用户自定义上下文）
        system_prompt = _get_system_prompt()
        if request.context and isinstance(request.context, dict):
            extra_ctx = request.context.get("extra", "")
            if extra_ctx:
                system_prompt += f"\n\n补充信息：{extra_ctx}"

        # 调用AI
        reply = chat_with_ai(
            system_prompt=system_prompt,
            user_message=user_message,
            history=_chat_history
        )

        if not reply:
            return ChatResponse(
                reply="抱歉，AI 服务暂时无响应，请稍后再试。",
                ai_available=False,
                timestamp=int(time.time())
            )

        # 保存对话历史
        _chat_history.append({"role": "user", "content": request.message})
        _chat_history.append({"role": "assistant", "content": reply})

        # 限制历史记录数量（保留最近20轮，即40条消息）
        if len(_chat_history) > _MAX_HISTORY * 2:
            _chat_history[:] = _chat_history[-_MAX_HISTORY * 2:]

        return ChatResponse(
            reply=reply,
            ai_available=True,
            timestamp=int(time.time())
        )

    except Exception as e:
        print(f"聊天接口异常: {e}")
        raise HTTPException(status_code=500, detail=f"服务内部错误: {str(e)}")


@router.get("/status")
async def check_status():
    """
    检查AI服务状态
    """
    available = is_ai_available()
    return {
        "ai_available": available,
        "history_count": len(_chat_history) // 2,
        "max_history": _MAX_HISTORY,
    }


@router.post("/clear")
async def clear_history():
    """
    清除对话历史
    """
    _chat_history.clear()
    return {
        "success": True,
        "message": "对话历史已清除",
    }
