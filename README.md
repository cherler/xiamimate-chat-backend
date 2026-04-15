# XiaMimate Chat Backend

这个仓库是 XiaMimate 拆分迁移 Phase 4 的 `chat_backend` 子项目骨架。

当前状态：

- 创建时间：2026-04-15
- 来源：从旧基线 `/path/to/xiamimate` 复制最小运行集
- 当前用途：正式承接 chat backend 运行
- 默认正式端口：`8200`

当前已迁入内容：

- `data_platform/api/chat_backend.py`
- `data_platform/llm_client.py`
- `scripts/manage_chat_backend.sh`
- `scripts/smoke_test_chat_backend.sh`
- `postgres/migrations/app/`
- `postgres/init_app_tables.sql`

边界说明：

1. 本仓拥有 `app.*` 表和 chat backend 的用户、积分、订单、订阅、会话、分析运行等业务逻辑。
2. `serving.*` 仍由 `xiamimate-theme-api` 负责，本仓只通过 HTTP 代理调用 Theme API。
3. 当前继续复用同一套 PostgreSQL，并优先复用共享运行时根目录 `/path/to/xiamimate-runtime` 的 Python 环境。

推荐启动方式：

1. 复制 `.env.example` 为本地 `.env`。
2. 至少填写：
   - `XIAMIMATE_RUNTIME_ROOT`
   - `XIAMIMATE_PYTHON_BIN`
   - `PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASSWORD`
   - `CHAT_BACKEND_SERVICE_SECRET`
3. 用正式端口启动：
   - `bash scripts/manage_chat_backend.sh start`
4. 跑 smoke test：
   - `bash scripts/smoke_test_chat_backend.sh`

PostgreSQL DDL：

- `postgres/migrations/app/` 是当前 `app.*` 层拆分后的 source-of-truth。
- `postgres/init_app_tables.sql` 是兼容入口，由 `bash postgres/scripts/rebuild_init_app_tables.sh` 生成。

架构与安全设计：

- `docs/chat_backend-模块边界与P0安全整改-2026-04-15.md` 给出当前推荐的模块边界拆分方案，以及 API Key、身份边界、计费链路的 P0 安全整改顺序。

当前补充说明：

1. 本仓已承接正式 `8200` 运行，旧 shadow `18200` 不再作为当前主路径说明。
2. 旧仓路径目前仅保留兼容 symlink，正式运行应以 shared runtime 路径为准。