#!/bin/bash

# --- 1. Configuration ---
PYTHON_BIN="python3"
PIP_BIN="pip3"
BOT_FILE="bot.py"
REQUIREMENTS="requirements.txt"

RESTART_WAIT=2			# Seconds to wait before restarting
MAX_CRASHES=2			# Max failures allowed...
CRASH_WINDOW=60			# ...within this many seconds


# --- 2. Internal Setup ---
APP_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
BOT_PATH="$APP_DIR/$BOT_FILE"
REQ_PATH="$APP_DIR/$REQUIREMENTS"
CRASH_TS=()

# Colors for terminal output
RED='\e[1;31m'
GRN='\e[1;32m'
YLW='\e[1;33m'
CYN='\e[1;36m'
RES='\e[0m'


# --- 3. Functions ---
log() {
	echo -e "${CYN}[$(date '%H:%M:%S')]${RES} ${GRN}[INFO   ]${RES} exec.sh: $1"
}

warn() {
	echo -e "${CYN}[$(date '%H:%M:%S')]${RES} ${YLW}[WARNING]${RES} exec.sh: $1"
}

error() {
	echo -e "${CYN}[$(date '%H:%M:%S')]${RES} ${RED}[ERROR  ]${RES} exec.sh: $1" >&2
}

check_env() {
	if ! command -v "$PYTHON_BIN" &> /dev/null; then
		error "Python not found: $PYTHON_BIN"
		exit 1
	fi

	if ! command -v "$PIP_BIN" &> /dev/null; then
		error "Pip not found: $PIP_BIN"
		exit 1
	fi

	if [[ ! -f "$BOT_PATH" ]]; then
		error "Bot script not found: $BOT_PATH"
		exit 1
	fi
}

install_deps() {
	if [[ -f "$REQ_PATH" ]]; then
		log "Checking dependencies..."
		if ! "$PIP_BIN" install -r "$REQ_PATH" --quiet; then
			warn "Dependency installation failed. Attempting to run anyway."
		fi
	fi
}

is_crash_looping() {
	local now=$(date +%s)
	local cutoff=$((now - CRASH_WINDOW))
	
	local updated_ts=()
	for ts in "${CRASH_TS[@]}"; do
		[[ "$ts" -gt "$cutoff" ]] && updated_ts+=("$ts")
	done
	
	updated_ts+=("$now")
	CRASH_TS=("${updated_ts[@]}")

	if [[ ${#CRASH_TS[@]} -ge $MAX_CRASHES ]]; then
		return 0 # True
	fi
	return 1 # False
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


# --- 4. Main Execution ---
trap "log 'Manual interruption detected. Exiting...'; exit 0" SIGINT SIGTERM

if [[ "$1" == "--docker" ]]; then
	run_docker
fi

check_env
install_deps

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
