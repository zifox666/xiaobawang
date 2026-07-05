from sqlalchemy import BigInteger, DateTime, Integer, create_engine, MetaData

def migrate():
    sqlite_url = 'sqlite:///./data/xiaobawang.db'
    pg_url = 'postgresql+psycopg://postgres:123456!@localhost:5432/xiaobawang'

    # 读取 SQLite
    src = create_engine(sqlite_url)
    meta = MetaData()
    meta.reflect(bind=src)

    # SQLite 类型 → Pg 兼容类型转换
    for table in meta.sorted_tables:
        for col in table.columns:
            # INTEGER → BIGINT（防止 EVE ID 溢出）
            if isinstance(col.type, Integer) and not isinstance(col.type, BigInteger):
                col.type = BigInteger()
            # DATETIME → TIMESTAMP（Pg 没有 DATETIME 类型）
            if isinstance(col.type, DateTime):
                col.type = DateTime()

    # 删除旧表后重建（确保列类型正确）
    dst = create_engine(pg_url)
    meta.drop_all(bind=dst)
    meta.create_all(bind=dst)

    # 逐表迁移数据
    for table in meta.sorted_tables:
        print(f'迁移表: {table.name}...')
        if table.name == 'alembic_version':
            print('  -> 跳过 alembic_version 表')
            continue
        with src.connect() as conn:
            rows = conn.execute(table.select()).fetchall()
        if rows:
            with dst.begin() as conn:
                conn.execute(table.insert(), [dict(row._mapping) for row in rows])
        print(f'  -> {len(rows)} 行')

    src.dispose()
    dst.dispose()
    print('迁移完成！')

migrate()