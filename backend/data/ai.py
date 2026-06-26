"""
AI 智能分析模块 - 硅基流动千问2.5-7B + 多维度技术分析
"""
import os
import json
import math
import urllib.request
import urllib.error
from typing import Optional

# 硅基流动 API 配置
SILICONFLOW_API_KEY = ""
SILICONFLOW_API_BASE = "https://api.siliconflow.cn/v1/chat/completions"
SILICONFLOW_MODEL = "Qwen/Qwen2.5-7B-Instruct"

# DeepSeek 备用
DEEPSEEK_API_KEY = ""
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def _load_api_keys():
    """加载 API Keys（优先从模块配置，其次环境变量）"""
    global SILICONFLOW_API_KEY, DEEPSEEK_API_KEY
    if not SILICONFLOW_API_KEY:
        try:
            from modules.sim_executor import get_module_config
            cfg = get_module_config()
            SILICONFLOW_API_KEY = cfg.get("siliconflow_api_key", "") or os.environ.get("SILICONFLOW_API_KEY", "")
        except Exception:
            SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
    if not DEEPSEEK_API_KEY:
        try:
            from modules.sim_executor import get_module_config
            cfg = get_module_config()
            DEEPSEEK_API_KEY = cfg.get("deepseek_api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        except Exception:
            DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


def _call_ai_api(prompt: str, use_fallback: bool = False) -> Optional[str]:
    """调用 AI API（主：硅基千问，备：DeepSeek）"""
    _load_api_keys()
    
    if use_fallback:
        api_key = DEEPSEEK_API_KEY
        api_base = DEEPSEEK_API_BASE
        model = DEEPSEEK_MODEL
    else:
        api_key = SILICONFLOW_API_KEY
        api_base = SILICONFLOW_API_BASE
        model = SILICONFLOW_MODEL
    
    if not api_key:
        return None
    
    try:
        data = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个专业的股票分析师，请用中文回答，给出简洁专业的分析。只返回JSON格式。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        }).encode("utf-8")
        
        req = urllib.request.Request(
            api_base,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content
    except Exception as e:
        print(f"AI API调用失败({model}): {e}")
        return None


def _safe_json_parse(json_str: str) -> Optional[dict]:
    """安全解析JSON，自动修复常见格式错误和字段名映射"""
    # 尝试直接解析
    try:
        result = json.loads(json_str)
        return _normalize_ai_result(result)
    except json.JSONDecodeError:
        pass
    
    # 修复常见问题
    try:
        import re
        # 修复: 中文引号替换
        fixed = json_str.replace('\u201c', '"').replace('\u201d', '"')
        fixed = fixed.replace('\u2018', "'").replace('\u2019', "'")
        # 修复: 缺少逗号
        fixed = re.sub(r'"\s*\n\s*"', '",\n  "', fixed)
        # 修复: 尾部多余逗号
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)
        # 修复: 数字前导零 (如 00 → 0)
        fixed = re.sub(r':\s*0+(?=[,\s\n}])', r': 0', fixed)
        result = json.loads(fixed)
        return _normalize_ai_result(result)
    except (json.JSONDecodeError, Exception):
        pass
    
    # 最后尝试: 逐字段提取（支持多种字段名）
    try:
        import re
        result = {}
        
        # 字段名映射（AI可能返回的变体 → 标准名）
        field_aliases = {
            "recommendation": ["recommendation", "recommend", "suggestion", "action", "advice", "操作建议"],
            "confidence": ["confidence", "score", "conf", "置信度"],
            "reasoning": ["reasoning", "reason", "analysis", "detail", "分析", "理由"],
            "suggested_ratio": ["suggested_ratio", "ratio", "position", "仓位", "建议仓位"],
            "risk_level": ["risk_level", "risk", "riskLevel", "风险等级", "风险"],
            "target_price": ["target_price", "target", "targetPrice", "目标价", "目标价格"],
            "buy_ratio": ["buy_ratio", "buyRatio", "add_ratio", "加仓率", "建议加仓", "加仓比例"],
            "sell_ratio": ["sell_ratio", "sellRatio", "减仓率", "卖出率", "建议卖出", "卖出比例"],
            "stop_loss_price": ["stop_loss_price", "stop_loss", "stopLoss", "止损价", "止损价格"],
            "stop_profit_price": ["stop_profit_price", "stop_profit", "take_profit", "止盈价", "止盈价格"],
            "key_support": ["key_support", "support", "支撑位", "关键支撑"],
            "key_resistance": ["key_resistance", "resistance", "阻力位", "关键阻力", "压力位"],
        }
        
        for std_name, aliases in field_aliases.items():
            for alias in aliases:
                # 匹配 "alias": value
                pattern = rf'"{alias}"\s*:\s*'
                match = re.search(pattern + r'([^,}\]]+)', json_str)
                if match:
                    val = match.group(1).strip().strip('"').strip("'")
                    if std_name == "confidence":
                        try:
                            result[std_name] = min(1.0, max(0.0, float(val)))
                        except ValueError:
                            result[std_name] = 0.5
                    elif std_name == "suggested_ratio":
                        try:
                            result[std_name] = min(1.0, max(0.0, float(val)))
                        except ValueError:
                            result[std_name] = 0.1
                    elif std_name == "target_price":
                        try:
                            result[std_name] = float(val)
                        except ValueError:
                            result[std_name] = None
                    elif std_name == "risk_level":
                        val_lower = val.lower()
                        if "high" in val_lower or "高" in val_lower:
                            result[std_name] = "high"
                        elif "low" in val_lower or "低" in val_lower:
                            result[std_name] = "low"
                        else:
                            result[std_name] = "medium"
                    elif std_name in ("buy_ratio", "sell_ratio"):
                        try:
                            fval = float(val)
                            if fval > 1:
                                result[std_name] = min(100.0, max(0.0, fval))
                            else:
                                result[std_name] = min(100.0, max(0.0, fval * 100))
                        except ValueError:
                            result[std_name] = 0.0
                    elif std_name in ("stop_loss_price", "stop_profit_price", "key_support", "key_resistance"):
                        try:
                            result[std_name] = float(val)
                        except ValueError:
                            result[std_name] = None
                    else:
                        result[std_name] = val
                    break
        
        # 提取数组字段
        arr_aliases = {
            "buy_reasons": ["buy_reasons", "buyReasons", "买入理由", "买入"],
            "sell_reasons": ["sell_reasons", "sellReasons", "卖出理由", "卖出", "风险提示"],
            "warnings": ["warnings", "warning", "注意事项", "风险警告", "警示", "提醒"],
        }
        for std_name, aliases in arr_aliases.items():
            for alias in aliases:
                arr_match = re.search(rf'"{alias}"\s*:\s*\[(.*?)\]', json_str, re.DOTALL)
                if arr_match:
                    items = re.findall(r'"([^"]*)"', arr_match.group(1))
                    result[std_name] = items
                    break
            if std_name not in result:
                result[std_name] = []
        
        if "recommendation" in result:
            # 规范化 recommendation 值
            rec = result["recommendation"].lower()
            if "buy" in rec or "买入" in rec:
                result["recommendation"] = "buy"
            elif "sell" in rec or "卖出" in rec:
                result["recommendation"] = "sell"
            else:
                result["recommendation"] = "hold"
            return result
    except Exception:
        pass
    
    return None


def _normalize_ai_result(result: dict) -> Optional[dict]:
    """规范化AI返回的字段名"""
    # 映射可能的字段名变体
    key_map = {
        "recommend": "recommendation", "suggestion": "recommendation",
        "action": "recommendation", "advice": "recommendation",
        "reason": "reasoning", "analysis": "reasoning",
        "ratio": "suggested_ratio", "position": "suggested_ratio",
        "risk": "risk_level", "riskLevel": "risk_level",
        "target": "target_price", "targetPrice": "target_price",
        "buyRatio": "buy_ratio", "add_ratio": "buy_ratio", "加仓率": "buy_ratio",
        "sellRatio": "sell_ratio", "减仓率": "sell_ratio", "卖出率": "sell_ratio",
        "stopLoss": "stop_loss_price", "stop_loss": "stop_loss_price", "止损价": "stop_loss_price",
        "stopProfit": "stop_profit_price", "take_profit": "stop_profit_price", "止盈价": "stop_profit_price",
        "support": "key_support", "支撑位": "key_support",
        "resistance": "key_resistance", "阻力位": "key_resistance", "压力位": "key_resistance",
    }
    
    normalized = {}
    for k, v in result.items():
        new_key = key_map.get(k, k)
        normalized[new_key] = v
    
    if "recommendation" not in normalized:
        return None
    
    # 规范化值
    rec = str(normalized.get("recommendation", "")).lower()
    if "buy" in rec or "买入" in rec:
        normalized["recommendation"] = "buy"
    elif "sell" in rec or "卖出" in rec:
        normalized["recommendation"] = "sell"
    else:
        normalized["recommendation"] = "hold"
    
    # 确保 confidence 是浮点数
    if "confidence" in normalized:
        try:
            normalized["confidence"] = float(normalized["confidence"])
        except (ValueError, TypeError):
            normalized["confidence"] = 0.5
    
    # 确保 target_price 是浮点数
    if "target_price" in normalized:
        try:
            normalized["target_price"] = float(normalized["target_price"])
        except (ValueError, TypeError):
            normalized["target_price"] = None
    
    return normalized


def analyze_stock(code: str, name: str, price: float, change_pct: float,
                  history: list[dict], market_indices: dict) -> dict:
    """
    使用 AI 分析股票，给出买入/卖出/持有建议
    """
    # 先获取技术指标摘要
    tech = _compute_indicators(history, price)

    # 构建最近走势摘要
    recent = history[-20:] if len(history) > 20 else history
    trend_summary = "\n".join([
        f"{d['date']}: 开{d['open']:.2f} 高{d['high']:.2f} 低{d['low']:.2f} 收{d['close']:.2f} 量{d['volume']:.0f}"
        for d in recent
    ])

    market_summary = "\n".join([
        f"{k}: {v['price']:.2f} (涨跌幅 {v['change_pct']:+.2f}%)" for k, v in market_indices.items()
    ]) if market_indices else "无市场指数数据"

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
- buy_ratio: 建议加仓百分比（0-100，如果建议买入或持有，给出建议加仓比例；如果建议卖出，设为0）
- sell_ratio: 建议卖出百分比（0-100，如果建议卖出或减仓，给出建议卖出比例；如果建议买入，设为0）
- buy_reasons: 列出3-5条买入理由（如果推荐买入）或风险提示（如果推荐卖出/持有）
- sell_reasons: 列出3-5条卖出理由或需要警惕的信号
- risk_level: 风险等级，可选 "low"（低风险）/ "medium"（中风险）/ "high"（高风险）
- target_price: 短期目标价格（如果是buy，给上涨目标；如果是sell，给下跌目标；hold给null）
- stop_loss_price: 止损价格
- stop_profit_price: 止盈价格
- warnings: 列出3-5条需要重点注意的风险提示或注意事项
- key_support: 关键支撑位价格
- key_resistance: 关键阻力位价格

只返回 JSON，不要包含其他内容。"""

    # 尝试主模型（硅基千问）
    response = _call_ai_api(prompt, use_fallback=False)
    if not response:
        # 尝试备用模型（DeepSeek）
        response = _call_ai_api(prompt, use_fallback=True)
    
    if response:
        try:
            content = response.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            import re
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                json_str = json_match.group()
                # 尝试修复常见JSON格式错误
                ai_result = _safe_json_parse(json_str)
                if ai_result:
                    # 获取技术分析结果作为基础
                    tech_result = _advanced_technical_analysis(
                        code, name, price, change_pct, history, market_indices
                    )
                    # 需要用技术分析兜底的字段（AI可能返回空或不正确的）
                    fallback_fields = [
                        "score_detail", "buy_reasons", "sell_reasons",
                        "warnings", "indicators"
                    ]
                    # 合并：AI返回的字段优先，缺失的或关键兜底字段用技术分析填充
                    for k, v in tech_result.items():
                        is_missing = k not in ai_result or ai_result[k] is None or ai_result[k] == ""
                        is_empty_list = isinstance(ai_result.get(k), list) and len(ai_result[k]) == 0
                        is_empty_dict = isinstance(ai_result.get(k), dict) and len(ai_result[k]) == 0
                        if k in ("indicators", "ai_available", "reasoning", "recommendation", "confidence", "target_price"):
                            continue
                        if is_missing or is_empty_list or is_empty_dict:
                            ai_result[k] = v
                    ai_result["indicators"] = tech
                    ai_result["ai_available"] = True
                    return ai_result
            else:
                print(f"AI 响应中未找到JSON: {response[:100]}")
        except Exception as e:
            print(f"AI 响应解析失败: {e}")
    
    # 降级到技术分析
    print(f"AI 分析不可用，回退技术分析: {code}")
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

    # 计算关键支撑位和阻力位
    recent_high_20 = max(d["high"] for d in history[-20:])
    recent_low_20 = min(d["low"] for d in history[-20:])
    key_support = round(min(tech["boll_lower"], recent_low_20 * 1.01, tech["ma20"] * 0.98), 2)
    key_resistance = round(max(tech["boll_upper"], recent_high_20 * 0.99, tech["ma20"] * 1.02), 2)

    # 构建注意事项
    warnings = []
    if tech["rsi"] > 70:
        warnings.append("RSI超买(>70)，短期回调风险较高，注意控制仓位")
    if tech["rsi"] < 30:
        warnings.append("RSI超卖(<30)，可能存在技术性反弹，但需确认底部信号")
    if tech["j"] > 100:
        warnings.append("KDJ超买(J>100)，短期获利盘抛压较大")
    if tech["j"] < 0:
        warnings.append("KDJ超卖(J<0)，关注是否企稳反弹")
    if price > tech["boll_upper"]:
        warnings.append("价格突破布林带上轨，超买状态，注意回调风险")
    if price < tech["boll_lower"]:
        warnings.append("价格跌破布林带下轨，超跌状态，关注企稳信号")
    if abs(change_pct) > 5:
        warnings.append(f"今日波动较大({change_pct:+.2f}%)，注意情绪面影响")
    if tech["vol_trend"] == "放量" and change_pct < 0:
        warnings.append("放量下跌，资金流出明显，需警惕进一步下行")
    if tech["vol_trend"] == "缩量" and change_pct > 0:
        warnings.append("缩量上涨，量价背离，上行动力可能不足")
    if len(warnings) < 3:
        warnings.append("建议设置止盈止损，严格执行交易纪律")
        warnings.append("关注大盘整体走势，系统性风险不可忽视")
        warnings.append("以上分析仅供参考，不构成投资建议")

    if total_score >= 4:
        recommendation = "buy"
        confidence = min(0.95, 0.5 + total_score * 0.06)
        suggested_ratio = min(0.3, 0.05 + total_score * 0.03)
        buy_ratio = min(80, 30 + total_score * 6)
        sell_ratio = 0
        risk_level = "low" if total_score >= 6 else "medium"
        # 目标价：基于布林带上轨+1倍标准差，或近期高点+5%
        recent_high = recent_high_20
        boll_target = tech["boll_upper"] * 1.02 if tech["boll_upper"] > price else tech["boll_upper"]
        target_price = round(max(recent_high * 1.03, boll_target, price * 1.05), 2)
        stop_loss_price = round(key_support * 0.98, 2)
        stop_profit_price = round(target_price * 0.97, 2)
    elif total_score >= 0:
        recommendation = "hold"
        confidence = 0.4 + total_score * 0.05
        suggested_ratio = max(0.0, 0.05 + total_score * 0.01)
        buy_ratio = min(40, 10 + total_score * 5)
        sell_ratio = max(0, 20 - total_score * 3)
        risk_level = "medium"
        # 持有也给出上行目标
        recent_high = recent_high_20
        target_price = round(max(recent_high, price * 1.03), 2) if recent_high > price else None
        stop_loss_price = round(key_support * 0.97, 2)
        stop_profit_price = round(key_resistance * 0.98, 2) if key_resistance > price else None
    elif total_score >= -3:
        recommendation = "hold"
        confidence = 0.3 - total_score * 0.03
        suggested_ratio = 0.03
        buy_ratio = 10
        sell_ratio = min(50, 30 - total_score * 5)
        risk_level = "medium"
        target_price = None
        stop_loss_price = round(key_support * 0.97, 2)
        stop_profit_price = None
    else:
        recommendation = "sell"
        confidence = min(0.95, 0.5 - total_score * 0.06)
        suggested_ratio = 0.0
        buy_ratio = 0
        sell_ratio = min(100, 60 - total_score * 5)
        risk_level = "high" if total_score <= -6 else "medium"
        # 下跌目标：基于布林带下轨或近期低点
        recent_low = recent_low_20
        target_price = round(min(recent_low * 0.97, tech["boll_lower"], price * 0.93), 2)
        stop_loss_price = round(key_resistance * 1.02, 2)
        stop_profit_price = round(target_price * 1.03, 2)

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
        "buy_ratio": round(buy_ratio, 0),
        "sell_ratio": round(sell_ratio, 0),
        "buy_reasons": buy_reasons[:5] if buy_reasons else ["暂无明确买入信号"],
        "sell_reasons": sell_reasons[:5] if sell_reasons else ["暂无明确卖出信号"],
        "risk_level": risk_level,
        "target_price": target_price,
        "stop_loss_price": stop_loss_price,
        "stop_profit_price": stop_profit_price,
        "warnings": warnings[:5],
        "key_support": key_support,
        "key_resistance": key_resistance,
        "indicators": tech,
        "ai_available": False,
        "score_detail": {"buy_score": buy_score, "sell_score": sell_score, "net_score": total_score},
    }


def chat_with_ai(system_prompt: str, user_message: str, history: list = None) -> str:
    """
    通用 AI 聊天接口

    参数:
        system_prompt: 系统提示词
        user_message: 用户消息
        history: 历史消息列表，每个元素是 {"role": "user"/"assistant", "content": "..."}

    返回:
        AI 回复的字符串，失败返回 None
    """
    _load_api_keys()

    if not history:
        history = []

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    def _call(api_key, api_base, model):
        if not api_key:
            return None
        try:
            data = json.dumps({
                "model": model,
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.7,
            }).encode("utf-8")
            req = urllib.request.Request(
                api_base,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content
        except Exception as e:
            print(f"AI 聊天调用失败 ({model}): {e}")
            return None

    response = _call(SILICONFLOW_API_KEY, SILICONFLOW_API_BASE, SILICONFLOW_MODEL)
    if not response:
        response = _call(DEEPSEEK_API_KEY, DEEPSEEK_API_BASE, DEEPSEEK_MODEL)

    return response


def is_ai_available() -> bool:
    _load_api_keys()
    return bool(SILICONFLOW_API_KEY) or bool(DEEPSEEK_API_KEY)