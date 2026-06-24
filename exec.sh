#!/bin/bash
set -u

# --- 1. Configuration ---
PYTHON_BIN="python3"
PIP_BIN="pip3"
BOT_FILE="bot.py"
REQUIREMENTS="requirements.txt"

RESTART_WAIT=2
MAX_CRASHES=2
CRASH_WINDOW=60

# Default behavior flags
SUPERVISE=false
INSTALL_DEPS=false
CHECK_ENV=false

# --- 2. Internal Setup ---
APP_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
BOT_PATH="$APP_DIR/$BOT_FILE"
REQ_PATH="$APP_DIR/$REQUIREMENTS"
CRASH_TS=()

RED='\e[1;31m'
GRN='\e[1;32m'
YLW='\e[1;33m'
CYN='\e[1;36m'
MAG='\e[1;35m'
RES='\e[0m'

# --- 3. Functions ---
log() {
	echo -e "${CYN}$(date '+%H:%M:%S')${RES} ${GRN}I${RES} exec.sh: $1"
}

warn() {
	echo -e "${CYN}$(date '+%H:%M:%S')${RES} ${YLW}W${RES} exec.sh: $1"
}

error() {
	echo -e "${CYN}$(date '+%H:%M:%S')${RES} ${RED}E${RES} exec.sh: $1" >&2
}

show_help() {
	echo -e "${MAG}▶ Bot Executor${RES}"
	echo "Usage: $0 [OPTIONS]"
	echo ""
	echo "Options:"
	echo "  -s, --supervise     Enable auto-restart and crash monitoring loop"
	echo "  -i, --install       Check and install dependencies before running"
	echo "  -c, --check         Verify environment (Python, Pip, Script existence)"
	echo "  -d, --docker        Run using Docker Compose (detached)"
	echo "  -r, --restart N     Set restart wait time in seconds (default: 2)"
	echo "  -m, --max-crashes N Set max crashes allowed in window (default: 2)"
	echo "  -h, --help          Show this help message"
}

check_env() {
	log "Checking environment..."
	if ! command -v "$PYTHON_BIN" &> /dev/null; then
		error "Python not found: $PYTHON_BIN"
		exit 1
	fi

	if [[ "$INSTALL_DEPS" == true ]] && ! command -v "$PIP_BIN" &> /dev/null; then
		error "Pip not found: $PIP_BIN"
		exit 1
	fi

	if [[ ! -f "$BOT_PATH" ]]; then
		error "Bot script not found: $BOT_PATH"
		exit 1
	fi
	log "Environment OK."
}

install_deps() {
	if [[ -f "$REQ_PATH" ]]; then
		log "Checking/Installing dependencies..."
		if ! "$PIP_BIN" install -r "$REQ_PATH" --quiet; then
			warn "Dependency installation failed. Attempting to run anyway."
		fi
	else
		warn "No $REQUIREMENTS found."
	fi
}

is_crash_looping() {
	local now=$(date +%s)
	local cutoff=$((now - CRASH_WINDOW))
	
	local updated_ts=()
	for ts in "${CRASH_TS[@]}"; do
		if [[ "$ts" -gt "$cutoff" ]]; then
			updated_ts+=("$ts")
		fi
	done
	
	updated_ts+=("$now")
	CRASH_TS=("${updated_ts[@]}")

	if [[ ${#CRASH_TS[@]} -ge $MAX_CRASHES ]]; then
		return 0
	fi
	return 1
}

run_docker() {
	if ! command -v docker &> /dev/null; then
		error "Docker not found. Please install Docker first."
		exit 1
	fi
	
	log "Building and starting containers (detached)..."
	docker compose up --build -d
	log "Container is up. Use 'docker compose logs -f' to view output."
	exit 0
}

# --- 4. Parse Arguments ---
while [[ $# -gt 0 ]]; do
	case "$1" in
		-s|--supervise)
			SUPERVISE=true
			shift
			;;
		-i|--install)
			INSTALL_DEPS=true
			shift
			;;
		-c|--check)
			CHECK_ENV=true
			shift
			;;
		-d|--docker)
			run_docker
			;;
		-r|--restart)
			RESTART_WAIT="$2"
			shift 2
			;;
		-m|--max-crashes)
			MAX_CRASHES="$2"
			shift 2
			;;
		-h|--help)
			show_help
			exit 0
			;;
		*)
			error "Unknown option: $1"
			show_help
			exit 1
			;;
	esac
done

# --- 5. Main Execution ---
clear

trap "log 'Manual interruption detected. Exiting...'; exit 0" SIGINT SIGTERM

[[ "$CHECK_ENV" == true ]] && check_env
[[ "$INSTALL_DEPS" == true ]] && install_deps

if [[ "$SUPERVISE" == false ]]; then
	clear
	"$PYTHON_BIN" "$BOT_PATH"
	exit $?
fi

log "Supervisor active. Monitoring $BOT_FILE..."

while true; do
	"$PYTHON_BIN" "$BOT_PATH"
	EXIT_CODE=$?

	case $EXIT_CODE in
		0)
			log "Clean exit detected. Stopping."
			break
			;;
		10)
			log "Critical error. Exiting."
			break
			;;
		42)
			log "System requested immediate restart..."
			sleep 1
			;;
		130 | 143)
			log "Termination signal ($EXIT_CODE). Exiting."
			break
			;;
		*)
			error "Bot crashed with code $EXIT_CODE."
			
			if is_crash_looping; then
				error "FATAL: Reached $MAX_CRASHES crashes in ${CRASH_WINDOW}s. Manual intervention required."
				exit 1
			fi
			
			log "Restarting in ${RESTART_WAIT}s (Failure ${#CRASH_TS[@]}/$MAX_CRASHES)..."
			sleep "$RESTART_WAIT"
			;;
	esac
done
