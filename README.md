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

当前新增能力：

1. 新增 `GET /v1/me/account-overview`，用于统一查看用户余额、最近账本、usage 汇总、订单、订阅、会话与运行记录。
2. 新增 `POST /internal/identity/exchange-webui-user`，供 Open WebUI / Pipelines 以内部服务身份交换用户上下文，不再依赖公开接口返回 raw key。
3. 新增内置后台页面 `GET /admin/backoffice`，配套 `GET /admin/api/*` 与 `POST /admin/api/users/{user_id}/grant-points`。
4. 支持 guest 日配额：通过 `CHAT_BACKEND_GUEST_DAILY_USERNAMES` 和 `CHAT_BACKEND_GUEST_DAILY_POINTS` 控制，默认对 `guest` 账号每日重置到 `500` 积分。

建议新增环境变量：

1. `CHAT_BACKEND_ADMIN_TOKEN`：后台 Bearer token，没有这个值时后台 API 不可用。
2. `CHAT_BACKEND_GUEST_DAILY_USERNAMES`：按逗号分隔的 guest 账号别名，默认 `guest`。
3. `CHAT_BACKEND_GUEST_DAILY_POINTS`：guest 每日积分上限，默认 `500`。
4. `CHAT_BACKEND_DAILY_RESET_TIMEZONE`：日配额重置时区，默认 `Asia/Shanghai`。
5. `CHAT_BACKEND_DISABLE_DEMO_FALLBACK`：设为 `true` 后，public API 不再接受 demo fallback 用户。
6. `DIFY_CHATBOT_TOKEN`：portal 右下角 bubble 使用的 Dify chatbot token/share code；切换 chatbot 时只改这个值即可，无需改代码。
7. `AGENT_OPENAI_*`：DeepSeek-V4-Pro 这条 OpenAI-compatible 线路的上游配置。
8. `AGENT_OPENAI_APIYI_*`：API易 GPT-5.5 这条 OpenAI Chat Completions-compatible profile 的上游配置；bridge 选择 GPT-5.5 profile 时会走这组参数。
9. `AGENT_ANTHROPIC_*`：MiniMax-M2.7 这条 Anthropic-compatible 线路的上游配置；bridge 选择 MiniMax profile 时会走这组参数。
