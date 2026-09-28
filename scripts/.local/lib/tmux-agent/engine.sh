#!/bin/bash
# engine.sh -- agent detection and state classification for tmux-agent.
# Sourced by ~/.local/bin/tmux-agent and by tests/test_tmux_agent.py.
#
# Detection walks the pane's process tree looking for a known coding-agent
# CLI. Classification is heuristic: CPU-time deltas say "working", and the
# bottom of the pane's captured output says what the agent waits on or that
# it finished. States:
#   blocked -- agent needs input or approval
#   working -- agent is actively running
#   ready   -- work finished, the pane has not been looked at since
#   idle    -- finished and seen
#
# shellcheck shell=bash

[[ -n "${_TA_ENGINE_LOADED:-}" ]] && return 0
_TA_ENGINE_LOADED=1

# CPU ticks (100ths of a second) gained across a poll interval to count as
# working when the captured pane output also changed. Idle TUIs periodically
# wake for housekeeping, so CPU activity alone is not evidence of work.
declare -r TA_CPU_TICKS_WORKING=25

# Known agent CLI names. Detection matches these against the process name
# (prefix, so "claude-code" counts) and against argv as a path/word boundary.
declare -r TA_AGENT_NAMES='opencode claude codex gemini aider amp droid grok copilot qoder kiro hermes antigravity'

ta_state_rank() {
    case "$1" in
    blocked) echo 0 ;;
    working) echo 1 ;;
    ready) echo 2 ;;
    idle) echo 3 ;;
    *) echo 4 ;;
    esac
}

ta_rollup() {
    # Most urgent of the given states; empty in, empty out.
    local worst='' st rank best=99
    for st in "$@"; do
        [[ -z "$st" ]] && continue
        rank=$(ta_state_rank "$st")
        if ((rank < best)); then
            best=$rank
            worst=$st
        fi
    done
    printf '%s\n' "$worst"
}

ta_state_color() {
    # tmux colour name per state.
    case "$1" in
    blocked) echo red ;;
    working) echo yellow ;;
    ready) echo blue ;;
    idle) echo green ;;
    *) echo white ;;
    esac
}

ta_state_ansi() {
    # ANSI colour per state, for fzf --ansi.
    case "$1" in
    blocked) printf '\033[31m' ;;
    working) printf '\033[33m' ;;
    ready) printf '\033[34m' ;;
    idle) printf '\033[32m' ;;
    *) printf '\033[37m' ;;
    esac
}

ta_agent_glyph() {
    # Nerd Font codicons: nf-cod-claude (U+EC82), nf-cod-openai (U+EC81)
    # for Codex, nf-cod-agent (U+EC67) for the rest. Overrides still accept
    # any terminal-renderable glyph.
    case "$1" in
    claude) echo "${TMUX_AGENT_ICON_CLAUDE:-}" ;;
    codex) echo "${TMUX_AGENT_ICON_CODEX:-}" ;;
    opencode) echo "${TMUX_AGENT_ICON_OPENCODE:-}" ;;
    *) echo "${TMUX_AGENT_ICON_DEFAULT:-}" ;;
    esac
}

ta_hook_state() {
    # $1 agent lifecycle event. Prints the state it reports, "end" when the
    # agent session closed, or nothing for events that say nothing about
    # state. Claude Code and Codex share hook event names; the OpenCode
    # plugin forwards its (v2) server bus event types.
    case "$1" in
    SessionStart) echo idle ;;
    UserPromptSubmit | PreToolUse | PostToolUse | PreCompact) echo working ;;
    session.execution.started | permission.replied | form.replied | form.cancelled) echo working ;;
    PermissionRequest | Notification) echo blocked ;;
    permission.asked | form.created) echo blocked ;;
    Stop) echo ready ;;
    session.execution.succeeded | session.execution.failed | session.execution.interrupted) echo ready ;;
    SessionEnd) echo end ;;
    esac
}

ta_match_blocked() {
    grep -qiE \
        'do you want|\[y/n\]|\[y/N\]|\[Y/n\]|\(y/n\)|press enter to|(^|[^[:alnum:]])(allow|approve|grant|permission)[^?]{0,80}\?|^[^[:alnum:]]{0,6}1\. (yes|no)' \
        <<<"$1"
}

ta_match_working() {
    # Spinner glyphs are alternations, not a bracket class: under a C
    # locale grep would match their bytes individually and light up on
    # unrelated box-drawing characters.
    grep -qiE \
        'esc to interrupt|esc to stop|working\.\.\.|thinking\.\.\.|running\.\.\.|(thinking|doodling|working|running|searching|planning|reading|writing|generating)…|⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏|◐|◓|◑|◒|⣾|⣽|⣻|⢿|⡿|⣟|⣯|⣷|◜|◠|◝|◞|◡|◟' \
        <<<"$1"
}

ta_match_ready() {
    grep -qiE \
        '✓|✔|(^|[^[:alnum:]])(done\.?|completed|finished|all done|task complete|success)([^[:alnum:]]|$)' \
        <<<"$1"
}

ta_classify() {
    # $1 pane tail text, $2 CPU ticks gained since last poll,
    # $3 previous state, $4 seen-since-last-change (1/0),
    # $5 captured output changed since last poll (1/0). Prints the state.
    local tail=${1:-} cpu_delta=${2:-0} prev=${3:-} seen=${4:-0}
    local output_changed=${5:-0} state=''
    if ta_match_blocked "$tail"; then
        state=blocked
    elif ta_match_working "$tail"; then
        state=working
    elif ((cpu_delta >= TA_CPU_TICKS_WORKING)) && [[ $output_changed == 1 ]]; then
        state=working
    elif ta_match_ready "$tail"; then
        state=ready
    elif [[ $prev == working ]]; then
        # It was going, now it is quiet: the work finished.
        state=ready
    else
        state=${prev:-idle}
    fi
    if [[ $state == ready && $seen == 1 ]]; then
        state=idle
    fi
    printf '%s\n' "$state"
}

ta_agent_name_of() {
    # $1 process name, $2 argv. Prints the matched agent name, if any.
    local comm=${1,,} args=${2,,} name
    for name in $TA_AGENT_NAMES; do
        case "$comm" in
        "$name" | "$name"-*)
            printf '%s\n' "$name"
            return 0
            ;;
        esac
        if grep -qE "(^|[/[:space:]])$name([/:.[:space:]]|$)" <<<"$args"; then
            printf '%s\n' "$name"
            return 0
        fi
    done
    return 1
}

ta_detect_agent() {
    # $1 pane pid. Prints "<agent name> <agent pid>" for the first agent
    # process found in the pane's process tree (the pane process included).
    local root=${1:-}
    [[ -n "$root" ]] || return 1
    local pid ppid comm args next name
    local -A children=() comms=() argss=()
    while read -r pid ppid comm args; do
        children[$ppid]="${children[$ppid]:-} $pid"
        comms[$pid]=$comm
        argss[$pid]=$args
    done < <(ps -eo pid=,ppid=,comm=,args= 2>/dev/null)

    local queue=("$root") visited=' '
    while ((${#queue[@]} > 0)); do
        pid=${queue[0]}
        queue=("${queue[@]:1}")
        case "$visited" in
        *" $pid "*) continue ;;
        esac
        visited="$visited$pid "
        if name=$(ta_agent_name_of "${comms[$pid]:-}" "${argss[$pid]:-}"); then
            printf '%s %s\n' "$name" "$pid"
            return 0
        fi
        for next in ${children[$pid]:-}; do
            queue+=("$next")
        done
    done
    return 1
}

ta_proc_cpu() {
    # utime+stime+cutime+cstime in clock ticks for $1 and its waited-for
    # children, from /proc/<pid>/stat (fields 14-17).
    local stat f
    stat=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
    read -r -a f <<<"${stat##*) }"
    echo $((${f[11]:-0} + ${f[12]:-0} + ${f[13]:-0} + ${f[14]:-0}))
}
