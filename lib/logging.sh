#!/bin/bash
# Logging and output helper functions

# Prevent multiple sourcing
if [[ -n "${_LOGGING_SH_LOADED:-}" ]]; then
    return 0
fi
_LOGGING_SH_LOADED=1

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Log levels
LOG_ERROR=0
LOG_WARN=1
LOG_INFO=2
LOG_DEBUG=3

# Current log level (can be overridden)
LOG_LEVEL="${LOG_LEVEL:-$LOG_INFO}"

# Progress tracking
PROGRESS_CURRENT=0
PROGRESS_TOTAL=0
PROGRESS_START_TIME=0
PROGRESS_STEP_START=0

# Spinner state
SPINNER_PID=0
SPINNER_MESSAGE=""

# Log a message with color
log() {
    local level=$1
    local color=$2
    shift 2
    
    if [[ $level -le $LOG_LEVEL ]]; then
        echo -e "${color}$*${NC}"
    fi
}

# Log error message
log_error() {
    log $LOG_ERROR "$RED" "ERROR: $*"
}

# Log warning message
log_warn() {
    log $LOG_WARN "$YELLOW" "WARNING: $*"
}

# Log info message
log_info() {
    log $LOG_INFO "$BLUE" "$*"
}

# Log success message
log_success() {
    log $LOG_INFO "$GREEN" "✓ $*"
}

# Log debug message
log_debug() {
    log $LOG_DEBUG "$PURPLE" "DEBUG: $*"
}

# Print section header
log_header() {
    local title=$1
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $title${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# Print step header
log_step() {
    local step=$1
    echo -e "${BLUE}▸ $step${NC}"
}

# Print error and exit
die() {
    log_error "$@"
    exit 1
}

# Check if a command exists
command_exists() {
    command -v "$1" &>/dev/null
}

# Require a command to exist
require_command() {
    local cmd=$1
    local msg=${2:-"$cmd is required but not installed"}
    
    if ! command_exists "$cmd"; then
        die "$msg"
    fi
}

# ═══════════════════════════════════════════════════════════════
# PROGRESS TRACKING
# ═══════════════════════════════════════════════════════════════

# Initialize progress tracking
progress_init() {
    PROGRESS_TOTAL=$1
    PROGRESS_CURRENT=0
    PROGRESS_START_TIME=$(date +%s)
    echo ""
}

# Advance progress to next step
progress_step() {
    local description=$1
    PROGRESS_CURRENT=$((PROGRESS_CURRENT + 1))
    PROGRESS_STEP_START=$(date +%s)
    
    # Calculate elapsed time
    local elapsed=$((PROGRESS_START_TIME - $(date +%s) + $(date +%s) - PROGRESS_START_TIME))
    elapsed=$(( $(date +%s) - PROGRESS_START_TIME ))
    
    echo ""
    echo -e "${WHITE}┌─────────────────────────────────────────────────────────┐${NC}"
    echo -e "${WHITE}│${NC} ${CYAN}Step $PROGRESS_CURRENT/$PROGRESS_TOTAL${NC} ${WHITE}│${NC} ${GREEN}$description${NC}"
    echo -e "${WHITE}└─────────────────────────────────────────────────────────┘${NC}"
}

# Complete current step with timing
progress_complete() {
    local status=${1:-"done"}
    local step_end_time=$(date +%s)
    local step_duration=$((step_end_time - PROGRESS_STEP_START))
    
    local minutes=$((step_duration / 60))
    local seconds=$((step_duration % 60))
    
    local time_str=""
    if [[ $minutes -gt 0 ]]; then
        time_str="${minutes}m ${seconds}s"
    else
        time_str="${seconds}s"
    fi
    
    if [[ "$status" == "done" ]]; then
        echo -e "${GREEN}  ✓ Complete${NC} ${BLUE}($time_str)${NC}"
    elif [[ "$status" == "skipped" ]]; then
        echo -e "${YELLOW}  ⊘ Skipped${NC} ${BLUE}($time_str)${NC}"
    elif [[ "$status" == "failed" ]]; then
        echo -e "${RED}  ✗ Failed${NC} ${BLUE}($time_str)${NC}"
    fi
}

# Print final summary
progress_summary() {
    local total_time=$(($(date +%s) - PROGRESS_START_TIME))
    local minutes=$((total_time / 60))
    local seconds=$((total_time % 60))
    
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Total time: ${minutes}m ${seconds}s${NC}"
    echo ""
}

# ═══════════════════════════════════════════════════════════════
# SPINNER ANIMATION
# ═══════════════════════════════════════════════════════════════

# Spinner frames
spinner_frames=() 
spinner_frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

# Start spinner in background
spinner_start() {
    SPINNER_MESSAGE=$1
    
    # Hide cursor
    echo -ne "\033[?25l"
    
    (
        while true; do
            for frame in "${spinner_frames[@]}"; do
                echo -ne "\r${CYAN}  $frame${NC} ${SPINNER_MESSAGE}  "
                sleep 0.1
            done
        done
    ) &
    SPINNER_PID=$!
    
    # Ensure spinner is cleaned up on exit
    trap "spinner_stop" EXIT
}

# Stop spinner
spinner_stop() {
    if [[ $SPINNER_PID -ne 0 ]]; then
        kill $SPINNER_PID 2>/dev/null || true
        wait $SPINNER_PID 2>/dev/null || true
        SPINNER_PID=0
    fi
    
    # Show cursor
    echo -ne "\033[?25h"
    
    # Clear spinner line
    echo -ne "\r\033[K"
}

# Run a command with spinner
run_with_spinner() {
    local message=$1
    shift
    
    spinner_start "$message"
    
    local exit_code=0
    if [[ "$DRY_RUN" == "true" ]]; then
        spinner_stop
        log_info "[DRY RUN] $*"
    else
        "$@" || exit_code=$?
        spinner_stop
    fi
    
    return $exit_code
}