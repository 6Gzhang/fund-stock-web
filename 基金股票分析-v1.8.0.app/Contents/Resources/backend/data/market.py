"""
市场数据获取模块 - 多数据源冗余（新浪主 + 腾讯备 + AKShare兜底）
"""
import akshare as ak
import pandas as pd
import time
import threading
import requests
import concurrent.futures
import re
from typing import Optional

_cache: dict = {}
_cache_lock = threading.Lock()
_fetch_events: dict = {}
_CACHE_TTL = 120
_FETCH_TIMEOUT = 60


def _session():
    s = requests.Session()
    s.trust_env = False
    return s


def _cached(key: str, fetcher, ttl: int = _CACHE_TTL, wait: bool = True):
    """通用缓存装饰器（线程安全，避免重复拉取，超时快速失败）"""
    now = time.time()
    with _cache_lock:
        if key in _cache:
            data, ts = _cache[key]
            if now - ts < ttl:
                return data
    with _cache_lock:
        if key in _fetch_events:
            if not wait:
                return None if "hk" in key else pd.DataFrame()
            event = _fetch_events[key]
            is_my_event = False
        else:
            if not wait:
                return None if "hk" in key else pd.DataFrame()
            event = threading.Event()
            _fetch_events[key] = event
            is_my_event = True
    if not is_my_event:
        event.wait(timeout=_FETCH_TIMEOUT)
        with _cache_lock:
            if key in _cache:
                return _cache[key][0]
        return None if "hk" in key else pd.DataFrame()
    else:
        try:
            data = fetcher()
            with _cache_lock:
                _cache[key] = (data, time.time())
            return data
        except Exception as e:
            print(f"缓存拉取失败 {key}: {e}")
            return None if "hk" in key else pd.DataFrame()
        finally:
            event.set()
            with _cache_lock:
                _fetch_events.pop(key, None)


def _clean_stock_name(name: str) -> str:
    """去除股票名称中的XD/XR/DR/ST等前缀和-W/-SW等后缀"""
    if not name:
        return name
    cleaned = re.sub(r'^(XD|XR|DR|N|\*ST|ST|S)', '', str(name))
    cleaned = re.sub(r'(-W|-SW|-WR|-R|-WD|-S)$', '', cleaned)
    return cleaned.strip()


def _clean_code(code: str) -> str:
    """去掉 sh/sz/bj 前缀"""
    if not code:
        return code
    code = str(code).strip().lower()
    for prefix in ("sh", "sz", "bj"):
        if code.startswith(prefix):
            return code[len(prefix):]
    return code


def _fix_stock_name(code: str, original_name: str) -> str:
    """修正股票名称（解决除权除息导致的名称截断/前缀问题）"""
    code = str(code).strip().lower()
    if code.startswith("hk"):
        code = code[2:]
    code = code.zfill(5) if len(code) <= 5 else code.zfill(6)

    best_name = None
    best_score = -1

    for alias, target_code in _STOCK_ALIASES.items():
        tc = target_code.replace("hk", "").zfill(5) if target_code.startswith("hk") else target_code.zfill(6)
        if tc == code:
            has_suffix = bool(re.search(r'(-W|-SW|-WR|-R|-WD|-S)$', alias))
            has_prefix = alias.startswith("港股")
            score = len(alias)
            if has_suffix:
                score *= 0.5
            if has_prefix:
                score *= 0.3
            if score > best_score:
                best_score = score
                best_name = alias

    cleaned = _clean_stock_name(original_name)

    if best_name:
        return best_name

    return cleaned if cleaned else original_name


# 知名股票别名映射（用于搜索增强，解决名称截断问题）
_STOCK_ALIASES = {
    # A股知名股票
    "茅台": "600519", "贵州茅台": "600519",
    "五粮液": "000858",
    "宁德时代": "300750",
    "比亚迪": "002594",
    "腾讯": "hk00700", "腾讯控股": "hk00700",
    "阿里": "hk09988", "阿里巴巴": "hk09988",
    "小米": "hk01810", "小米集团": "hk01810", "小米集团-W": "hk01810",
    "美团": "hk03690", "美团-W": "hk03690",
    "京东": "hk09618",
    "百度": "hk09888",
    "网易": "hk09999",
    "快手": "hk01024",
    "哔哩哔哩": "hk09626", "B站": "hk09626",
    "中国平安": "601318",
    "招商银行": "600036",
    "工商银行": "601398",
    "建设银行": "601939",
    "农业银行": "601288",
    "中国银行": "601988",
    "中国石油": "601857",
    "中国石化": "600028",
    "格力电器": "000651",
    "美的集团": "000333",
    "海尔智家": "600690",
    "伊利股份": "600887",
    "恒瑞医药": "600276",
    "药明康德": "603259",
    "海康威视": "002415",
    "中兴通讯": "000063",
    "科大讯飞": "002230",
    "中芯国际": "688981",
    "北方华创": "002371",
    "韦尔股份": "603501",
    "兆易创新": "603986",
    "立讯精密": "002475",
    "歌尔股份": "002241",
    "蓝思科技": "300433",
    "赣锋锂业": "002460",
    "天齐锂业": "002466",
    "华友钴业": "603799",
    "隆基绿能": "601012",
    "通威股份": "600438",
    "阳光电源": "300274",
    "晶澳科技": "002459",
    "天合光能": "688599",
    "东方财富": "300059",
    "中信证券": "600030",
    "华泰证券": "601688",
    "国泰君安": "601211",
    "海通证券": "600837",
    "中国中免": "601888",
    "长春高新": "000661",
    "片仔癀": "600436",
    "云南白药": "000538",
    "同仁堂": "600085",
    "长江电力": "600900",
    "中国神华": "601088",
    "陕西煤业": "601225",
    "紫金矿业": "601899",
    "山东黄金": "600547",
    "中金黄金": "600489",
    "三一重工": "600031",
    "徐工机械": "000425",
    "恒力石化": "600346",
    "万华化学": "600309",
    "海螺水泥": "600585",
    "中国建筑": "601668",
    "万科A": "000002", "万科": "000002",
    "保利发展": "600048",
    "招商蛇口": "001979",
    "上汽集团": "600104",
    "长城汽车": "601633",
    "长安汽车": "000625",
    "潍柴动力": "000338",
    "京东方A": "000725", "京东方": "000725",
    "TCL科技": "000100",
    "三安光电": "600703",
    "闻泰科技": "600745",
    "用友网络": "600588",
    "金山办公": "688111",
    "广联达": "002410",
    "恒生电子": "600570",
    "同花顺": "300033",
    "东方雨虹": "002271",
    "海螺新材": "000619",
    "北新建材": "000786",
    "中国中铁": "601390",
    "中国铁建": "601186",
    "中国交建": "601800",
    "中国电建": "601669",
    "中国能建": "601868",
    "中国移动": "600941",
    "中国联通": "600050",
    "中国电信": "601728",
    "平安银行": "000001",
    "港股腾讯": "hk00700",
    "港股阿里": "hk09988",
    "港股小米": "hk01810",
    "港股美团": "hk03690",
}


def _search_alias(keyword: str) -> list[dict]:
    """通过别名映射搜索（解决名称截断问题），不等待缓存"""
    results = []
    kw = keyword.strip().lower()
    if not kw:
        return results

    hk_list = _cached("hk_spot", _fetch_hk_spot, ttl=180, wait=False)
    stock_df = _cached("stock_spot", _fetch_stock_spot, wait=False)
    etf_df = _cached("etf_spot", _fetch_etf_spot, wait=False)

    for alias, code in _STOCK_ALIASES.items():
        if kw not in alias.lower():
            continue
        if code.startswith("hk"):
            if not hk_list:
                continue
            hk_code = code[2:].zfill(5)
            for item in hk_list:
                if str(item.get("code", "")).zfill(5) == hk_code:
                    results.append({
                        "code": "hk" + hk_code,
                        "name": str(item.get("name", "")),
                        "price": float(item.get("price", 0)),
                        "change": float(item.get("change", 0)),
                        "change_pct": float(item.get("change_pct", 0)),
                        "type": "stock_hk",
                    })
                    break
        else:
            found = False
            if stock_df is not None and not stock_df.empty:
                matched = stock_df[stock_df["代码"] == code]
                if not matched.empty:
                    row = matched.iloc[0]
                    results.append({
                        "code": code,
                        "name": str(row["名称"]),
                        "price": float(row["最新价"]),
                        "change": float(row["涨跌额"]),
                        "change_pct": float(row["涨跌幅"]),
                        "type": "stock",
                    })
                    found = True
            if not found and etf_df is not None and not etf_df.empty:
                matched = etf_df[etf_df["代码"] == code]
                if not matched.empty:
                    row = matched.iloc[0]
                    results.append({
                        "code": code,
                        "name": str(row["名称"]),
                        "price": float(row["最新价"]),
                        "change": float(row["涨跌额"]),
                        "change_pct": float(row["涨跌幅"]),
                        "type": "etf",
                    })
    return results


# ========== 新浪行情列表（A股/ETF主数据源） ==========

def _fetch_sina_list(node: str, max_pages: int = 80) -> list[dict]:
    """新浪行情列表通用拉取"""
    session = _session()
    headers = {"Referer": "https://finance.sina.com.cn"}
    url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    all_data = []

    def _fetch_page(pn):
        params = {
            'page': pn, 'num': 80, 'sort': 'symbol', 'asc': 1,
            'node': node, 'symbol': '', '_s_r_a': 'init'
        }
        try:
            r = session.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if first.get('code') == 's_auth' or first.get('name') == 'FAILED':
                    return []
                return data
        except Exception:
            pass
        return []

    try:
        first_page = _fetch_page(1)
        if not first_page:
            return []
        all_data.extend(first_page)

        total = max_pages * 80
        pages = min(max_pages, 80)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_fetch_page, p): p for p in range(2, pages + 1)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    data = future.result()
                    if data:
                        all_data.extend(data)
                    else:
                        break
                except Exception:
                    pass
    except Exception as e:
        print(f"新浪列表拉取失败 ({node}): {e}")

    return all_data


# ========== 东方财富通用拉取（备用数据源） ==========

def _fetch_em_list(fs: str, fields: str = None) -> list[dict]:
    """东方财富行情列表通用拉取（并发分页）"""
    if fields is None:
        fields = "f2,f3,f4,f5,f6,f7,f12,f14,f15,f16,f17,f18"
    session = _session()
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    all_data = []

    def _fetch_page(pn):
        params = {
            "pn": pn, "pz": 100, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2, "fid": "f12",
            "fs": fs, "fields": fields,
            "_": int(time.time() * 1000),
        }
        try:
            r = session.get(url, params=params, timeout=10)
            data = r.json()
            if data.get("data") and data["data"].get("diff"):
                return data["data"]["diff"]
        except Exception:
            pass
        return []

    try:
        first_page = _fetch_page(1)
        if not first_page:
            return []
        all_data.extend(first_page)

        total = 3000
        try:
            params_count = {
                "pn": 1, "pz": 1, "po": 1, "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2, "invt": 2, "fid": "f12",
                "fs": fs, "fields": fields,
                "_": int(time.time() * 1000),
            }
            r = session.get(url, params=params_count, timeout=8)
            d = r.json()
            total = d.get("data", {}).get("total", 3000)
        except Exception:
            pass

        pages = min(60, (total + 99) // 100)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_fetch_page, p): p for p in range(2, pages + 1)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    data = future.result()
                    if data:
                        all_data.extend(data)
                except Exception:
                    pass
    except Exception as e:
        print(f"东方财富拉取失败 ({fs[:30]}): {e}")

    return all_data


# ========== A 股数据（新浪主 + 东方财富备 + AKShare兜底） ==========

def _fetch_stock_spot_sina() -> pd.DataFrame:
    """全量A股实时行情（新浪数据源）"""
    raw = _fetch_sina_list("hs_a", max_pages=70)

    rows = []
    seen = set()
    for item in raw:
        try:
            code = str(item.get("code", "")).zfill(6)
            if code in seen or not code or len(code) != 6:
                continue
            seen.add(code)

            name = str(item.get("name", ""))
            price = float(item.get("trade", 0) or 0)
            change_pct = float(item.get("changepercent", 0) or 0)
            change = float(item.get("pricechange", 0) or 0)
            volume = float(item.get("volume", 0) or 0)
            amount = float(item.get("amount", 0) or 0)
            high = float(item.get("high", 0) or 0)
            low = float(item.get("low", 0) or 0)
            open_price = float(item.get("open", 0) or 0)
            pre_close = float(item.get("settlement", 0) or 0)

            if price <= 0:
                price = pre_close

            fixed_name = _fix_stock_name(code, name)
            rows.append({
                "代码": code,
                "名称": fixed_name,
                "名称_original": name,
                "名称_clean": _clean_stock_name(name),
                "最新价": price,
                "涨跌额": change,
                "涨跌幅": change_pct,
                "今开": open_price,
                "最高": high,
                "最低": low,
                "昨收": pre_close,
                "成交量": volume,
                "成交额": amount,
            })
        except (ValueError, TypeError):
            continue

    return pd.DataFrame(rows)


def _fetch_stock_spot_em() -> pd.DataFrame:
    """全量A股实时行情（东方财富备用）"""
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    raw = _fetch_em_list(fs)

    rows = []
    seen = set()
    for item in raw:
        try:
            code = str(item.get("f12", "")).zfill(6)
            if code in seen or not code or len(code) != 6:
                continue
            seen.add(code)

            name = str(item.get("f14", ""))
            price = float(item.get("f2", 0) or 0)
            change_pct = float(item.get("f3", 0) or 0)
            change = float(item.get("f4", 0) or 0)
            volume = float(item.get("f5", 0) or 0)
            amount = float(item.get("f6", 0) or 0)
            high = float(item.get("f15", 0) or 0)
            low = float(item.get("f16", 0) or 0)
            open_price = float(item.get("f17", 0) or 0)
            pre_close = float(item.get("f18", 0) or 0)

            if price <= 0:
                price = pre_close

            fixed_name = _fix_stock_name(code, name)
            rows.append({
                "代码": code,
                "名称": fixed_name,
                "名称_original": name,
                "名称_clean": _clean_stock_name(name),
                "最新价": price,
                "涨跌额": change,
                "涨跌幅": change_pct,
                "今开": open_price,
                "最高": high,
                "最低": low,
                "昨收": pre_close,
                "成交量": volume,
                "成交额": amount,
            })
        except (ValueError, TypeError):
            continue

    return pd.DataFrame(rows)


def _fetch_stock_spot() -> pd.DataFrame:
    """全量A股实时行情（多数据源冗余）"""
    print("正在获取A股数据...")

    df = _fetch_stock_spot_sina()
    if df is not None and not df.empty and len(df) > 1000:
        print(f"新浪数据源成功，共 {len(df)} 只A股")
        return df

    print("新浪数据源失败，尝试东方财富...")
    df = _fetch_stock_spot_em()
    if df is not None and not df.empty and len(df) > 1000:
        print(f"东方财富数据源成功，共 {len(df)} 只A股")
        return df

    print("东方财富数据源失败，尝试AKShare兜底...")
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            rows = []
            for _, row in df.iterrows():
                try:
                    code = str(row.get("代码", "")).zfill(6)
                    name = str(row.get("名称", ""))
                    price = float(row.get("最新价", 0) or 0)
                    change_pct = float(row.get("涨跌幅", 0) or 0)
                    change = float(row.get("涨跌额", 0) or 0)
                    volume = float(row.get("成交量", 0) or 0)
                    amount = float(row.get("成交额", 0) or 0)
                    high = float(row.get("最高", 0) or 0)
                    low = float(row.get("最低", 0) or 0)
                    open_price = float(row.get("今开", 0) or 0)
                    pre_close = float(row.get("昨收", 0) or 0)

                    if price <= 0:
                        price = pre_close

                    fixed_name = _fix_stock_name(code, name)
                    rows.append({
                        "代码": code,
                        "名称": fixed_name,
                        "名称_original": name,
                        "名称_clean": _clean_stock_name(name),
                        "最新价": price,
                        "涨跌额": change,
                        "涨跌幅": change_pct,
                        "今开": open_price,
                        "最高": high,
                        "最低": low,
                        "昨收": pre_close,
                        "成交量": volume,
                        "成交额": amount,
                    })
                except (ValueError, TypeError):
                    continue
            result = pd.DataFrame(rows)
            print(f"AKShare兜底成功，共 {len(result)} 只A股")
            return result
    except Exception as e:
        print(f"AKShare也失败: {e}")

    print("所有A股数据源都失败了！")
    return pd.DataFrame()


# ========== 港股数据（AKShare腾讯主 + 新浪单股备 + 别名兜底） ==========

def _is_hk_stock(code: str, name: str) -> bool:
    """判断是否为港股正股（过滤权证、衍生品等）"""
    code = str(code).zfill(5)
    name = str(name)
    bad_patterns = ['购', '沽', '牛', '熊', '权证', 'N28', 'B27', 'N26', 'B26']
    for p in bad_patterns:
        if p in name:
            return False
    if code.startswith('8'):
        return False
    return True


def _fetch_hk_spot_ak_tencent() -> list[dict]:
    """全量港股实时行情（AKShare腾讯数据源 - 主数据源）"""
    try:
        df = ak.stock_hk_spot()
        if df is None or df.empty:
            return []
        results = []
        seen = set()
        for _, row in df.iterrows():
            try:
                code = str(row.get("代码", "")).zfill(5)
                name = str(row.get("中文名称", ""))
                if code in seen or not code:
                    continue
                if not _is_hk_stock(code, name):
                    continue
                seen.add(code)

                price = float(row.get("最新价", 0) or 0)
                change = float(row.get("涨跌额", 0) or 0)
                change_pct = float(row.get("涨跌幅", 0) or 0)
                volume = float(row.get("成交量", 0) or 0)
                amount = float(row.get("成交额", 0) or 0)
                high = float(row.get("最高", 0) or 0)
                low = float(row.get("最低", 0) or 0)
                open_price = float(row.get("今开", 0) or 0)
                pre_close = float(row.get("昨收", 0) or 0)

                if price <= 0:
                    price = pre_close

                fixed_name = _fix_stock_name("hk" + code, name)
                results.append({
                    "code": code,
                    "name": fixed_name,
                    "name_original": name,
                    "name_clean": _clean_stock_name(name),
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "pre_close": pre_close,
                    "volume": volume,
                    "amount": amount,
                })
            except (ValueError, TypeError):
                continue
        return results
    except Exception as e:
        print(f"AKShare腾讯港股失败: {e}")
        return []


def _fetch_hk_spot_em() -> list[dict]:
    """全量港股实时行情（东方财富备用）"""
    fs = "m:128+t:3,m:128+t:4,m:128+t:1,m:128+t:2"
    raw = _fetch_em_list(fs)

    results = []
    seen = set()
    for item in raw:
        try:
            code = str(item.get("f12", "")).zfill(5)
            name = str(item.get("f14", ""))
            if code in seen or not code:
                continue
            if not _is_hk_stock(code, name):
                continue
            seen.add(code)

            price = float(item.get("f2", 0) or 0)
            change_pct = float(item.get("f3", 0) or 0)
            change = float(item.get("f4", 0) or 0)
            volume = float(item.get("f5", 0) or 0)
            amount = float(item.get("f6", 0) or 0)
            high = float(item.get("f15", 0) or 0)
            low = float(item.get("f16", 0) or 0)
            open_price = float(item.get("f17", 0) or 0)
            pre_close = float(item.get("f18", 0) or 0)

            if price <= 0:
                price = pre_close

            fixed_name = _fix_stock_name("hk" + code, name)
            results.append({
                "code": code,
                "name": fixed_name,
                "name_original": name,
                "name_clean": _clean_stock_name(name),
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "open": open_price,
                "high": high,
                "low": low,
                "pre_close": pre_close,
                "volume": volume,
                "amount": amount,
            })
        except (ValueError, TypeError):
            continue

    return results


def _fetch_hk_spot_from_aliases() -> list[dict]:
    """从别名映射中构建港股列表（最小可用方案）"""
    results = []
    seen = set()
    session = _session()
    headers = {"Referer": "https://finance.sina.com.cn"}

    hk_codes = []
    for alias, code in _STOCK_ALIASES.items():
        if code.startswith("hk") and code not in seen:
            seen.add(code)
            hk_codes.append(code)

    if not hk_codes:
        return []

    try:
        symbols = ",".join(hk_codes)
        url = f"http://hq.sinajs.cn/list={symbols}"
        r = session.get(url, headers=headers, timeout=10)
        text = r.text

        for line in text.strip().split("\n"):
            if not line.strip() or "=" not in line:
                continue
            try:
                var_name, var_value = line.split("=", 1)
                full_code = var_name.split("hq_str_")[-1]
                var_value = var_value.strip('"; ')
                fields = var_value.split(",")
                if len(fields) < 6:
                    continue

                code = full_code.replace("hk", "").zfill(5)
                name_en = fields[0] if len(fields) > 0 else ""
                name_cn = fields[1] if len(fields) > 1 else ""
                name = name_cn if name_cn else name_en

                price = float(fields[6]) if len(fields) > 6 else 0
                pre_close = float(fields[3]) if len(fields) > 3 else 0
                change = float(fields[7]) if len(fields) > 7 else 0
                change_pct = float(fields[8]) if len(fields) > 8 else 0
                high = float(fields[5]) if len(fields) > 5 else 0
                low = float(fields[4]) if len(fields) > 4 else 0
                open_price = float(fields[2]) if len(fields) > 2 else 0
                volume = float(fields[12]) if len(fields) > 12 else 0
                amount = float(fields[11]) if len(fields) > 11 else 0

                if price <= 0:
                    price = pre_close

                fixed_name = _fix_stock_name("hk" + code, name)
                results.append({
                    "code": code,
                    "name": fixed_name,
                    "name_original": name,
                    "name_clean": _clean_stock_name(name),
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "pre_close": pre_close,
                    "volume": volume,
                    "amount": amount,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"从别名构建港股列表失败: {e}")

    return results


def _fetch_hk_spot() -> list[dict]:
    """全量港股实时行情（多数据源冗余）"""
    print("正在获取港股数据...")

    hk_list = _fetch_hk_spot_ak_tencent()
    if hk_list and len(hk_list) > 100:
        print(f"AKShare腾讯港股成功，共 {len(hk_list)} 只")
        return hk_list

    print("AKShare腾讯港股失败，尝试东方财富...")
    hk_list = _fetch_hk_spot_em()
    if hk_list and len(hk_list) > 100:
        print(f"东方财富港股成功，共 {len(hk_list)} 只")
        return hk_list

    print("东方财富港股也失败，使用别名最小集...")
    hk_list = _fetch_hk_spot_from_aliases()
    print(f"别名最小集，共 {len(hk_list)} 只")
    return hk_list


# ========== ETF 数据（新浪 + 东方财富 + AKShare） ==========

def _fetch_etf_spot_sina() -> pd.DataFrame:
    """ETF实时行情（新浪）"""
    raw = _fetch_sina_list("etf_hq_fund", max_pages=20)

    rows = []
    seen = set()
    for item in raw:
        try:
            code = str(item.get("code", ""))
            if code in seen or not code:
                continue
            seen.add(code)

            name = str(item.get("name", ""))
            price = float(item.get("trade", 0) or 0)
            change_pct = float(item.get("changepercent", 0) or 0)
            change = float(item.get("pricechange", 0) or 0)
            volume = float(item.get("volume", 0) or 0)
            amount = float(item.get("amount", 0) or 0)
            high = float(item.get("high", 0) or 0)
            low = float(item.get("low", 0) or 0)
            open_price = float(item.get("open", 0) or 0)
            pre_close = float(item.get("settlement", 0) or 0)

            if price <= 0:
                price = pre_close

            fixed_name = _fix_stock_name(code, name)
            rows.append({
                "代码": code,
                "名称": fixed_name,
                "名称_original": name,
                "名称_clean": _clean_stock_name(name),
                "最新价": price,
                "涨跌额": change,
                "涨跌幅": change_pct,
                "今开": open_price,
                "最高": high,
                "最低": low,
                "昨收": pre_close,
                "成交量": volume,
                "成交额": amount,
            })
        except (ValueError, TypeError):
            continue

    return pd.DataFrame(rows)


def _fetch_etf_spot_em() -> pd.DataFrame:
    """ETF实时行情（东方财富）"""
    fs = "b:MK0021,b:MK0022,b:MK0023,b:MK0024"
    raw = _fetch_em_list(fs)

    rows = []
    seen = set()
    for item in raw:
        try:
            code = str(item.get("f12", ""))
            if code in seen or not code:
                continue
            seen.add(code)

            name = str(item.get("f14", ""))
            price = float(item.get("f2", 0) or 0)
            change_pct = float(item.get("f3", 0) or 0)
            change = float(item.get("f4", 0) or 0)
            volume = float(item.get("f5", 0) or 0)
            amount = float(item.get("f6", 0) or 0)
            high = float(item.get("f15", 0) or 0)
            low = float(item.get("f16", 0) or 0)
            open_price = float(item.get("f17", 0) or 0)
            pre_close = float(item.get("f18", 0) or 0)

            if price <= 0:
                price = pre_close

            fixed_name = _fix_stock_name(code, name)
            rows.append({
                "代码": code,
                "名称": fixed_name,
                "名称_original": name,
                "名称_clean": _clean_stock_name(name),
                "最新价": price,
                "涨跌额": change,
                "涨跌幅": change_pct,
                "今开": open_price,
                "最高": high,
                "最低": low,
                "昨收": pre_close,
                "成交量": volume,
                "成交额": amount,
            })
        except (ValueError, TypeError):
            continue

    return pd.DataFrame(rows)


def _fetch_etf_spot() -> pd.DataFrame:
    """ETF实时行情（多数据源冗余）"""
    print("正在获取ETF数据...")

    df = _fetch_etf_spot_sina()
    if df is not None and not df.empty and len(df) > 50:
        print(f"新浪ETF成功，共 {len(df)} 只")
        return df

    print("新浪ETF失败，尝试东方财富...")
    df = _fetch_etf_spot_em()
    if df is not None and not df.empty and len(df) > 50:
        print(f"东方财富ETF成功，共 {len(df)} 只")
        return df

    print("东方财富ETF失败，尝试AKShare...")
    try:
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            rows = []
            for _, row in df.iterrows():
                try:
                    code = str(row.get("代码", ""))
                    name = str(row.get("名称", ""))
                    price = float(row.get("最新价", 0) or 0)
                    change_pct = float(row.get("涨跌幅", 0) or 0)
                    change = float(row.get("涨跌额", 0) or 0)
                    volume = float(row.get("成交量", 0) or 0)
                    amount = float(row.get("成交额", 0) or 0)
                    high = float(row.get("最高", 0) or 0)
                    low = float(row.get("最低", 0) or 0)
                    open_price = float(row.get("开盘价", 0) or 0)
                    pre_close = float(row.get("昨收", 0) or 0)

                    if price <= 0:
                        price = pre_close

                    fixed_name = _fix_stock_name(code, name)
                    rows.append({
                        "代码": code,
                        "名称": fixed_name,
                        "名称_original": name,
                        "名称_clean": _clean_stock_name(name),
                        "最新价": price,
                        "涨跌额": change,
                        "涨跌幅": change_pct,
                        "今开": open_price,
                        "最高": high,
                        "最低": low,
                        "昨收": pre_close,
                        "成交量": volume,
                        "成交额": amount,
                    })
                except (ValueError, TypeError):
                    continue
            result = pd.DataFrame(rows)
            print(f"AKShare ETF成功，共 {len(result)} 只")
            return result
    except Exception as e:
        print(f"AKShare ETF失败: {e}")

    print("所有ETF数据源都失败了！")
    return pd.DataFrame()


# ========== 指数数据 ==========

def _fetch_index_spot() -> dict:
    """主要市场指数（新浪数据源）"""
    session = _session()
    index_map = {
        "s_sh000001": "上证指数",
        "s_sz399001": "深证成指",
        "s_sz399006": "创业板指",
        "s_sh000300": "沪深300",
    }
    symbols = ",".join(index_map.keys())
    try:
        url = f"http://hq.sinajs.cn/list={symbols}"
        r = session.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
        text = r.text
        indices = {}
        for line in text.strip().split("\n"):
            if not line.strip() or "=" not in line:
                continue
            try:
                var_name, var_value = line.split("=", 1)
                code = var_name.split("hq_str_")[-1]
                if code not in index_map:
                    continue
                var_value = var_value.strip('"; ')
                fields = var_value.split(",")
                if len(fields) < 4:
                    continue
                name = index_map[code]
                price = float(fields[1])
                change_pct = float(fields[3])
                indices[name] = {"price": price, "change_pct": change_pct}
            except Exception:
                continue
        return indices
    except Exception as e:
        print(f"获取指数失败: {e}")
        return {}


# ========== 搜索 ==========

def search_stock(keyword: str) -> list[dict]:
    """搜索股票（A股 + 港股），支持别名匹配、拼音、代码等，非阻塞优先"""
    results = []
    kw = keyword.strip()
    if not kw:
        return results
    kw_lower = kw.lower()

    try:
        df = _cached("stock_spot", _fetch_stock_spot, wait=True)
        if df is not None and not df.empty and "名称_clean" in df.columns:
            mask = (
                df["名称"].str.contains(kw, na=False, case=False) |
                df["名称_clean"].str.contains(kw, na=False, case=False) |
                df["名称_original"].str.contains(kw, na=False, case=False) |
                df["代码"].str.contains(kw, na=False)
            )
            matched = df[mask]
            for _, row in matched.head(30).iterrows():
                results.append({
                    "code": str(row["代码"]),
                    "name": str(row["名称"]),
                    "price": float(row["最新价"]),
                    "change": float(row["涨跌额"]),
                    "change_pct": float(row["涨跌幅"]),
                    "type": "stock",
                })
    except Exception as e:
        print(f"搜索 A 股失败: {e}")

    try:
        hk_list = _cached("hk_spot", _fetch_hk_spot, ttl=180, wait=False)
        if hk_list:
            for item in hk_list:
                code = str(item.get("code", ""))
                name = str(item.get("name", ""))
                name_clean = str(item.get("name_clean", name))
                name_original = str(item.get("name_original", name))
                if (kw_lower in code.lower() or
                    kw_lower in name.lower() or
                    kw_lower in name_clean.lower() or
                    kw_lower in name_original.lower()):
                    results.append({
                        "code": "hk" + code,
                        "name": name,
                        "price": item.get("price", 0),
                        "change": item.get("change", 0),
                        "change_pct": item.get("change_pct", 0),
                        "type": "stock_hk",
                    })
            results = results[:50]
    except Exception as e:
        print(f"搜索港股失败: {e}")

    if len(results) < 15:
        try:
            alias_results = _search_alias(kw)
            existing_codes = {r["code"] for r in results}
            for ar in alias_results:
                if ar["code"] not in existing_codes:
                    results.append(ar)
                    existing_codes.add(ar["code"])
        except Exception as e:
            print(f"别名搜索失败: {e}")

    def _search_score(item):
        name = item["name"].lower()
        code = item["code"].lower()
        score = 0
        if name == kw_lower or code == kw_lower:
            score += 100
        elif name.startswith(kw_lower):
            score += 50
        elif kw_lower in name:
            score += 20
        if code.startswith(kw_lower) or code.endswith(kw_lower):
            score += 30
        if item["type"] == "stock":
            score += 5
        return score

    results.sort(key=_search_score, reverse=True)
    return results[:50]


def get_stock_quote(code: str) -> Optional[dict]:
    """获取单只股票实时行情"""
    if code.startswith("hk"):
        hk_code = code[2:].zfill(5)
        try:
            hk_list = _cached("hk_spot", _fetch_hk_spot, ttl=180)
            if hk_list:
                for item in hk_list:
                    if str(item.get("code", "")).zfill(5) == hk_code:
                        return {
                            "code": "hk" + hk_code,
                            "name": str(item.get("name", "")),
                            "price": float(item.get("price", 0)),
                            "change": float(item.get("change", 0)),
                            "change_pct": float(item.get("change_pct", 0)),
                            "open": float(item.get("open", 0)),
                            "high": float(item.get("high", 0)),
                            "low": float(item.get("low", 0)),
                            "pre_close": float(item.get("pre_close", 0)),
                            "volume": float(item.get("volume", 0)),
                            "amount": float(item.get("amount", 0)),
                            "type": "stock_hk",
                        }
        except Exception as e:
            print(f"获取港股行情失败: {e}")

        try:
            session = _session()
            headers = {"Referer": "https://finance.sina.com.cn"}
            url = f"http://hq.sinajs.cn/list=hk{hk_code}"
            r = session.get(url, headers=headers, timeout=8)
            text = r.text
            for line in text.strip().split("\n"):
                if not line.strip() or "=" not in line:
                    continue
                var_name, var_value = line.split("=", 1)
                var_value = var_value.strip('"; ')
                fields = var_value.split(",")
                if len(fields) < 10:
                    continue
                name_cn = fields[1] if len(fields) > 1 else ""
                price = float(fields[6]) if len(fields) > 6 else 0
                pre_close = float(fields[3]) if len(fields) > 3 else 0
                change = float(fields[7]) if len(fields) > 7 else 0
                change_pct = float(fields[8]) if len(fields) > 8 else 0
                high = float(fields[5]) if len(fields) > 5 else 0
                low = float(fields[4]) if len(fields) > 4 else 0
                open_price = float(fields[2]) if len(fields) > 2 else 0
                volume = float(fields[12]) if len(fields) > 12 else 0
                amount = float(fields[11]) if len(fields) > 11 else 0

                if price <= 0:
                    price = pre_close

                fixed_name = _fix_stock_name("hk" + hk_code, name_cn)
                return {
                    "code": "hk" + hk_code,
                    "name": fixed_name,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "pre_close": pre_close,
                    "volume": volume,
                    "amount": amount,
                    "type": "stock_hk",
                }
        except Exception as e:
            print(f"新浪港股单股行情失败: {e}")

        return None

    try:
        df = _cached("stock_spot", _fetch_stock_spot)
        if df is not None and not df.empty:
            clean_code = _clean_code(code)
            mask = df["代码"].str.contains(clean_code, regex=False, na=False)
            row = df[mask]
            if not row.empty:
                r = row.iloc[0]
                return {
                    "code": str(r["代码"]),
                    "name": str(r["名称"]),
                    "price": float(r["最新价"]),
                    "change": float(r["涨跌额"]),
                    "change_pct": float(r["涨跌幅"]),
                    "open": float(r["今开"]),
                    "high": float(r["最高"]),
                    "low": float(r["最低"]),
                    "pre_close": float(r["昨收"]),
                    "volume": float(r["成交量"]),
                    "amount": float(r["成交额"]),
                    "type": "stock",
                }
    except Exception as e:
        print(f"从列表获取股票行情失败: {e}")

    try:
        session = _session()
        headers = {"Referer": "https://finance.sina.com.cn"}
        clean_code = _clean_code(code).zfill(6)
        if clean_code[0] in ('6', '9'):
            full_code = f"sh{clean_code}"
        else:
            full_code = f"sz{clean_code}"
        url = f"http://hq.sinajs.cn/list={full_code}"
        r = session.get(url, headers=headers, timeout=8)
        text = r.text
        for line in text.strip().split("\n"):
            if not line.strip() or "=" not in line:
                continue
            var_name, var_value = line.split("=", 1)
            var_value = var_value.strip('"; ')
            fields = var_value.split(",")
            if len(fields) < 10:
                continue
            name = fields[0]
            open_price = float(fields[1]) if len(fields) > 1 else 0
            pre_close = float(fields[2]) if len(fields) > 2 else 0
            price = float(fields[3]) if len(fields) > 3 else 0
            high = float(fields[4]) if len(fields) > 4 else 0
            low = float(fields[5]) if len(fields) > 5 else 0
            volume = float(fields[8]) if len(fields) > 8 else 0
            amount = float(fields[9]) if len(fields) > 9 else 0
            change = price - pre_close
            change_pct = (change / pre_close * 100) if pre_close > 0 else 0

            if price <= 0:
                price = pre_close

            fixed_name = _fix_stock_name(clean_code, name)
            return {
                "code": clean_code,
                "name": fixed_name,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "open": open_price,
                "high": high,
                "low": low,
                "pre_close": pre_close,
                "volume": volume,
                "amount": amount,
                "type": "stock",
            }
    except Exception as e:
        print(f"新浪单股行情失败: {e}")

    return None


# ========== 历史数据 ==========

def _fetch_em_history(secid: str, days: int = 90) -> list[dict]:
    """东方财富历史K线（备用）"""
    session = _session()
    url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    end_date = pd.Timestamp.now().strftime("%Y%m%d")
    start_date = (pd.Timestamp.now() - pd.Timedelta(days=days + 60)).strftime("%Y%m%d")

    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": start_date,
        "end": end_date,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }

    try:
        r = session.get(url, params=params, timeout=15)
        data = r.json()
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return []
        results = []
        for line in klines[-days:]:
            parts = line.split(",")
            if len(parts) < 6:
                continue
            try:
                results.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]) if len(parts) > 6 else 0,
                })
            except (ValueError, IndexError):
                continue
        return results
    except Exception as e:
        print(f"东方财富历史数据失败 ({secid}): {e}")
        return []


def _fetch_sina_history(code: str, days: int = 90) -> list[dict]:
    """新浪历史K线（主数据源）"""
    session = _session()
    code = _clean_code(code)
    if len(code) == 6 and code[0] in ('6', '9', '5'):
        full_code = f"sh{code}"
    elif len(code) == 6 and code[0] in ('0', '3', '1'):
        full_code = f"sz{code}"
    else:
        full_code = f"sz{code}"

    url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {
        "symbol": full_code, "scale": 240, "ma": "no", "datalen": days + 20,
    }
    try:
        r = session.get(url, params=params, timeout=12)
        data = r.json()
        if not data or not isinstance(data, list):
            return []
        results = []
        for item in data:
            try:
                results.append({
                    "date": str(item.get("day", "")),
                    "open": float(item.get("open", 0)),
                    "close": float(item.get("close", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "volume": float(item.get("volume", 0)),
                    "amount": float(item.get("amount", 0)),
                })
            except Exception:
                continue
        return results[-days:]
    except Exception:
        return []


def _fetch_tencent_hk_history(code: str, days: int = 90) -> list[dict]:
    """腾讯财经港股历史K线（主数据源）"""
    session = _session()
    url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        'param': f'hk{code},day,,,{days + 20},qfq',
    }
    try:
        r = session.get(url, params=params, timeout=12)
        data = r.json()
        if not data.get('data'):
            return []
        stock_data = data['data'].get(f'hk{code}', {})
        klines = stock_data.get('qfqday', stock_data.get('day', []))
        if not klines:
            return []
        results = []
        for kline in klines[-days:]:
            try:
                results.append({
                    "date": str(kline[0]),
                    "open": float(kline[1]),
                    "close": float(kline[2]),
                    "high": float(kline[3]),
                    "low": float(kline[4]),
                    "volume": float(kline[5]),
                    "amount": 0,
                })
            except (ValueError, IndexError):
                continue
        return results
    except Exception as e:
        print(f"腾讯港股历史数据失败 ({code}): {e}")
        return []


def _fetch_sina_hk_history(code: str, days: int = 90) -> list[dict]:
    """新浪港股历史K线（备用）"""
    return []


def get_stock_history(code: str, period: str = "daily", days: int = 90) -> list[dict]:
    """获取股票历史K线（多数据源冗余）"""
    code = str(code).strip().lower()
    is_hk = code.startswith("hk") or (code.isdigit() and len(code) <= 5)
    if is_hk:
        hk_code = code.replace("hk", "").zfill(5)
        cache_key = f"history_hk_{hk_code}_{days}"
        def _hk_fetcher():
            hk_code = code.replace("hk", "").zfill(5)
            min_required = min(days, 10)
            tencent_data = _fetch_tencent_hk_history(hk_code, days)
            if tencent_data and len(tencent_data) >= min_required:
                return tencent_data
            em_data = _fetch_em_history(f"116.{hk_code}", days)
            if em_data and len(em_data) >= min_required:
                return em_data
            try:
                df = ak.stock_hk_hist(
                    symbol=hk_code, period=period,
                    start_date=(pd.Timestamp.now() - pd.Timedelta(days=days + 30)).strftime("%Y%m%d"),
                    end_date=pd.Timestamp.now().strftime("%Y%m%d"), adjust="qfq",
                )
                if df is None or df.empty:
                    return []
                results = []
                for _, row in df.tail(days).iterrows():
                    results.append({
                        "date": str(row["日期"]),
                        "open": float(row["开盘"]),
                        "close": float(row["收盘"]),
                        "high": float(row["最高"]),
                        "low": float(row["最低"]),
                        "volume": float(row["成交量"]),
                        "amount": float(row.get("成交额", 0)),
                    })
                return results
            except Exception as e:
                print(f"AKShare港股历史失败: {e}")
                return []
        return _cached(cache_key, _hk_fetcher, ttl=300)

    cache_key = f"history_{code}_{days}"
    def _fetcher():
        clean_code = _clean_code(code)
        sina_data = _fetch_sina_history(code, days)
        min_required = min(days, 10)
        if sina_data and len(sina_data) >= min_required:
            return sina_data
        if len(clean_code) == 6 and clean_code[0] in ('6', '9', '5'):
            secid = f"1.{clean_code}"
        else:
            secid = f"0.{clean_code}"
        em_data = _fetch_em_history(secid, days)
        if em_data and len(em_data) >= min_required:
            return em_data
        try:
            df = ak.stock_zh_a_hist(
                symbol=clean_code, period=period,
                start_date=(pd.Timestamp.now() - pd.Timedelta(days=days + 30)).strftime("%Y%m%d"),
                end_date=pd.Timestamp.now().strftime("%Y%m%d"), adjust="qfq",
            )
            if df is None or df.empty:
                return []
            results = []
            for _, row in df.tail(days).iterrows():
                results.append({
                    "date": str(row["日期"]),
                    "open": float(row["开盘"]),
                    "close": float(row["收盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "volume": float(row["成交量"]),
                    "amount": float(row.get("成交额", 0)),
                })
            return results
        except Exception as e:
            print(f"获取历史数据失败 {code}: {e}")
            return []
    return _cached(cache_key, _fetcher, ttl=300)


# ========== 基金搜索 ==========

def search_fund(keyword: str) -> list[dict]:
    """搜索基金（ETF + 开放式基金）"""
    results = []
    kw = keyword.strip()
    if not kw:
        return results

    try:
        df = _cached("etf_spot", _fetch_etf_spot, wait=True)
        if df is not None and not df.empty and "名称_clean" in df.columns:
            mask = (
                df["名称"].str.contains(kw, na=False, case=False) |
                df["名称_clean"].str.contains(kw, na=False, case=False) |
                df["名称_original"].str.contains(kw, na=False, case=False) |
                df["代码"].str.contains(kw, na=False)
            )
            matched = df[mask]
            for _, row in matched.head(20).iterrows():
                results.append({
                    "code": str(row["代码"]),
                    "name": str(row["名称"]),
                    "price": float(row["最新价"]),
                    "change": float(row["涨跌额"]),
                    "change_pct": float(row["涨跌幅"]),
                    "type": "etf",
                })
    except Exception as e:
        print(f"搜索 ETF 失败: {e}")

    if len(results) < 10:
        try:
            import akshare as ak
            df_all = _cached("fund_name", lambda: ak.fund_name_em(), ttl=3600, wait=True)
            if df_all is not None and not df_all.empty:
                mask = (df_all["基金简称"].str.contains(kw, na=False, case=False) |
                        df_all["基金代码"].str.contains(kw, na=False))
                matched = df_all[mask]
                for _, row in matched.head(20).iterrows():
                    code = str(row["基金代码"])
                    if not any(r["code"] == code for r in results):
                        results.append({
                            "code": code,
                            "name": str(row["基金简称"]),
                            "price": 0,
                            "change": 0,
                            "change_pct": 0,
                            "type": "fund",
                        })
        except Exception as e:
            print(f"搜索开放式基金失败: {e}")

    return results


def get_fund_quote(code: str) -> Optional[dict]:
    """获取基金实时行情"""
    try:
        df = _cached("etf_spot", _fetch_etf_spot)
        if df is not None and not df.empty:
            row = df[df["代码"] == code]
            if not row.empty:
                r = row.iloc[0]
                return {
                    "code": str(r["代码"]),
                    "name": str(r["名称"]),
                    "price": float(r["最新价"]),
                    "change": float(r["涨跌额"]),
                    "change_pct": float(r["涨跌幅"]),
                    "open": float(r["今开"]),
                    "high": float(r["最高"]),
                    "low": float(r["最低"]),
                    "pre_close": float(r["昨收"]),
                    "volume": float(r["成交量"]),
                    "amount": float(r["成交额"]),
                    "type": "etf",
                }
    except Exception:
        pass

    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            price = float(latest["单位净值"])
            prev_price = float(prev["单位净值"])
            return {
                "code": code,
                "name": code,
                "price": price,
                "change": round(price - prev_price, 4),
                "change_pct": round((price - prev_price) / prev_price * 100, 2) if prev_price else 0,
                "open": price,
                "high": price,
                "low": price,
                "volume": 0,
                "amount": 0,
                "type": "fund",
            }
    except Exception as e:
        print(f"获取基金净值失败: {e}")
    return None


def get_fund_history(code: str, days: int = 90) -> list[dict]:
    """获取基金历史净值走势"""
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.tail(days).iterrows():
            results.append({
                "date": str(row["净值日期"]),
                "open": float(row["单位净值"]),
                "close": float(row["单位净值"]),
                "high": float(row["单位净值"]),
                "low": float(row["单位净值"]),
                "volume": 0,
                "amount": 0,
            })
        return results
    except Exception as e:
        print(f"获取基金历史数据失败: {e}")
        return []


def get_market_index() -> dict:
    """主要市场指数"""
    try:
        return _cached("index_spot", _fetch_index_spot, ttl=60)
    except Exception as e:
        print(f"获取指数失败: {e}")
        return {}
