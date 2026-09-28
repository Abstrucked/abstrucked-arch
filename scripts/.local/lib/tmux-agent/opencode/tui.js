// tmux-agent OpenCode TUI plugin: forwards session lifecycle events to
// `tmux-agent hook opencode <event>` so the tmux status bar and desktop
// notifications follow the agent exactly instead of guessing from the pane.
//
// OpenCode 2 runs one shared server for every TUI, so this has to be a TUI
// plugin: only the TUI process lives in the tmux pane (TMUX_PANE). The
// directory is linked to ~/.config/opencode/plugins/tmux-agent by
// `tmux-agent install-hooks`.

import { spawn } from "node:child_process";

const BIN = process.env.TMUX_AGENT_BIN || `${process.env.HOME}/.local/bin/tmux-agent`;

// Server bus events forwarded as-is; tmux-agent maps them to states.
// Execution events only count for root sessions: a subagent finishing does
// not mean the pane is done. Prompts for the user count from any session.
const EXECUTION = new Set([
  "session.execution.started",
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.interrupted",
]);
const PROMPTS = new Set([
  "permission.asked",
  "permission.replied",
  "form.created",
  "form.replied",
  "form.cancelled",
]);

function report(event) {
  // Fire and forget: the hook rescans panes in the background anyway.
  try {
    spawn(BIN, ["hook", "opencode", event], { stdio: "ignore", detached: true }).unref();
  } catch {
    // tmux-agent missing or not executable: stay out of the agent's way.
  }
}

function sessionOf(event) {
  const data = event?.data ?? {};
  return data.sessionID ?? data.form?.sessionID;
}

export default {
  id: "tmux-agent",
  setup(api) {
    if (!process.env.TMUX_PANE) {
      return;
    }

    // The server streams every TUI's sessions. Keep the ones this pane has
    // shown (routed or tabbed), so they still count after navigating away.
    const owned = new Set();
    const root = (id) => api.data?.session?.root?.(id) ?? id;
    const mine = (id) => {
      const r = root(id);
      if (owned.has(r)) {
        return true;
      }
      const route = api.ui?.router?.current?.();
      const shown =
        (route?.type === "session" && root(route.sessionID) === r) ||
        (api.ui?.tabs?.list?.() ?? []).some((tab) => tab.sessionID === r);
      if (shown) {
        owned.add(r);
      }
      return shown;
    };

    const handle = (event) => {
      const type = event?.type;
      const id = sessionOf(event);
      if (id === undefined || !(EXECUTION.has(type) || PROMPTS.has(type)) || !mine(id)) {
        return;
      }
      if (EXECUTION.has(type) && root(id) !== id) {
        return;
      }
      if (type === "session.execution.interrupted" && event.data?.reason === "shutdown") {
        return;
      }
      report(type);
    };

    const abort = new AbortController();
    (async () => {
      // Reconnect with backoff: the shared server may restart under us.
      for (let delay = 500; !abort.signal.aborted; delay = Math.min(delay * 2, 10_000)) {
        try {
          for await (const event of api.client.event.subscribe({ signal: abort.signal })) {
            delay = 500;
            handle(event);
          }
        } catch {
          // Stream dropped; retry below unless disposed.
        }
        if (!abort.signal.aborted) {
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }
    })();

    return () => abort.abort();
  },
};
