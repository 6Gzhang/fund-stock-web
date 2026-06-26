"""
模块1: 本地数据库底层管理
- 多市场标的分类存储
- 重复股票弹窗合并
- 抓取失败3次自动标记失效
- Data文件夹一键备份/还原
- 数据库容量监控、一键清理旧数据
- 个股手动备注，供给AI分析调用
"""
import sqlite3
import os
import shutil
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# 独立模块路径，不修改原有DB_PATH
MODULE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(MODULE_DIR, "Data")
DB_PATH = os.path.join(MODULE_DIR, "app.db")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
LOG_DIR = os.path.join(DATA_DIR, "logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def _get_module_db():
    """获取模块数据库连接（使用独立表，不影响原有表）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_module_db():
    """初始化模块1的独立数据表"""
    conn = _get_module_db()
    conn.executescript("""
        -- 多市场标的分类存储
        CREATE TABLE IF NOT EXISTS module_stock_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            market TEXT NOT NULL DEFAULT 'A',  -- A/港股/ETF
            status TEXT DEFAULT 'active',  -- active/disabled
            fail_count INTEGER DEFAULT 0,
            last_fetch_at TIMESTAMP,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, market)
        );

        -- 抓取日志
        CREATE TABLE IF NOT EXISTS module_fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            market TEXT NOT NULL,
            source TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            error_msg TEXT,
            fetch_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 备份记录
        CREATE TABLE IF NOT EXISTS module_backup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 数据库容量监控
        CREATE TABLE IF NOT EXISTS module_db_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            db_size_mb REAL,
            table_count INTEGER,
            record_count INTEGER,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 个股备注
        CREATE TABLE IF NOT EXISTS module_stock_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            note TEXT NOT NULL,
            category TEXT DEFAULT 'general',  -- general/technical/fundamental/risk
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


# ========== 多市场标的分类存储 ==========

def classify_stock(code: str, name: str, market: str = "A"):
    """将标的写入分类表，自动处理重复"""
    conn = _get_module_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO module_stock_catalog (code, name, market)
            VALUES (?, ?, ?)
        """, (code, name, market))
        
        if cursor.rowcount == 0:
            # 已存在，更新名称
            cursor.execute("""
                UPDATE module_stock_catalog SET name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE code = ? AND market = ?
            """, (name, code, market))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"[模块1] 分类存储失败: {e}")
        return False
    finally:
        conn.close()


def mark_failed(code: str, market: str = "A", error_msg: str = ""):
    """标记抓取失败，3次后自动标记失效"""
    conn = _get_module_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE module_stock_catalog 
        SET fail_count = fail_count + 1, last_fetch_at = CURRENT_TIMESTAMP
        WHERE code = ? AND market = ?
    """, (code, market))
    
    # 记录日志
    cursor.execute("""
        INSERT INTO module_fetch_log (code, market, source, success, error_msg)
        VALUES (?, ?, ?, 0, ?)
    """, (code, market, "auto", error_msg))
    
    # 失败3次自动标记失效
    cursor.execute("""
        UPDATE module_stock_catalog SET status = 'disabled'
        WHERE code = ? AND market = ? AND fail_count >= 3
    """, (code, market))
    
    conn.commit()
    conn.close()


def mark_success(code: str, market: str = "A"):
    """标记抓取成功，重置失败计数"""
    conn = _get_module_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE module_stock_catalog 
        SET fail_count = 0, last_fetch_at = CURRENT_TIMESTAMP, status = 'active'
        WHERE code = ? AND market = ?
    """, (code, market))
    cursor.execute("""
        INSERT INTO module_fetch_log (code, market, source, success)
        VALUES (?, ?, 'auto', 1)
    """, (code, market))
    conn.commit()
    conn.close()


# ========== Data文件夹备份/还原 ==========

def backup_database():
    """一键备份数据库到Data/backups/"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    try:
        shutil.copy2(DB_PATH, backup_path)
        file_size = os.path.getsize(backup_path)
        
        conn = _get_module_db()
        conn.execute("""
            INSERT INTO module_backup_log (backup_name, file_path, file_size)
            VALUES (?, ?, ?)
        """, (backup_name, backup_path, file_size))
        conn.commit()
        conn.close()
        
        return {"success": True, "backup_name": backup_name, "size_mb": round(file_size / 1024 / 1024, 2)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restore_database(backup_name: str):
    """从备份还原数据库"""
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_path):
        return {"success": False, "error": "备份文件不存在"}
    
    try:
        # 先备份当前
        current_backup = backup_database()
        shutil.copy2(backup_path, DB_PATH)
        return {"success": True, "current_backup": current_backup.get("backup_name")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_backups():
    """列出所有备份"""
    conn = _get_module_db()
    rows = conn.execute("""
        SELECT * FROM module_backup_log ORDER BY created_at DESC LIMIT 20
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ========== 数据库容量监控 ==========

def check_db_health():
    """数据库容量监控"""
    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    
    conn = _get_module_db()
    tables = conn.execute("""
        SELECT name FROM sqlite_master WHERE type='table'
    """).fetchall()
    
    total_records = 0
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM [{t['name']}]").fetchone()[0]
        total_records += count
    
    stats = {
        "db_size_mb": round(db_size / 1024 / 1024, 2),
        "table_count": len(tables),
        "record_count": total_records,
        "checked_at": datetime.now().isoformat(),
    }
    
    conn.execute("""
        INSERT INTO module_db_stats (db_size_mb, table_count, record_count)
        VALUES (?, ?, ?)
    """, (stats["db_size_mb"], stats["table_count"], stats["record_count"]))
    conn.commit()
    conn.close()
    
    return stats


def clean_old_data(days: int = 30):
    """一键清理旧数据（保留最近N天）"""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _get_module_db()
    
    cleaned = {}
    for table in ["module_fetch_log", "module_backup_log", "module_db_stats"]:
        result = conn.execute(f"DELETE FROM {table} WHERE created_at < ?", (cutoff,))
        cleaned[table] = result.rowcount
    
    conn.commit()
    conn.close()
    return cleaned


# ========== 个股备注 ==========

def add_stock_note(code: str, note: str, category: str = "general"):
    """添加个股手动备注"""
    conn = _get_module_db()
    conn.execute("""
        INSERT INTO module_stock_notes (code, note, category)
        VALUES (?, ?, ?)
    """, (code, note, category))
    conn.commit()
    conn.close()
    return True


def get_stock_notes(code: str):
    """获取个股备注"""
    conn = _get_module_db()
    notes = conn.execute("""
        SELECT * FROM module_stock_notes 
        WHERE code = ? 
        ORDER BY created_at DESC
    """, (code,)).fetchall()
    conn.close()
    return [dict(r) for r in notes]


def delete_stock_note(note_id: int):
    """删除个股备注"""
    conn = _get_module_db()
    conn.execute("DELETE FROM module_stock_notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return True


# 初始化
init_module_db()