#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/load_chat_backend_env.sh
source "$ROOT_DIR/scripts/load_chat_backend_env.sh"
PYTHON_BIN="${XIAMIMATE_PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/chat_backend.pid"
LOG_FILE="$LOG_DIR/chat_backend.log"
HOST="${CHAT_BACKEND_HOST:-0.0.0.0}"
PORT="${CHAT_BACKEND_PORT:-18200}"

mkdir -p "$LOG_DIR"

cleanup_metadata() {
    rm -f "$PID_FILE"
}

wait_for_shutdown() {
    local pid="$1"
    local attempts="${2:-50}"
    local interval_seconds="${3:-0.2}"
    local attempt=0

    while kill -0 "$pid" 2>/dev/null; do
        if (( attempt >= attempts )); then
            return 1
        fi
        sleep "$interval_seconds"
        attempt=$((attempt + 1))
    done

    return 0
}

resolve_pid() {
    local pid

    if [[ -f "$PID_FILE" ]]; then
        pid="$(cat "$PID_FILE")"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi

    pid="$(lsof -ti:"$PORT" 2>/dev/null | head -n 1 || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        echo "$pid" > "$PID_FILE"
        echo "$pid"
        return 0
    fi

    return 1
}

is_running() {
    resolve_pid >/dev/null 2>&1
}

preview_backend() {
    echo "python_bin=$PYTHON_BIN"
    echo "host=$HOST"
    echo "port=$PORT"
    echo "log_file=$LOG_FILE"
    echo "command=$PYTHON_BIN -m uvicorn data_platform.api.chat_backend:app --host $HOST --port $PORT"
}

start_backend() {
    if [[ ! -x "$PYTHON_BIN" ]]; then
        echo "python not found: $PYTHON_BIN"
        return 1
    fi

    if is_running; then
        echo "chat backend already running: PID $(resolve_pid)  http://${HOST}:${PORT}"
        return 0
    fi

    cleanup_metadata
    nohup "$PYTHON_BIN" -m uvicorn data_platform.api.chat_backend:app \
        --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    local attempt=0
    while (( attempt < 30 )); do
        if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
            echo "chat backend started: PID $(cat "$PID_FILE")  http://${HOST}:${PORT}"
            echo "log file: $LOG_FILE"
            return 0
        fi
        sleep 0.5
        attempt=$((attempt + 1))
    done

    echo "chat backend may have failed to start; check log: $LOG_FILE"
    return 1
}

stop_backend() {
    if ! is_running; then
        cleanup_metadata
        echo "chat backend is not running"
        return 0
    fi

    local pid
    pid="$(resolve_pid)"
    kill "$pid" 2>/dev/null || true
    if ! wait_for_shutdown "$pid"; then
        echo "chat backend did not stop gracefully; forcing kill: PID $pid"
        kill -9 "$pid" 2>/dev/null || true
        if ! wait_for_shutdown "$pid" 25 0.2; then
            echo "failed to stop chat backend: PID $pid"
            return 1
        fi
    fi

    cleanup_metadata
    echo "chat backend stopped: PID $pid"
}

status_backend() {
    if is_running; then
        local pid
        pid="$(resolve_pid)"
        echo "chat backend running: PID $pid  http://${HOST}:${PORT}"
        echo "log file: $LOG_FILE"
        if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
            echo "health check: OK"
        else
            echo "health check: FAILED"
        fi
    else
        echo "chat backend is not running"
        return 1
    fi
}

restart_backend() {
    stop_backend || true
    start_backend
}

show_logs() {
    local lines="${2:-50}"
    if [[ ! -f "$LOG_FILE" ]]; then
        echo "log file does not exist yet: $LOG_FILE"
        return 1
    fi
    tail -n "$lines" "$LOG_FILE"
}

case "${1:-}" in
    start)
        start_backend
        ;;
    stop)
        stop_backend
        ;;
    restart)
        restart_backend
        ;;
    status)
        status_backend
        ;;
    logs)
        show_logs "$@"
        ;;
        preview)
                preview_backend
                ;;
    *)
        cat <<EOF
Usage: bash scripts/manage_chat_backend.sh {start|stop|restart|status|logs|preview}

Commands:
    start    启动 chat backend（默认 0.0.0.0:18200，供 phase 4 影子验证）
  stop     停止 chat backend
  restart  重启 chat backend
  status   查看运行状态 + 健康检查
  logs     查看最近日志（可选：logs 100）
    preview  仅打印解析后的启动命令与端口
EOF
        exit 1
        ;;
esac