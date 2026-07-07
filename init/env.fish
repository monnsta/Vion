#!/usr/bin/env fish

# --- 1. Configuration ---
set -g BOT_FILE "bot.py"
set -g REQUIREMENTS "requirements.txt"
set -g RESTART_WAIT 2
set -g MAX_CRASHES 2
set -g CRASH_WINDOW 60

set -gx ANDROID_API_LEVEL 34
set -gx PYO3_USE_ABI3_FORWARD_COMPATIBILITY 1
set -gx CARGO_BUILD_JOBS (command -v nproc >/dev/null && nproc 2>/dev/null; or echo 4)
set -gx CARGO_BUILD_TARGET (command -v rustc >/dev/null && rustc -Vv 2>/dev/null | grep host | cut -d ' ' -f 2; or echo "")

# --- 2. Internal Setup & OS Detection ---
set -g APP_DIR (realpath (dirname (status filename))/..)

set -g BOT_PATH "$APP_DIR/$BOT_FILE"
set -g REQ_PATH "$APP_DIR/$REQUIREMENTS"

set -g CRASH_TS

if contains $OS Windows_NT; or string match -q "*msys*" $OSTYPE; or string match -q "*cygwin*" $OSTYPE
    set -g PYTHON_VENV_BIN "$APP_DIR/.venv/Scripts/python.exe"
    set -g PIP_VENV_BIN "$APP_DIR/.venv/Scripts/pip.exe"
else
    set -g PYTHON_VENV_BIN "$APP_DIR/.venv/bin/python"
    set -g PIP_VENV_BIN "$APP_DIR/.venv/bin/pip"
end

# --- 3. Logging Functions ---
function _bot_get_ts
    echo -e "\033[2m"(date '+%H:%M:%S')"\033[0m"
end

function bot_log
    echo -e (_bot_get_ts)" \033[1;32mI\033[0m $argv"
end

function bot_warn
    echo -e (_bot_get_ts)" \033[1;33mW\033[0m $argv" >&2
end

function bot_error
    echo -e (_bot_get_ts)" \033[1;31mE\033[0m $argv" >&2
end

# --- 4. Core Utility Functions ---
function bot_clean
    bot_log "Cleaning Python cache files..."
    find "$APP_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
    find "$APP_DIR" -type f -name "*.pyc" -delete 2>/dev/null
    if test $status -ne 0
        bot_warn "Cache cleaning encountered some issues, but continued. Check permissions if files persist."
    else
        bot_log "Cache cleaned."
    end
end

function _bot_find_system_python
    set -l PYTHON_CANDIDATES python3 python
    set -l FOUND_PYTHON_CMD ""

    for cmd in $PYTHON_CANDIDATES
        if command -v "$cmd" >/dev/null 2>&1
            if $cmd -c "import venv" >/dev/null 2>&1
                set FOUND_PYTHON_CMD "$cmd"
                break
            else
                bot_warn "Python command '$cmd' found, but 'venv' module is missing. Skipping."
            end
        end
    end

    if test -z "$FOUND_PYTHON_CMD"
        bot_error "No suitable Python interpreter with 'venv' module found on your system."
        bot_error "Please install Python 3 and its 'venv' module (e.g., 'python3-venv' on Debian/Ubuntu, or ensure pip is installed)."
        return 1
    end

    echo "$FOUND_PYTHON_CMD"
    return 0
end

function bot_check
    bot_log "Checking environment..."

    if not test -f "$BOT_PATH"
        bot_error "Bot script not found: $BOT_PATH"
        bot_error "Please ensure '$BOT_FILE' exists in '$APP_DIR'."
        return 1
    end

    if not test -w "$APP_DIR"
        bot_error "Cannot write to application directory: $APP_DIR"
        bot_error "Please check directory permissions. The script needs write access to create the '.venv' directory."
        return 1
    end

    if not test -x "$PYTHON_VENV_BIN"
        bot_warn "Virtual environment not found or not executable. Attempting to create one..."

        set -l SYSTEM_PYTHON_CMD (_bot_find_system_python)
        if test $status -ne 0
            return 1
        end

        set -l VENV_ARGS -m venv "$APP_DIR/.venv"

        if string match -q "*com.termux*" "$PREFIX"
            bot_log "Termux detected: Enabling system site-packages for venv to link pre-installed native libraries."
            set -a VENV_ARGS --system-site-packages
        end

        bot_log "Attempting to create virtual environment using '$SYSTEM_PYTHON_CMD'..."
        if $SYSTEM_PYTHON_CMD $VENV_ARGS
            if test -x "$PYTHON_VENV_BIN"
                bot_log "Virtual environment created successfully at '$APP_DIR/.venv'."
            else
                bot_error "Virtual environment creation succeeded, but python executable not found at '$PYTHON_VENV_BIN'."
                bot_error "This might indicate a broken venv or platform mismatch. Please inspect '$APP_DIR/.venv'."
                return 1
            end
        else
            set -l VENV_STATUS $status
            bot_error "Failed to create virtual environment. System command exit code: $VENV_STATUS"
            bot_error "Please check the Python installation and ensure the 'venv' module is available."
            bot_error "Consider running: '$SYSTEM_PYTHON_CMD' -m venv '$APP_DIR/.venv' manually to debug."
            return 1
        end
    else
        bot_log "Virtual environment detected and executable."
        if not $PYTHON_VENV_BIN -c "import sys; print(sys.prefix)" | grep -q "$APP_DIR/.venv"
            bot_warn "Existing virtual environment's Python doesn't appear to be linked to '$APP_DIR/.venv'."
            bot_warn "Consider removing '$APP_DIR/.venv' and re-running 'bot_check' to recreate it."
        end
    end

    bot_log "Environment OK."
    return 0
end

function _bot_handle_termux_system_deps
    if string match -q "*com.termux*" "$PREFIX"
        bot_log "Termux detected: Scanning for hard-to-compile system dependencies required by Python packages."
        set -l SYS_PKGS_TO_INSTALL

        if test -f "$REQ_PATH"
            if grep -qi cryptography "$REQ_PATH" 2>/dev/null
                set -a SYS_PKGS_TO_INSTALL python-cryptography rust
            end
            if grep -qi pillow "$REQ_PATH" 2>/dev/null
                set -a SYS_PKGS_TO_INSTALL python-pillow
            end
            if grep -qi numpy "$REQ_PATH" 2>/dev/null
                set -a SYS_PKGS_TO_INSTALL python-numpy
            end
            # Add more as needed
        else
            bot_warn "No '$REQUIREMENTS' file found, skipping Termux system dependency scan."
            return 0
        end

        if test (count $SYS_PKGS_TO_INSTALL) -gt 0
            bot_warn "Installing pre-compiled system packages via 'pkg install': $SYS_PKGS_TO_INSTALL"
            if command -v pkg >/dev/null 2>&1
                if pkg install -y $SYS_PKGS_TO_INSTALL
                    bot_log "Termux system packages installed successfully."
                else
                    set -l PKG_STATUS $status
                    bot_error "Failed to install Termux system packages. Exit code: $PKG_STATUS"
                    bot_error "Please ensure Termux is up to date and packages exist: 'pkg update && pkg upgrade'."
                    return 1
                end
            else
                bot_error "'pkg' command not found. Cannot install Termux system dependencies."
                bot_error "Ensure Termux is correctly set up. Skipping system package installation."
                return 1
            end
        else
            bot_log "No specific Termux system dependencies identified in '$REQUIREMENTS'."
        end
    end
    return 0
end

function bot_install
    if not bot_check
        bot_error "Environment check failed. Cannot proceed with installation."
        return 1
    end

    if not test -f "$REQ_PATH"
        bot_warn "No '$REQUIREMENTS' file found at '$REQ_PATH'. Skipping dependency installation."
        return 0
    end

    if not _bot_handle_termux_system_deps
        bot_error "Termux system dependency installation failed. Aborting Python package installation."
        return 1
    end

    bot_log "Ensuring pip and wheel are up to date within the virtual environment..."
    if not $PYTHON_VENV_BIN -m pip install --retries 5 --timeout 60 --upgrade pip wheel >/dev/null 2>&1
        set -l PIP_UPGRADE_STATUS $status
        bot_error "Failed to upgrade pip and wheel. Exit code: $PIP_UPGRADE_STATUS"
        bot_error "This can happen due to network issues or restrictive environments."
        bot_error "Attempting to proceed, but future pip commands might fail."
    else
        bot_log "pip and wheel updated."
    end

    bot_log "Installing dependencies from '$REQ_PATH' via pip..."

    set -l TEMP_REQ (mktemp -t bot-reqs.XXXXXX)
    if test $status -ne 0
        bot_error "Failed to create temporary file for requirements. Check permissions or disk space."
        return 1
    end

    set -l PIP_INSTALL_CMD "$PYTHON_VENV_BIN -m pip install --retries 5 --timeout 60 --no-input"
    set -l COMPILER_VARS ""

    if string match -q "*com.termux*" "$PREFIX"
        grep -Evi "^(cryptography|pillow|numpy)" "$REQ_PATH" >"$TEMP_REQ"
        if test $status -ne 0
            bot_warn "Filtering Termux-specific packages from '$REQ_PATH' failed. Attempting full installation."
            cp "$REQ_PATH" "$TEMP_REQ"
        end
        set COMPILER_VARS "MATHLIB=m CFLAGS=\"-Wno-implicit-function-declaration -fPIC\" LDFLAGS=\"-L$PREFIX/lib\""
        bot_log "Applying Termux specific compiler flags for Python package installation."
        bot_warn "Be aware that custom CFLAGS can sometimes introduce security risks if dependencies are untrusted."
        set PIP_INSTALL_CMD "$COMPILER_VARS $PIP_INSTALL_CMD"
    else
        cp "$REQ_PATH" "$TEMP_REQ"
        if test $status -ne 0
            bot_error "Failed to copy '$REQ_PATH' to temporary file. Check permissions or disk space."
            rm -f "$TEMP_REQ"
            return 1
        end
    end

    set PIP_INSTALL_CMD "$PIP_INSTALL_CMD -r \"$TEMP_REQ\""

    bot_log "Executing: $PIP_INSTALL_CMD"
    set -l PIP_OUTPUT (eval "$PIP_INSTALL_CMD" 2>&1)
    set -l PIP_STATUS $status

    rm -f "$TEMP_REQ"

    if test $PIP_STATUS -ne 0
        bot_error "Dependency installation failed with exit code $PIP_STATUS."
        bot_error "Pip output (showing potential errors):"
        echo "$PIP_OUTPUT" | sed 's/^/  /' >&2
        bot_error "Common reasons for failure include missing build tools (e.g., C compiler), network issues, or incompatible package versions."
        bot_error "If running in Termux, ensure 'pkg install build-essential' is done and required system packages are pre-installed."
        bot_error "If network issues are suspected, try again or check your internet connection."
        return 1
    end

    bot_log "Dependencies up to date."
    bot_warn "For enhanced security, consider using 'pip install --require-hashes' with a locked requirements file."
    return 0
end

# --- 5. Runtime Supervision Functions ---
function _bot_is_crash_looping
    set -l now (date +%s)
    set -l cutoff (math "$now - $CRASH_WINDOW")
    set -l new_ts

    for ts in $CRASH_TS
        if test "$ts" -gt "$cutoff"
            set -a new_ts "$ts"
        end
    end

    set -g CRASH_TS $new_ts
    set -a CRASH_TS "$now"

    if test (count $CRASH_TS) -gt $MAX_CRASHES
        return 0
    end
    return 1
end

function bot_run
    if not bot_check
        bot_error "Pre-run check failed. Please resolve environment issues before running the bot."
        return 1
    end
    bot_log "Starting bot via '$PYTHON_VENV_BIN $BOT_PATH'..."
    $PYTHON_VENV_BIN "$BOT_PATH" $argv
    set -l RUN_STATUS $status
    if test $RUN_STATUS -ne 0
        bot_error "Bot exited with non-zero status: $RUN_STATUS."
    else
        bot_log "Bot exited cleanly (status 0)."
    end
    return $RUN_STATUS
end

function bot_supervise
    while true
        bot_log "Supervisor active. Starting bot with auto-restart..."
        $PYTHON_VENV_BIN "$BOT_PATH" $argv
        set EXIT_CODE $status

        switch $EXIT_CODE
            case 0
                bot_log "Clean exit detected. Stopping supervisor."
                break
            case 10
                bot_log "Bot requested critical shutdown (exit code 10). Exiting supervisor."
                break
            case 42
                bot_log "Bot requested immediate restart (exit code 42)..."
                sleep 1
            case 130 143
                bot_log "Termination signal caught (exit code $EXIT_CODE). Exiting supervisor."
                break
            case '*'
                bot_error "Bot crashed unexpectedly with exit code $EXIT_CODE."

                if _bot_is_crash_looping
                    bot_error "FATAL: Reached $MAX_CRASHES crashes in {$CRASH_WINDOW}s."
                    bot_error "Manual intervention required. Supervisor shutting down."
                    return 1
                end

                set -l crash_count (count $CRASH_TS)
                bot_log "Restarting in {$RESTART_WAIT}s (Failure $crash_count/$MAX_CRASHES)."
                sleep $RESTART_WAIT
        end
    end
end

# --- 6. Help Function ---
function bot_help
    echo -e "\033[1;35m▶ BOT SOURCED COMMANDS\033[0m"
    echo -e "\033[2m----------------------------------------\033[0m"
    echo -e "  \033[1;36mbot_run\033[0m       Start the bot normally"
    echo -e "  \033[1;36mbot_supervise\033[0m Start the bot with auto-restart loop"
    echo -e "  \033[1;36mbot_check\033[0m     Verify or create the virtual environment"
    echo -e "  \033[1;36mbot_install\033[0m   Install dependencies from requirements.txt"
    echo -e "  \033[1;36mbot_clean\033[0m     Remove __pycache__ and .pyc files"
    echo -e "  \033[1;36mbot_help\033[0m      Show this menu"
end

# --- 7. Initial Script Execution ---
bot_log "Environment loaded. Type 'bot_help' for available commands."
