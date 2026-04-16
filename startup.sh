#!/usr/bin/env bash
# ── Vexor BCN — Startup Script ──────────────────────────────────────────
# Starts both backend (FastAPI/uvicorn) and frontend (Vite) dev servers.
# Usage:
#   ./startup.sh          Start both backend + frontend
#   ./startup.sh backend  Start backend only
#   ./startup.sh frontend Start frontend only
#   ./startup.sh --kill   Stop all running Vexor processes
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
PID_DIR="$ROOT/.pids"

BACKEND_PORT=8000
FRONTEND_PORT=5173

# ── Colors ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

log()  { echo -e "${CYAN}[vexor]${RESET} $1"; }
ok()   { echo -e "${GREEN}[vexor]${RESET} $1"; }
warn() { echo -e "${YELLOW}[vexor]${RESET} $1"; }
err()  { echo -e "${RED}[vexor]${RESET} $1" >&2; }

# ── Helpers ──────────────────────────────────────────────────────────────

check_port() {
    local port=$1 name=$2
    if lsof -i :"$port" -sTCP:LISTEN -t &>/dev/null; then
        local pid
        pid=$(lsof -i :"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)
        warn "Port $port ($name) already in use by PID $pid"
        return 1
    fi
    return 0
}

kill_procs() {
    log "Stopping Vexor processes..."
    local killed=0

    # Kill by PID files
    if [[ -d "$PID_DIR" ]]; then
        for pidfile in "$PID_DIR"/*.pid; do
            [[ -f "$pidfile" ]] || continue
            local pid
            pid=$(<"$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null && killed=$((killed + 1))
                log "  Stopped $(basename "$pidfile" .pid) (PID $pid)"
            fi
            rm -f "$pidfile"
        done
    fi

    # Kill anything still on our ports
    for port in $BACKEND_PORT $FRONTEND_PORT; do
        local pids
        pids=$(lsof -i :"$port" -sTCP:LISTEN -t 2>/dev/null || true)
        for pid in $pids; do
            kill "$pid" 2>/dev/null && killed=$((killed + 1))
            log "  Killed process on port $port (PID $pid)"
        done
    done

    if [[ $killed -eq 0 ]]; then
        log "Nothing to stop."
    else
        ok "Stopped $killed process(es)."
    fi
    rm -rf "$PID_DIR"
}

wait_for_port() {
    local port=$1 name=$2 timeout=30 elapsed=0
    while ! lsof -i :"$port" -sTCP:LISTEN -t &>/dev/null; do
        sleep 0.5
        elapsed=$((elapsed + 1))
        if [[ $elapsed -ge $((timeout * 2)) ]]; then
            err "$name failed to start on port $port within ${timeout}s"
            return 1
        fi
    done
}

# ── Backend ──────────────────────────────────────────────────────────────

start_backend() {
    log "Starting backend..."

    # Check .env
    if [[ ! -f "$BACKEND_DIR/.env" ]]; then
        warn "No .env found — copying from .env.example"
        if [[ -f "$BACKEND_DIR/.env.example" ]]; then
            cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
            warn "Edit ${DIM}backend/.env${RESET}${YELLOW} with your API keys"
        else
            err "No .env.example either — create backend/.env manually"
            return 1
        fi
    fi

    # Sync deps
    log "  Syncing Python dependencies..."
    (cd "$BACKEND_DIR" && uv sync --quiet)

    # Check port
    if ! check_port $BACKEND_PORT "backend"; then
        warn "Skipping backend — kill it first or run: ./startup.sh --kill"
        return 1
    fi

    # Launch
    mkdir -p "$PID_DIR"
    (cd "$BACKEND_DIR" && uv run uvicorn app.main:app \
        --host 0.0.0.0 \
        --port $BACKEND_PORT \
        --reload \
        --log-level info) &
    echo $! > "$PID_DIR/backend.pid"

    wait_for_port $BACKEND_PORT "Backend"
    ok "Backend running  ${DIM}http://localhost:${BACKEND_PORT}${RESET}"
    ok "  API docs       ${DIM}http://localhost:${BACKEND_PORT}/docs${RESET}"
}

# ── Frontend ─────────────────────────────────────────────────────────────

start_frontend() {
    log "Starting frontend..."

    # Install deps if needed
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        log "  Installing npm dependencies..."
        (cd "$FRONTEND_DIR" && npm install --silent)
    fi

    # Check port
    if ! check_port $FRONTEND_PORT "frontend"; then
        warn "Skipping frontend — kill it first or run: ./startup.sh --kill"
        return 1
    fi

    # Launch
    mkdir -p "$PID_DIR"
    (cd "$FRONTEND_DIR" && npm run dev -- --host 0.0.0.0) &
    echo $! > "$PID_DIR/frontend.pid"

    wait_for_port $FRONTEND_PORT "Frontend"
    ok "Frontend running ${DIM}http://localhost:${FRONTEND_PORT}${RESET}"
}

# ── Cleanup on exit ──────────────────────────────────────────────────────

cleanup() {
    log "Shutting down..."
    kill_procs
}

# ── Main ─────────────────────────────────────────────────────────────────

banner() {
    echo ""
    echo -e "${BOLD}${CYAN}"
    echo "  ╦  ╦┌─┐─┐ ┬┌─┐┬─┐  ╔╗ ╔═╗╔╗╔"
    echo "  ╚╗╔╝├┤ ┌┴┬┘│ │├┬┘  ╠╩╗║  ║║║"
    echo "   ╚╝ └─┘┴ └─└─┘┴└─  ╚═╝╚═╝╝╚╝"
    echo -e "${RESET}"
    echo -e "  ${DIM}OSINT Enrichment Pipeline${RESET}"
    echo ""
}

main() {
    local target="${1:-all}"

    case "$target" in
        --kill|-k|kill|stop)
            kill_procs
            exit 0
            ;;
        backend|back|api)
            banner
            trap cleanup EXIT INT TERM
            start_backend
            log ""
            log "Press ${BOLD}Ctrl+C${RESET} to stop."
            wait
            ;;
        frontend|front|ui)
            banner
            trap cleanup EXIT INT TERM
            start_frontend
            log ""
            log "Press ${BOLD}Ctrl+C${RESET} to stop."
            wait
            ;;
        all|"")
            banner
            trap cleanup EXIT INT TERM
            start_backend
            start_frontend
            echo ""
            echo -e "  ${GREEN}${BOLD}Ready.${RESET}"
            echo ""
            echo -e "  ${DIM}Backend  ${RESET} http://localhost:${BACKEND_PORT}"
            echo -e "  ${DIM}Frontend ${RESET} http://localhost:${FRONTEND_PORT}"
            echo -e "  ${DIM}API Docs ${RESET} http://localhost:${BACKEND_PORT}/docs"
            echo ""
            log "Press ${BOLD}Ctrl+C${RESET} to stop both."
            wait
            ;;
        *)
            err "Unknown target: $target"
            echo "Usage: ./startup.sh [backend|frontend|--kill]"
            exit 1
            ;;
    esac
}

main "$@"
