// Server half of the tmux-agent OpenCode plugin. OpenCode 2 lists TUI
// plugins through the server's plugin registry, which requires a server
// entrypoint; the work happens in ./tui.js, inside the pane's TUI process.
export default {
  id: "tmux-agent",
  setup() {},
};
