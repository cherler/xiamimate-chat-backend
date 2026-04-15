# Chat Backend PostgreSQL DDL

本目录只保留 `chat_backend` 自身负责的 `app.*` migration。

当前结构：

- `migrations/app/001_create_app_schema.sql`
- `migrations/app/010_app_business_tables.sql`
- `migrations/app/020_app_indexes.sql`
- `init_app_tables.sql`

说明：

1. `init_app_tables.sql` 是兼容性入口，适合 phase 4 shadow 初始化时直接执行。
2. 真正的编辑入口是 `migrations/app/*.sql`。
3. 修改碎片 SQL 后，执行 `bash postgres/scripts/rebuild_init_app_tables.sh` 重建兼容入口。