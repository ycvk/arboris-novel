#!/usr/bin/env python3
"""
数据库迁移脚本 - 自动检查并添加缺失的字段

此脚本在容器启动时自动运行，确保数据库结构与模型定义保持一致。
支持 SQLite 和 MySQL 两种数据库。
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_db_config():
    """从环境变量获取数据库配置"""
    db_provider = os.getenv('DB_PROVIDER', 'sqlite').lower()
    
    if db_provider == 'sqlite':
        db_path = os.getenv('SQLITE_DB_PATH', '/app/storage/arboris.db')
        return {
            'provider': 'sqlite',
            'path': db_path
        }
    elif db_provider == 'mysql':
        return {
            'provider': 'mysql',
            'host': os.getenv('MYSQL_HOST', 'db'),
            'port': int(os.getenv('MYSQL_PORT', '3306')),
            'database': os.getenv('MYSQL_DATABASE', 'arboris'),
            'user': os.getenv('MYSQL_USER', 'arboris'),
            'password': os.getenv('MYSQL_PASSWORD', '')
        }
    else:
        raise ValueError(f"不支持的数据库类型: {db_provider}")


def check_column_exists(cursor, table_name, column_name, db_provider):
    """检查表中是否存在指定的列"""
    if db_provider == 'sqlite':
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        return column_name in columns
    elif db_provider == 'mysql':
        cursor.execute(f"""
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = '{table_name}' 
            AND COLUMN_NAME = '{column_name}'
        """)
        return cursor.fetchone()[0] > 0
    return False


def add_metadata_column_sqlite(cursor):
    """为 SQLite 数据库添加 metadata 字段"""
    try:
        cursor.execute("ALTER TABLE novel_projects ADD COLUMN metadata TEXT")
        logger.info("✅ 成功添加 novel_projects.metadata 字段 (SQLite)")
        return True
    except Exception as e:
        if 'duplicate column name' in str(e).lower():
            logger.info("ℹ️  novel_projects.metadata 字段已存在 (SQLite)")
            return True
        else:
            logger.error(f"❌ 添加 novel_projects.metadata 字段失败 (SQLite): {e}")
            return False


def add_metadata_column_mysql(cursor):
    """为 MySQL 数据库添加 metadata 字段"""
    try:
        cursor.execute("ALTER TABLE novel_projects ADD COLUMN metadata JSON")
        logger.info("✅ 成功添加 novel_projects.metadata 字段 (MySQL)")
        return True
    except Exception as e:
        if 'duplicate column name' in str(e).lower() or "Duplicate column name" in str(e):
            logger.info("ℹ️  novel_projects.metadata 字段已存在 (MySQL)")
            return True
        else:
            logger.error(f"❌ 添加 novel_projects.metadata 字段失败 (MySQL): {e}")
            return False


def run_migrations_sqlite(db_path):
    """运行 SQLite 数据库迁移"""
    import sqlite3
    
    # 检查数据库文件是否存在
    if not os.path.exists(db_path):
        logger.warning(f"⚠️  数据库文件不存在: {db_path}")
        logger.info("ℹ️  数据库将在应用首次启动时自动创建")
        return True
    
    logger.info(f"🔍 检查 SQLite 数据库: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查 novel_projects 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='novel_projects'")
        if not cursor.fetchone():
            logger.info("ℹ️  novel_projects 表不存在，将在应用启动时自动创建")
            conn.close()
            return True
        
        # 检查并添加 metadata 字段
        if not check_column_exists(cursor, 'novel_projects', 'metadata', 'sqlite'):
            success = add_metadata_column_sqlite(cursor)
            if success:
                conn.commit()
        else:
            logger.info("ℹ️  novel_projects.metadata 字段已存在")
        
        conn.close()
        logger.info("✅ SQLite 数据库迁移完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ SQLite 数据库迁移失败: {e}")
        return False


def run_migrations_mysql(config):
    """运行 MySQL 数据库迁移"""
    try:
        import pymysql
    except ImportError:
        logger.error("❌ pymysql 模块未安装，无法连接 MySQL 数据库")
        return False
    
    logger.info(f"🔍 检查 MySQL 数据库: {config['host']}:{config['port']}/{config['database']}")
    
    try:
        conn = pymysql.connect(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            database=config['database']
        )
        cursor = conn.cursor()
        
        # 检查 novel_projects 表是否存在
        cursor.execute("SHOW TABLES LIKE 'novel_projects'")
        if not cursor.fetchone():
            logger.info("ℹ️  novel_projects 表不存在，将在应用启动时自动创建")
            conn.close()
            return True
        
        # 检查并添加 metadata 字段
        if not check_column_exists(cursor, 'novel_projects', 'metadata', 'mysql'):
            success = add_metadata_column_mysql(cursor)
            if success:
                conn.commit()
        else:
            logger.info("ℹ️  novel_projects.metadata 字段已存在")
        
        conn.close()
        logger.info("✅ MySQL 数据库迁移完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ MySQL 数据库迁移失败: {e}")
        return False


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始运行数据库迁移...")
    logger.info("=" * 60)
    
    try:
        config = get_db_config()
        logger.info(f"📊 数据库类型: {config['provider'].upper()}")
        
        if config['provider'] == 'sqlite':
            success = run_migrations_sqlite(config['path'])
        elif config['provider'] == 'mysql':
            success = run_migrations_mysql(config)
        else:
            logger.error(f"❌ 不支持的数据库类型: {config['provider']}")
            success = False
        
        if success:
            logger.info("=" * 60)
            logger.info("✅ 数据库迁移完成")
            logger.info("=" * 60)
            return 0
        else:
            logger.error("=" * 60)
            logger.error("❌ 数据库迁移失败")
            logger.error("=" * 60)
            return 1
            
    except Exception as e:
        logger.error(f"❌ 数据库迁移过程中发生错误: {e}")
        logger.error("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())

