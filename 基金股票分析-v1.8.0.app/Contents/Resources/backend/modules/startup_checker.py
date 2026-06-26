"""
模块8: 启动自检与程序运维
- 抓取、计算、AI、界面四类独立日志
- 开机自检网络、数据源、本地数据库完整性
- 内存过高、数据冗余优化提醒
- 报错精准定位对应模块
- AI离线降级兜底，断AI接口软件可正常使用基础功能
"""
import os
import sys
import time
import json
import logging
import threading
import traceback
from datetime import datetime
from pathlib import Path

MODULE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(MODULE_DIR, "Data")
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ========== 四类独立日志 ==========

class ModuleLogger:
    """四类独立日志系统"""
    _loggers = {}
    
    @classmethod
    def get_logger(cls, category: str):
        if category not in cls._loggers:
            logger = logging.getLogger(f"module_{category}")
            logger.setLevel(logging.INFO)
            
            # 文件handler
            log_file = os.path.join(LOG_DIR, f"{category}_{datetime.now().strftime('%Y%m%d')}.log")
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.INFO)
            
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            fh.setFormatter(formatter)
            logger.addHandler(fh)
            
            cls._loggers[category] = logger
        
        return cls._loggers[category]


def log_fetch(msg: str, level: str = "info"):
    """抓取日志"""
    logger = ModuleLogger.get_logger("fetch")
    getattr(logger, level)(msg)


def log_compute(msg: str, level: str = "info"):
    """计算日志"""
    logger = ModuleLogger.get_logger("compute")
    getattr(logger, level)(msg)


def log_ai(msg: str, level: str = "info"):
    """AI日志"""
    logger = ModuleLogger.get_logger("ai")
    getattr(logger, level)(msg)


def log_ui(msg: str, level: str = "info"):
    """界面日志"""
    logger = ModuleLogger.get_logger("ui")
    getattr(logger, level)(msg)


def log_error(module: str, error: Exception, context: str = ""):
    """报错精准定位"""
    logger = ModuleLogger.get_logger("error")
    logger.error(f"[{module}] {context}: {error}")
    logger.error(traceback.format_exc())


# ========== 开机自检 ==========

def run_startup_check() -> dict:
    """开机自检：网络、数据源、数据库完整性"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "overall": "pass",
        "warnings": [],
        "errors": [],
    }
    
    # 1. 网络检查
    try:
        import urllib.request
        urllib.request.urlopen("https://www.baidu.com", timeout=5)
        results["checks"]["network"] = "pass"
    except Exception as e:
        results["checks"]["network"] = "fail"
        results["errors"].append(f"网络连接失败: {e}")
        results["overall"] = "warning"
    
    # 2. 数据源检查
    try:
        import akshare as ak
        results["checks"]["akshare"] = "pass"
    except ImportError:
        results["checks"]["akshare"] = "fail"
        results["errors"].append("AKShare未安装，港股数据将不可用")
        results["overall"] = "warning"
    
    # 3. 数据库完整性检查
    try:
        db_path = os.path.join(MODULE_DIR, "app.db")
        if os.path.exists(db_path):
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA integrity_check")
            conn.close()
            results["checks"]["database"] = "pass"
        else:
            results["checks"]["database"] = "warning"
            results["warnings"].append("数据库文件不存在，首次运行会自动创建")
    except Exception as e:
        results["checks"]["database"] = "fail"
        results["errors"].append(f"数据库检查失败: {e}")
    
    # 4. 数据目录检查
    if os.path.exists(DATA_DIR):
        results["checks"]["data_dir"] = "pass"
    else:
        os.makedirs(DATA_DIR, exist_ok=True)
        results["checks"]["data_dir"] = "warning"
        results["warnings"].append("Data目录已自动创建")
    
    # 5. AI接口检查
    try:
        from modules.ai_analyzer import get_ai_status
        ai_status = get_ai_status()
        if ai_status["offline_mode"]:
            results["checks"]["ai"] = "offline"
            results["warnings"].append("AI处于离线模式，将使用本地指标分析")
        elif ai_status["primary_available"]:
            results["checks"]["ai"] = "pass"
        else:
            results["checks"]["ai"] = "warning"
            results["warnings"].append("AI接口不可用，已自动切换离线模式")
    except Exception as e:
        results["checks"]["ai"] = "offline"
        results["warnings"].append(f"AI模块检查失败: {e}")
    
    # 6. 内存检查
    try:
        import psutil
        mem = psutil.virtual_memory()
        if mem.percent > 80:
            results["checks"]["memory"] = "warning"
            results["warnings"].append(f"内存使用率较高({mem.percent}%)，建议关闭其他应用")
        else:
            results["checks"]["memory"] = "pass"
    except ImportError:
        results["checks"]["memory"] = "pass"
        results["warnings"].append("psutil未安装，跳过内存检查")
    
    # 7. 新增功能模块检查
    module_files = [
        "modules/db_manager.py",
        "modules/auto_fetcher.py",
        "modules/indicator_engine.py",
        "modules/decision_engine.py",
        "modules/ai_analyzer.py",
        "modules/sim_executor.py",
    ]
    missing = [m for m in module_files if not os.path.exists(os.path.join(MODULE_DIR, m))]
    if missing:
        results["checks"]["modules"] = "warning"
        results["warnings"].append(f"模块文件缺失: {missing}")
    else:
        results["checks"]["modules"] = "pass"
    
    # 保存自检结果
    os.makedirs(LOG_DIR, exist_ok=True)
    check_file = os.path.join(LOG_DIR, f"startup_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(check_file, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    log_fetch(f"开机自检完成: {results['overall']}")
    return results


def get_latest_check() -> dict:
    """获取最近一次自检结果"""
    import glob
    checks = sorted(glob.glob(os.path.join(LOG_DIR, "startup_check_*.json")), reverse=True)
    if checks:
        with open(checks[0]) as f:
            return json.load(f)
    return {"error": "无自检记录"}


# ========== 内存监控 ==========

def check_memory_usage():
    """内存过高提醒"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        sys_mem = psutil.virtual_memory()
        
        return {
            "process_memory_mb": round(mem_info.rss / 1024 / 1024, 2),
            "system_memory_pct": sys_mem.percent,
            "warning": sys_mem.percent > 80,
            "message": "内存使用率较高，建议关闭其他应用" if sys_mem.percent > 80 else "内存使用正常",
        }
    except ImportError:
        return {"warning": False, "message": "psutil未安装，无法监控内存"}


def check_data_redundancy():
    """数据冗余优化提醒"""
    data_size = 0
    file_count = 0
    if os.path.exists(DATA_DIR):
        for root, dirs, files in os.walk(DATA_DIR):
            for f in files:
                fp = os.path.join(root, f)
                data_size += os.path.getsize(fp)
                file_count += 1
    
    size_mb = round(data_size / 1024 / 1024, 2)
    return {
        "data_size_mb": size_mb,
        "file_count": file_count,
        "warning": size_mb > 500,
        "message": f"数据文件共{file_count}个，占用{size_mb}MB" + 
                   ("，建议清理旧数据" if size_mb > 500 else ""),
    }


# ========== AI降级兜底 ==========

def ensure_ai_fallback():
    """确保AI离线降级兜底"""
    try:
        from modules.ai_analyzer import get_ai_status, set_offline_mode
        status = get_ai_status()
        
        if not status["primary_available"] and not status["fallback_available"]:
            set_offline_mode(True)
            log_ai("AI接口全部不可用，已自动切换离线模式")
            return {"ai_mode": "offline", "reason": "AI接口不可用"}
        
        return {"ai_mode": status["offline_mode"] and "offline" or "online", "reason": "正常"}
    except Exception as e:
        log_error("ai", e, "AI降级检查失败")
        return {"ai_mode": "offline", "reason": str(e)}


# ========== 新增功能总开关 ==========

_global_toggle = True  # 默认开启


def is_module_enabled():
    """检查新增功能是否开启"""
    return _global_toggle


def toggle_modules(enabled: bool):
    """一键开关全部新增功能"""
    global _global_toggle
    _global_toggle = enabled
    log_ui(f"新增功能已{'开启' if enabled else '关闭'}")
    return {"enabled": enabled}


# 初始化
def init_module():
    """模块8初始化"""
    log_fetch("模块8启动自检初始化完成")
    ensure_ai_fallback()