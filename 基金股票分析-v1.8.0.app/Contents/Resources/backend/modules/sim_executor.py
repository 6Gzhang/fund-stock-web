"""
模块7: 模拟执行与全局配置
- 限价/市价模拟委托，未成交订单可撤单
- 支持3个独立虚拟子账户
- 本地CSV导入持仓
- 日/周/月自动AI复盘
- AI调用用量可视化统计
- 自定义屏蔽分析关键词
- 配置文件损坏自动恢复
- 自定义软件存储路径，一键迁移全部本地数据
"""
import os
import json
import csv
import shutil
import time
from datetime import datetime, timedelta
from typing import Optional

MODULE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(MODULE_DIR, "Data")
CONFIG_FILE = os.path.join(DATA_DIR, "module_config.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "virtual_accounts.json")
ORDERS_FILE = os.path.join(DATA_DIR, "sim_orders.json")
REVIEWS_FILE = os.path.join(DATA_DIR, "ai_reviews.json")

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "storage_path": DATA_DIR,
    "blocked_keywords": [],
    "auto_review_schedule": {"daily": True, "weekly": True, "monthly": True},
    "ai_call_limit": {"daily": 100, "used": 0, "reset_date": datetime.now().strftime("%Y-%m-%d")},
    "last_migration": None,
    "version": "1.0.0",
}

_default_accounts = {
    "accounts": [
        {"id": "default", "name": "主账户", "cash": 1000000, "created_at": datetime.now().isoformat()},
        {"id": "account2", "name": "账户2", "cash": 500000, "created_at": datetime.now().isoformat()},
        {"id": "account3", "name": "账户3", "cash": 300000, "created_at": datetime.now().isoformat()},
    ],
    "active_account": "default",
}


def _load_json(path: str, default: dict = None):
    """安全加载JSON（损坏自动恢复）"""
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, Exception):
        print(f"[模块7] 配置文件损坏，自动恢复: {path}")
        if default:
            _save_json(path, default)
    return default or {}


def _save_json(path: str, data: dict):
    """安全保存JSON"""
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ========== 模拟委托 ==========

def place_order(account_id: str, code: str, name: str, price: float, shares: float,
                order_type: str = "market", limit_price: float = None, action: str = "buy", market: str = "A"):
    """限价/市价模拟委托"""
    orders = _load_json(ORDERS_FILE, {"orders": []})
    accounts = _load_json(ACCOUNTS_FILE, _default_accounts)
    
    # 找到账户
    account = next((a for a in accounts["accounts"] if a["id"] == account_id), None)
    if not account:
        return {"success": False, "error": "账户不存在"}
    
    order = {
        "id": f"ORD{int(time.time())}{len(orders['orders']):04d}",
        "account_id": account_id,
        "code": code,
        "name": name,
        "price": price,
        "limit_price": limit_price,
        "shares": shares,
        "order_type": order_type,
        "action": action,
        "market": market,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "filled_at": None,
        "filled_price": None,
    }
    
    # 市价单立即成交
    if order_type == "market":
        order["status"] = "filled"
        order["filled_at"] = datetime.now().isoformat()
        order["filled_price"] = price
    
    orders["orders"].append(order)
    _save_json(ORDERS_FILE, orders)
    
    return {"success": True, "order": order}


def cancel_order(order_id: str):
    """撤单"""
    orders = _load_json(ORDERS_FILE, {"orders": []})
    for o in orders["orders"]:
        if o["id"] == order_id and o["status"] == "pending":
            o["status"] = "cancelled"
            _save_json(ORDERS_FILE, orders)
            return {"success": True, "order": o}
    return {"success": False, "error": "订单不存在或已成交"}


def get_orders(account_id: str = None, status: str = None):
    """获取订单列表"""
    orders = _load_json(ORDERS_FILE, {"orders": []})
    result = orders["orders"]
    if account_id:
        result = [o for o in result if o["account_id"] == account_id]
    if status:
        result = [o for o in result if o["status"] == status]
    return result[-50:]  # 最近50条


# ========== 虚拟子账户 ==========

def get_accounts():
    """获取所有虚拟账户"""
    return _load_json(ACCOUNTS_FILE, _default_accounts)


def switch_account(account_id: str):
    """切换活跃账户"""
    accounts = _load_json(ACCOUNTS_FILE, _default_accounts)
    if any(a["id"] == account_id for a in accounts["accounts"]):
        accounts["active_account"] = account_id
        _save_json(ACCOUNTS_FILE, accounts)
        return {"success": True, "active_account": account_id}
    return {"success": False, "error": "账户不存在"}


def add_account(name: str, initial_cash: float = 100000):
    """添加虚拟账户"""
    accounts = _load_json(ACCOUNTS_FILE, _default_accounts)
    account_id = f"acc_{int(time.time())}"
    accounts["accounts"].append({
        "id": account_id,
        "name": name,
        "cash": initial_cash,
        "created_at": datetime.now().isoformat(),
    })
    _save_json(ACCOUNTS_FILE, accounts)
    return {"success": True, "account_id": account_id}


# ========== CSV导入持仓 ==========

def import_positions_from_csv(file_path: str, account_id: str = "default"):
    """从CSV导入持仓"""
    try:
        positions = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                positions.append({
                    "code": row.get("code", ""),
                    "name": row.get("name", ""),
                    "shares": float(row.get("shares", 0)),
                    "cost": float(row.get("cost", 0)),
                    "market": row.get("market", "A"),
                    "imported_at": datetime.now().isoformat(),
                })
        
        return {"success": True, "count": len(positions), "positions": positions}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ========== AI复盘 ==========

def save_review(review_type: str, content: str, period: str = "daily"):
    """保存AI复盘"""
    reviews = _load_json(REVIEWS_FILE, {"reviews": []})
    reviews["reviews"].append({
        "type": review_type,
        "content": content,
        "period": period,
        "created_at": datetime.now().isoformat(),
    })
    _save_json(REVIEWS_FILE, reviews)
    return {"success": True}


def get_reviews(period: str = None, limit: int = 10):
    """获取复盘记录"""
    reviews = _load_json(REVIEWS_FILE, {"reviews": []})
    result = reviews["reviews"]
    if period:
        result = [r for r in result if r["period"] == period]
    return result[-limit:]


# ========== AI用量统计 ==========

def track_ai_call():
    """追踪AI调用次数"""
    config = _load_json(CONFIG_FILE, DEFAULT_CONFIG)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if config.get("ai_call_limit", {}).get("reset_date") != today:
        config["ai_call_limit"]["reset_date"] = today
        config["ai_call_limit"]["used"] = 0
    
    config["ai_call_limit"]["used"] += 1
    _save_json(CONFIG_FILE, config)
    
    used = config["ai_call_limit"]["used"]
    limit = config["ai_call_limit"]["daily"]
    return {"used": used, "limit": limit, "remaining": limit - used, "exceeded": used >= limit}


def get_ai_usage():
    """获取AI用量统计"""
    config = _load_json(CONFIG_FILE, DEFAULT_CONFIG)
    return config.get("ai_call_limit", {"daily": 100, "used": 0})


# ========== 配置管理 ==========

def get_module_config():
    """获取模块配置"""
    return _load_json(CONFIG_FILE, DEFAULT_CONFIG)


def update_module_config(**kwargs):
    """更新模块配置"""
    config = _load_json(CONFIG_FILE, DEFAULT_CONFIG)
    for k, v in kwargs.items():
        if k in config:
            config[k] = v
    _save_json(CONFIG_FILE, config)
    return config


def add_blocked_keyword(keyword: str):
    """添加屏蔽关键词"""
    config = _load_json(CONFIG_FILE, DEFAULT_CONFIG)
    if keyword not in config["blocked_keywords"]:
        config["blocked_keywords"].append(keyword)
        _save_json(CONFIG_FILE, config)
    return config["blocked_keywords"]


def remove_blocked_keyword(keyword: str):
    """移除屏蔽关键词"""
    config = _load_json(CONFIG_FILE, DEFAULT_CONFIG)
    if keyword in config["blocked_keywords"]:
        config["blocked_keywords"].remove(keyword)
        _save_json(CONFIG_FILE, config)
    return config["blocked_keywords"]


# ========== 数据迁移 ==========

def migrate_data(new_path: str):
    """一键迁移全部本地数据到新路径"""
    if not os.path.exists(new_path):
        os.makedirs(new_path, exist_ok=True)
    
    migrated = []
    for item in os.listdir(DATA_DIR):
        src = os.path.join(DATA_DIR, item)
        dst = os.path.join(new_path, item)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            migrated.append(item)
        elif os.path.isdir(src) and item != "backups":
            shutil.copytree(src, dst, dirs_exist_ok=True)
            migrated.append(item)
    
    config = _load_json(CONFIG_FILE, DEFAULT_CONFIG)
    config["storage_path"] = new_path
    config["last_migration"] = datetime.now().isoformat()
    _save_json(CONFIG_FILE, config)
    
    return {"success": True, "migrated": migrated, "new_path": new_path}


# 初始化
def init_module():
    """初始化模块7"""
    _load_json(CONFIG_FILE, DEFAULT_CONFIG)
    _load_json(ACCOUNTS_FILE, _default_accounts)