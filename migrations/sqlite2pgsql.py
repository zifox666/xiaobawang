"""
SQLite → PostgreSQL 数据迁移脚本
===================================
前提：PostgreSQL 表结构已通过 nb orm upgrade 正确创建。
本脚本仅负责从 SQLite 读取数据并写入已存在的 Pg 表。
无需导入任何 ORM 模型，不依赖 NoneBot。
"""
from sqlalchemy import MetaData, create_engine

# 要迁移的表（排除 alembic 管理表）
SKIP_TABLES = {"alembic_version", "spatial_ref_sys"}


def migrate():
    sqlite_url = "sqlite:///./data/xiaobawang.db"
    pg_url = "postgresql+psycopg://postgres:123456!@host:5432/xiaobawang"

    src = create_engine(sqlite_url)
    dst = create_engine(pg_url)

    # 读取 SQLite 和 Pg 的表结构
    src_meta = MetaData()
    src_meta.reflect(bind=src)

    dst_meta = MetaData()
    dst_meta.reflect(bind=dst)

    # 只迁移两边都存在的表
    common_tables = set(src_meta.tables) & set(dst_meta.tables) - SKIP_TABLES

    for table_name in sorted(common_tables):
        src_table = src_meta.tables[table_name]
        dst_table = dst_meta.tables[table_name]

        print(f"迁移表: {table_name}...")

        with src.connect() as conn:
            rows = conn.execute(src_table.select()).fetchall()

        try:
            if rows:
                # 将行数据转为 dict，只取 Pg 表存在的列
                dst_columns = {c.name for c in dst_table.columns}
                data = [{k: v for k, v in dict(r._mapping).items() if k in dst_columns} for r in rows]

                with dst.begin() as conn:
                    conn.execute(dst_table.insert(), data)
        except Exception as e:
            print(f"  -> 迁移失败: {e}")
            continue

        print(f"  -> {len(rows)} 行")

    src.dispose()
    dst.dispose()
    print("\n迁移完成！")


migrate()