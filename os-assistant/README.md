# os-assistant

A small, local OS assistant. It runs a quantized local model (default
Qwen3-4B Instruct 2507; MiniCPM5-2B was the previous default) through a
local Ollama server and exposes curated system tools and optional, confirmed
actions. Written in standard-library-only Python (no third-party Python dependencies;
the optional Bash tool requires installed bubblewrap/utilities), and shipped as an
optional GNU Stow package: nothing is linked unless you opt in.

- Model source: <https://ollama.com/openbmb/minicpm5-2b>, pulled by the exact tag
  `openbmb/minicpm5-2b:latest`. The upstream model is published at
  <https://huggingface.co/openbmb/MiniCPM5-2B>. The installed artifact is
  Q4_K_M (1561319547 bytes, roughly 1.6 GB) and reports tool calling and
  completion support; the client always requests thinking off.
- The default is `qwen3:4b-instruct-2507-q4_K_M` (Qwen3-4B Instruct 2507,
  pulled with `ollama pull qwen3:4b-instruct-2507-q4_K_M`). MiniCPM5-2B
  (`openbmb/minicpm5-2b:latest`) was the previous default and remains
  allowed; the MiniCPM measurements below are labelled as such. `[model] name`
  may instead be one of a small allowlist: `openbmb/minicpm5-2b:latest`,
  `qwen3.5:2b-q4_K_M`, `llama3.2:3b`, `granite4:3b`, or
  `phi4-mini:3.8b`. Only the exact configured tag runs; every other name
  (aliases, other tags, cloud names) is refused with an error listing the
  allowed names, and there is no fallback or silent substitution. Only the
  previous default (MiniCPM5-2B) has been measured; the figures below do not
  apply to other models, including the new Qwen3-4B default.
- The model runs on this machine: the configured host is the loopback address
  `http://127.0.0.1:11434`. Remote Ollama hosts are rejected. The assistant
  itself talks only to loopback; the optional web search is off by default and,
  when enabled, reaches public engines only through your local SearXNG (see
  Web search below).

## Layout

| Path | Purpose |
| --- | --- |
| `os-assistant/.local/bin/os-assistant` | Launcher (bash); resolves its own real path, then runs `run.py` with `/usr/bin/python3 -B -I` |
| `os-assistant/.local/share/os-assistant/run.py` | Python entry point; adds its resolved parent to `sys.path` and calls `os_assistant.cli.main()` |
| `os-assistant/.local/share/os-assistant/os_assistant/` | CLI, config parsing, policy, tools (stdlib Python) |
| `os-assistant/.config/os-assistant/config.toml` | Strict TOML configuration |

The launcher works straight from a checkout (`os-assistant/.local/bin/os-assistant`)
and when stowed: it resolves its own symlink with `realpath`, so relocation of
the checkout and paths containing spaces are fine.

## Install (optional, Stow)

Preview first (this is the default and changes nothing):

```sh
install/setup-os-assistant.sh
```

Create the links only when the preview looks right:

```sh
install/setup-os-assistant.sh --apply
```

If you already have a personal `~/.config/os-assistant/config.toml` (a regular
file), the helper keeps it untouched and links everything else; it is never
adopted, moved, or replaced. Any other conflicting file still makes it fail.

The helper only stows this one package, with `--no-folding` so your existing
`~/.local`, `~/.config`, and friends stay real directories. It never installs
packages, downloads anything, enables services, or elevates privileges, and it
refuses to run as root. `--target DIR` links into another (absolute) directory,
which the tests use against throwaway homes. Existing conflicting files make
both modes fail. Equivalent manual command:

```sh
stow --no-folding -d <dotfiles-checkout> -t "$HOME" os-assistant
```

To unlink: `stow -D --no-folding -d <dotfiles-checkout> -t "$HOME" os-assistant`.

## Ollama (manual setup)

Ollama is in Arch's Extra repository; no AUR helper is needed. This assistant
never enables or starts services for you — set it up by hand:

```sh
sudo pacman -S --needed ollama
```

Serve it in its own terminal and leave it in the foreground:

```sh
export OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_HOST=127.0.0.1:11434 ollama serve
```

These settings disable Ollama cloud features and keep inference concurrency to
one request/model. No automatic boot service is needed.

In another terminal, if the model is **not already installed**, pull the exact
model tag (roughly 1.6 GB):

```sh
ollama pull openbmb/minicpm5-2b:latest
```

`openbmb/minicpm5-2b:latest` is a mutable namespace tag, so always identify the
installed weights by digest. The artifact currently installed on this machine
is Q4_K_M (1561319547 bytes), digest
`71a44e98400fbd490d66332a0ebba31143479a714987c13f45c82e94025cbfa7`. Print the
selected model's digest so you can record the exact artifact. The
assistant's `--doctor` uses Ollama's `/api/tags` model listing:

```sh
os-assistant --doctor
```

Weights from the earlier Qwen baseline (`qwen3.5:2b-q4_K_M`) are retained on
disk and are not removed, but they are **not** a fallback: the assistant refuses
any model name other than the exact configured tag.

No latency is promised: a cold model load and a warm one differ a lot, and the
assistant makes no timing guarantees either way.

## Usage

```sh
os-assistant 'prompt'   # one-shot prompt, e.g. 'what is using my disk?'
os-assistant chat       # interactive session
```

You can ask ordinary folder-size and file-count questions in chat; no shell commands or JSON
are needed. For example, with `~/.dotfiles` already approved:

```text
You> size of the ~/.dotfiles folder
You> size of /home/abstrucked/.dotfiles folder
You> how big is the dotfiles folder?
You> check the size of this directory
You> size of tests folder
You> how many files are in ~/.dotfiles?
```

Clear, single folder-size/file-count questions are recognized **locally, before inference**.
They use the existing `directory_usage` policy and guarded recursive metadata
scanner, not model-generated `du` arguments. They work even when Ollama is
unavailable. A size question returns allocated size; a count question returns
the number of scanned regular files. Logical size or both size metrics are shown
when explicitly requested. Each default answer is one short `result · <tool>` block
with a filtered-view qualifier; incomplete scans keep a short partial-result warning.
General conversation and requests
outside this small grammar still use the selected MiniCPM model; this does not
make its tool routing generally reliable.

The default approved folder is used for "this directory" or an unspecified size
target. Otherwise literal absolute paths, your own approved `~/` aliases, approved
root names and relative subfolders are checked against existing approvals. A
relative child uses its own name, such as `tests`; `./dotfiles` explicitly names
a child rather than an approved root's alias. Ambiguous root names or multiple
roots without a default get a local clarification. An immediate literal folder
reply can finish that size question; "which folder was that?" reports the measured
path without rescanning. Unrelated conversation, errors, previews and `/reset`
clear this narrow local context. Model-written instructions cannot arm it.

No access is expanded, no denied request is retried via the model, and local size
routing never selects a mutation or reads source-file contents. Mixed, negated,
conditional or explanatory prose is not treated as a local size command. `--dry-run`
retains exact previews without scans or inference for recognized size requests;
direct `--tool` also defaults to readable prose; `--json` opts into structured
diagnostics. Other natural-language requests
can still be misinterpreted by MiniCPM.

The preceding size-routing checkpoint was checked through its **unmodified launcher
in a real terminal session**: both exact size questions above, the earlier "use bash and
check the size of this directory" request and its bare `~/.dotfiles` follow-up
all succeeded (**4/4 actual size scans**). Each reported **30.1 GiB allocated /
29.5 GiB logical**, complete within the permitted view, with **165,106 encountered
entries excluded**. "Which folder was that?" returned the measured path without
a fifth scan, and `/reset` cleared the local context. No inference, source-file
content read, native `du`, confirmation or mutation was needed. Evidence:
`/tmp/opencode/os-assistant-natural-chat-live-rm5_9ptg.json`;
harness: `/tmp/opencode/os-assistant-natural-chat-live.py`.

Regression tests separately exercise known logical/allocated metadata, aliases,
subfolders, ambiguous-root clarifications, denied paths, bounded/partial scans,
no-content access, no model fallback after denial, dry-run, reset, and ordinary
chat fallback with a mocked client. This validates the narrow local grammar,
not broader model accuracy or mutation execution.
That checkpoint's full validation: **1,601 tests and 551 subtests passed**, plus syntax,
ShellCheck and whitespace checks. No new broad live-model evaluation or live
mutation/desktop restart was performed in this follow-up.

| Option | Meaning |
| --- | --- |
| `--config FILE` | Use an explicit configuration file instead of `~/.config/os-assistant/config.toml` |
| `--allow-root PATH` | Approve one more folder for scanning (repeatable; on top of `paths.allowed_roots`) |
| `--dry-run` | Show what a tool call would do without doing it |
| `--details` | Show additional readable detail, not JSON |
| `--json` | Explicitly request structured tool results |
| `--tool NAME --arguments JSON` | Run one curated tool directly, without the model, under the same policy checks |
| `--probe` | Evaluate the live model against non-executing test tools (see below) |
| `--doctor` | Check the launcher, config, and Ollama endpoint and report state |
| `--check-alerts` | Evaluate disk/RAM alert thresholds once, without the model; exit status 6 when any metric is at warning or critical (`--json` supported) |
| `--watch-alerts` | Run the alert watcher loop (see System alerts); normally started by the `system-alerts` plugin |

There is deliberately **no** `--yes` and no option to bypass approvals.
`--dry-run` cannot be combined with `--doctor` or `--probe`; those modes perform
diagnostics/inference, not tool previews. It is likewise refused with
`--check-alerts` and `--watch-alerts`, neither of which accepts a prompt.

### Plain answers and chat memory

All tools share a plain-language result formatter. Normal chat hides raw tool
arguments, JSON and diagnostic data blocks; known successful results are rendered
from actual tool records, without another model turn to reword numbers. Model
conversation is instructed to answer only the requested facts, usually in one
sentence, but its compliance and general routing remain experimental. Output is a one-line header at column 0 (`── <model> · no tools ran`,
`── result · <tool>`) followed by content indented two spaces, so model prose and tool data
cannot imitate the assistant's own prompts or approval text.

For file/output requests, **showing contents and explaining them are different**:

```text
You> tell me what the ~/.dotfiles/install.sh does
You> summarize ~/.dotfiles/install/setup-os-assistant.sh
You> Run `cat install.sh` and explain the output
```

Clear explanation/summarization requests use an additional **text-only model
pass** after successful authorized Bash reads, instead of returning raw stdout.
This pass has no tools or execution loop: proposed tool calls are rejected, not
prepared, approved, retried or executed. File text and read-command labels remain
quoted untrusted data; no additional helper files are read because the source
mentions them. It uses the same selected local MiniCPM and existing settings.
Only the current question and captured read output are supplied, not old history
or approvals. Text is bounded to fit the context with output room reserved;
excerpts and incomplete snapshots retain a short partial-read warning.

Interpretations sit under a `<model> · summary of read-only output` header, not verified execution facts. They describe
apparent behavior if the code is run, not proof of runtime behavior or unseen
helper implementations. Small-model summaries can still be inaccurate, and its
initial tool selection remains experimental. Empty/binary reads, malformed
summaries, tool proposals, recognized source dumps and structured responses fail without a
raw-content fallback or another read. Errors, denials, previews and mutations do
not enter the summary pass. Explicit `show contents` / literal `cat` requests keep
readable quoted output; sizes/counts keep deterministic fact-only answers.
`as JSON` / `--json` on an explanation produces a labelled model-answer object,
not a source dump. Cached `/details` and `/json` can still inspect the read record
explicitly, without rerunning anything.

The exact `tell me what the ~/.dotfiles/install.sh does` request was checked
through the unmodified checkout launcher and the selected live MiniCPM. It now
returns a short model interpretation, not the source listing; an explicit
`show me the contents of ~/.dotfiles/install.sh` request still returns quoted
contents. Instrumented live evidence separately confirmed **one sandboxed file
read followed by one no-tools summary call** (14 tool schemas for selection,
zero for summarization). Evidence:
`/tmp/opencode/os-assistant-file-explanation-live-1ubhtb77.json`;
harness: `/tmp/opencode/os-assistant-file-explanation-live.py`;
launcher outputs: `/tmp/opencode/os-assistant-file-explanation-live.log` and
`/tmp/opencode/os-assistant-file-contents-live.log`.
This verifies routing/control flow and presentation, **not semantic accuracy**:
the small model still over-associated the main installer with its optional
LazyVim component. A separate live launcher-summary request was stopped by an
unsupported Bash option, without relaxing policy. These are not broad model
accuracy results, and no script execution, approval expansion, installation,
service startup, model replacement/download or real mutation was performed.
Validation: **1,337 assistant tests passed**, including 51 synthesis regressions,
plus syntax, ShellCheck and whitespace checks. The full-suite attempts completed
with **1,727 passed and 551 subtests passed**, but one unrelated tmux closure
persistence test timed out; that test passed when rerun alone. It was not changed.
The initial full-suite run also exceeded its harness deadline. Logs:
`/tmp/opencode/os-assistant-synthesis-assistant-tests-final.log` and
`/tmp/opencode/os-assistant-synthesis-full-tests-final.log`.

Mutation and dry-run previews remain exact, but readable: literal argument values
and every frozen executable argument are shown separately. A mutation preview
cannot be truncated; an oversized preview is refused before confirmation. Typed
interactive `yes` is still required per mutation. Successful stdout is inert and
quoted line by line so filenames/output cannot impersonate approval or status UI.

| Chat command | Effect |
| --- | --- |
| `/clear`, `/reset` | Clear history, compacted notes, cached results and pending folder follow-ups |
| `/compact` | Replace older conversation with bounded historical notes; no inference or tool execution |
| `/details` | Show the last tool result as readable detail, explicitly not a new check |
| `/json` | Show that same historical result as JSON, without rerunning it |
| `/help` | List commands |
| `/quit` | Exit |

Natural `show details` / `show JSON` requests also inspect the cached result.
Append `with details` or `as JSON` to an ordinary question to request that format
for the new result. Quoted paths and literal command operands are never rewritten
as output preferences; backtick-delimited commands can have an explicit format
suffix. Format selection never adds permissions or alters tool arguments.

Before model input reaches the context budget, completed older exchanges are
compacted automatically. The trusted system instructions, complete enabled-tool
schemas, current request, and active tool/correction exchange are never dropped.
If those alone cannot fit, the turn still fails closed. Budgeting uses the existing
conservative character estimate, not an exact MiniCPM tokenizer.

Compaction is deterministic and in memory only: no extra summarization inference,
cloud call, persistence, service, model download or context-window change. Notes
retain a bounded literal user goal and selected typed observations from successful
read-only checks. They are quoted **historical, untrusted data**, not fresh system
facts or instructions. Model success claims, raw file output, action arguments and
old approvals are not promoted into the notes. This is lossy: older wording or
details may be discarded, especially when tool schemas leave little room. Clearing
or compacting never changes configured roots or authorization; `/compact` also
disarms local folder follow-ups. Cached result inspection never retries an action.

The plain-answer/context follow-up passed **1,677 tests and 551 subtests**, plus
syntax, ShellCheck and whitespace checks. Its unmodified launcher also passed a
real terminal session covering size/count replies, explicit details/JSON, cached
inspection without rescanning, `/compact`, and `/clear`. The first size reply was
one line (`30.1 GiB allocated (filtered view)`); the count reply contained only
the count and scope qualifier. These are historical permitted-view measurements,
not unrestricted totals or atomic snapshots. Evidence:
`/tmp/opencode/os-assistant-concise-chat-live-8ztz96uz.json`;
harness: `/tmp/opencode/os-assistant-concise-chat-live.py`.
A separate live MiniCPM RAM request returned just the available-memory fact:
`/tmp/opencode/os-assistant-concise-live-memory.log`.
Automatic compaction and active-exchange budget failures were tested with mocked
clients; this is not a new broad live-model accuracy evaluation. No real mutation,
desktop restart, install, service startup, model change or approval expansion was
performed. Stow simulation was blocked by the existing real-home config file;
it was left unchanged. Restart chat through the checkout launcher to load changes:
`~/.dotfiles/os-assistant/.local/bin/os-assistant chat`.

### Conversational argument recovery

Known tools with missing/unknown fields get **one** correction opportunity before
any tool result or approval, only for a single-call proposal. Feedback contains
trusted field names/validation text, never unknown argument values or model
permission metadata. Execution budgets do not increase. Unknown/disabled tools,
invalid types/ranges, unsafe paths/commands, mixed batches, and failures after a
result are not retried; denials and runtime errors still stop the turn.

A conservative guard rejects substitution of recognizable explicitly requested
command names (for example, `Use bash to run ls ...` cannot silently become `du`).
For a single unambiguous literal directive beginning with `Run`, `Execute` or
`Use bash to run/execute`, it now also compares the complete audited command plan:
options, operands, pipeline stages/order/counts, working folder, and mutation
text/destination. It never silently rewrites the proposal. One safe single-call
mismatch can use the same pre-execution correction budget; split/extra batches
execute nothing. Unsupported options and unsafe paths remain policy failures,
not repairable mismatches. Standalone `du` may use the equivalent live-size tool
only for the same approved folder; a pipeline cannot become a plain size call.

Prefer backticks to delimit a literal command in chat:

```text
Run `ls -lh . | head -n 5`
Execute `find tests -type f -name '*.py' | head -n 3` and explain the output.
```

Fixed approved-folder suffixes are also recognized outside shell quotes. Shell
quoting/whitespace and in-root absolute/relative equivalents compare by audited
effects; simple `ls -lh/-hl/-l -h` switches commute, but arbitrary option order
does not. Filename punctuation and quoted text are not trimmed as prose. The
comparison performs no filesystem probes or execution and grants no permission.
This is not full natural-language understanding: ambiguous, negated, conditional,
historical and explanatory examples are not command authorizations. Other phrasing
can still receive only the name-level guard or rely on model interpretation.
Failed user turns now remain in bounded in-memory history, with a safe stop note,
so subsequent folder answers do not fall back to a stale prior request. `/reset`
still clears all conversational history.
It also clears local folder-size follow-up/clarification state.

Chat prints its default approved folder, and the model receives that same explicit
context. With a single Bash root, "this directory" means that root, not `~/` or
an arbitrary shell working directory. If that root is under your home directory,
the context also includes its exact accepted `~/...` alias mapping, derived from
the same home path used by validation. An alias does not authorize the whole home.
Successful single-call Bash reads return
their captured output and a deterministic `result · <tool>` block instead
of another tool-enabled model turn. This prevents repeated `ls` and invented
counts, but does not add free-form model interpretation of file contents.

### Actions (off by default)

Actions such as launching an app stay disabled. To use them you must both set
`actions.enabled = true` in `config.toml` and give a typed `yes` at each call's
confirmation prompt. Even then aliases map only to fixed absolute executables
(for example `'/usr/bin/firefox'`); there is no arbitrary command execution.
Executables and their resolved parent directories must be root-owned and not
group/other-writable. Approval requires
an interactive terminal: piping `yes` cannot approve an action.

### Tools

Available: `system_status`, `processes`, `find_files`, `directory_usage`, plus
the six machine-specific read-only status tools below. Results are bounded
summaries — counts, names, sizes and selected state. The optional `bash` interface
additionally permits ordinary file-content reads inside explicitly approved
folders; credential paths remain excluded. Process command lines/environment
are never exposed.

Optional, implemented but disabled by default: `web_search` (see Web search),
`launch_app`, `set_volume`,
`set_brightness`, the separately opted-in `theme_status` / `set_theme` / `apply_theme`,
and the restricted `bash` command interface. Run the routing probe and safety tests before opting into
these actions. This is a validation milestone, not an automatic configuration change.

Not offered: unrestricted content access, process command lines/environment,
package installation, privilege escalation, arbitrary shells/scripts, recursive
deletion, service/journal logs, or access outside approved folders. The restricted
Bash interface permits only its supported, confirmed file operations, not general
command execution.

`find_files` only scans folders approved in `paths.allowed_roots` or via
`--allow-root`; the shipped list is empty. Search stops at the smaller `scan_*`
limits and reports logical file sizes, not allocated disk blocks. Bounded samples
can miss larger files elsewhere. No contents or timestamps are returned.
`directory_usage` also accepts enabled Bash roots, uses separate `usage_*` limits,
and reports live logical and allocated sizes; see Recursive file sizes below.

### Restricted Bash commands

`bash` is a **restricted command interface, not a general-purpose shell**. It
reuses installed Bash/coreutils/grep/rg/find for audited read-only commands; it
does not execute model-supplied scripts or trust a model's "read-only" label.
Repository defaults keep it off. To opt in locally:

```toml
[bash]
enabled = true
allowed_roots = ['~/.dotfiles']
allow_writes = false
```

Approving a Bash folder grants **ordinary file-content access**, unlike
`[paths].allowed_roots` and `--allow-root`, which still authorize metadata only.
The config lists remain separate: metadata approval never grants content access;
enabled Bash content approval also permits the narrower `directory_usage` metadata
tool in that same folder. The initial local scope on this machine
is only `/home/abstrucked/.dotfiles`, not the whole home folder. Local supported
writes are opted in, but every one still requires typed `yes` and
`[actions].enabled = true`; shipped defaults grant neither.

```sh
assistant="$HOME/.dotfiles/os-assistant/.local/bin/os-assistant"
"$assistant" --tool bash --arguments '{"root":"/home/abstrucked/.dotfiles","command":"ls -lh ."}'
"$assistant" --tool bash --arguments '{"root":"/home/abstrucked/.dotfiles","command":"grep -n Stow README.md"}'
"$assistant" --tool bash --arguments '{"root":"/home/abstrucked/.dotfiles","command":"grep -r -l themectl themes | head -n 5"}'
"$assistant" --dry-run --tool bash --arguments '{"root":"/home/abstrucked/.dotfiles","command":"touch scratch.txt"}'
```

`command` is required. `root` defaults to the sole approved Bash folder; with
multiple roots it is required. `cwd` is an optional literal subfolder of `root`,
default `.`. Approved root/cwd/operand paths accept your own `~/...` shorthand,
canonicalized and then checked against the allowlist; other users' `~name` paths
are not supported. Paths may also be literal relative paths or absolute paths
inside the root (mapped internally as `/work`). No parent traversal, shell
variable expansion or pathname globs: use `find . -name '*.py'` rather than
`ls *.py`. Argument quoting is parsed then safely reconstructed; the original
command text never reaches a host shell.

**Automatic reads:** `pwd`, `ls`, `cat`, `grep`, `rg`, restricted `find`, `head`,
`tail`, `wc`, `sort`, `uniq`, `cut`, `df`, literal `echo`/`printf`, and up to
four read-only pipe stages. **Standalone `du` summaries are the exception:**
they use a guarded live-metadata adapter, not Bash/native `du` and not snapshot
blocks. They support one directory and `-s/-h/-b/-k/--apparent-size`; omitted `-s`
is normalized to a summary. `-b`/`--apparent-size` select logical file bytes;
otherwise allocated file/directory blocks are reported. `du` pipelines, `-a/-c`,
and depth options are rejected; use `directory_usage` for subdirectory reports.
No host shell, source contents or temporary copy is involved in size measurement.
Options are allowlisted too: examples include
`grep -r/-n/-l/-e`, `head/tail -n/-c`, `cut -d/-f/-c/-b`, and find
`-name/-iname/-type/-maxdepth/-mindepth/-print`. Not every standard flag is supported.
No `find -exec/-delete`, `sort -o/--compress-program`, `uniq` output operand,
`tail -f`, rg preprocessors, `xargs`, shell startup files, command substitution,
command chains, background jobs or arbitrary executables. Unknown syntax is
**blocked**, not reclassified as safe or silently run after a generic approval.

Snapshot commands run with root-owned Bash/binaries, bubblewrap and `prlimit`.
The namespace hides the host home, credentials/environment, desktop sockets,
host processes and network. `/usr` and a private **filtered snapshot** of the
approved root are read-only; `/usr/local` is hidden and the small `/tmp` scratch
mount is private. Further user namespaces are disabled. There is no unsandboxed
fallback if these dependencies or namespace permissions are unavailable.

The snapshot uses fd-relative, no-follow reads, excludes protected names
(including `.git`, `.config`, `.env*`, credential files), symlinks, hardlinks,
special files and nested mounts (including same-device bind mounts, checked with
Linux mount IDs). Only requested paths/subtrees are staged. `ls`/`find` need
no source-file contents: their ordinary files are represented by sparse metadata
placeholders up to **16 GiB** logical size. Content-reading commands never read
these placeholders: their operands instead require real copied contents, with
files over **1 MiB** excluded and at most **16 MiB** copied in total. The snapshot
respects the existing entry/depth/time scan limits. Results explicitly say
`snapshot_only` / `sample_only`, count exclusions and mark truncation. In
particular, **ls-style metadata and df results describe the filtered copy
and sandbox filesystem, not complete/live host metadata**. `pwd` reports the
virtual `/work` path. File sizes in `ls` reflect source logical sizes, but modes,
timestamps, directory sizes and allocated blocks do not. **Do not derive host
disk usage from snapshot `ls` blocks or directory metadata.** `df` reports the
sandbox filesystem, not host disk usage (use `system_status` for that).
A missing match does not prove absence in the real tree.

Sandbox subprocesses have the configured wall timeout, 8 KiB combined stdout/stderr cap,
128 MiB per-process address-space limit, CPU/fd/file-size limits and no core dumps.
Temporary snapshot files are private and normally removed after each call;
forcibly killing the assistant can leave a private temporary directory. The
snapshot deadline is best-effort between filesystem operations, not a kernel
I/O timeout; live size scans use separate `usage_*` budgets, and guarded file
operations also have no kernel I/O timeout. A denylist
cannot identify every sensitive filename: approve narrow
folders whose ordinary contents you intend to share with the local model.

**Confirmed writes:** one-operand `mkdir`, `touch`, `rm`; two-operand `cp`, `mv`;
and literal `echo ... > file` or `printf '%s'/'%s\\n' value > / >> file`. These
use guarded fd-relative Python filesystem operations, **not a host shell**.
They support owned regular files up to 1 MiB, never recursive/force flags,
directory moves/removal, symlinks/hardlinks, protected paths, or modifying the
assistant's own package/permission code or its trusted theme/plugin/status
helper sources (the `themes`/`plugins` trees and fixed display/syntax helpers).
Read/copy-out access to an ordinary helper source is not permission to edit it.
Parent folders must already exist:
`mkdir -p` and `rm -rf` remain blocked. New touch files and cp/echo/printf content
replacements have mode 0600; mv and touching existing files preserve their mode.
New directories have mode 0700. This is deliberately a limited command subset,
not complete GNU command semantics or a general editor.

The full original command, root/cwd, normalized operation argv and effects are
previewed before typed `yes`. Ownership/path/inode/source metadata is checked
again across approval. `>` and `cp` publish by atomic replacement rather than
truncating a potentially raced link. These guards do not defend against all
compromised-account races or guarantee complete transitive system-code integrity.
Failures stop the turn and may leave changes; no automatic retry/rollback occurs.
Dry-run never copies file contents, executes commands, creates output files or
asks for confirmation. No live checkout file write was used for validation.

### Machine-specific status tools

All six take **no arguments**, run without confirmation and can be disabled
individually with `[status].enabled`. They read only fixed state/attribute files
and this checkout's metadata; they do not grant arbitrary home-folder access.

| Tool | What it reports |
| --- | --- |
| `desktop_status` | This user's desktop-process presence, system/user `tailscaled` presence, saved layout/palette/wallpaper-set state; not IPC or service health |
| `power_status` | CPU0 governor, platform profile, battery, and installed power-backend executable presence; not proof a backend works |
| `plugin_status` | This checkout's plugin IDs/names and enabled state; does not run `pluginctl`, widgets, key helpers or Tailscale |
| `display_status` | Connected monitors and `display-detect list`'s **planned** modes, positions and wallpaper choices, not verified current settings |
| `dotfiles_status` | Local Git branch/tracking/change-path metadata and actual assistant Stow links; no file contents returned, commit, push or fetch |
| `alerts_status` | Current disk/RAM usage against the `[alerts]` thresholds and whether the alert watcher is running; sends nothing, changes nothing |

Invoke directly without using the model:

```sh
assistant="$HOME/.dotfiles/os-assistant/.local/bin/os-assistant"
"$assistant" --tool desktop_status
"$assistant" --tool power_status
"$assistant" --tool plugin_status
"$assistant" --tool display_status
"$assistant" --tool dotfiles_status
"$assistant" --tool alerts_status
"$assistant" --dry-run --tool display_status
```

Status-file reads reject pipes, devices and symlinks (including parent links),
with 128-byte selection / 4096-byte plugin-file caps. The intentional
`themes/out` generation link is allowed only
inside the theme output tree; kernel `/sys` directory links are needed for CPU
attributes. Process/plugin enumeration stops at 2048/256 entries or about one
second, respectively, and partial scans are labelled. Missing/invalid plugin
enabled state is **unavailable**, not disabled;
missing Git output is **unavailable**, not a clean repository. Git output uses
NUL-delimited paths and shows at most 20 changes; monitor output shows at most 8.
The Git pending count counts porcelain records, not every individual file;
untracked directories can be collapsed into one record.

`display_status` trusts only this checkout's fixed `display-detect list` helper,
with trusted-owner/non-writable-by-others source and parents, and root-owned
resolved shell dependencies. Source/dependency changes invalidate prepared calls.
A bounded, validated wallpaper set is passed explicitly so that the shell helper
does not open its own state files. No layout/wallpaper mutation branch is exposed.
Without a supported desktop connection or trusted dependencies it reports unavailable.
This integration trusts repository code; it is not an OS sandbox.

Git disables optional index writes, filesystem-monitor hooks, replacement objects,
rename/submodule scanning, global/system config, lazy fetching and network protocols.
The Git directory and working tree are forced to this checkout, and personal
exclude/attribute files are disabled; linked local exclude metadata is refused.
A fixed, bounded config-key preflight refuses configured filters and includes
without following includes or returning their values. Linked worktrees, linked or
oversized local Git configs, secondary worktree config and untrusted Git metadata
are unavailable. The preflight uses `git config --file` from `/`, not `-C`, because
repository discovery can load includes before `--no-includes` takes effect. Checks are
metadata snapshots, not protection against a compromised user racing execution.

Wallpaper/display changes, screenshots, picom control, plugin enable/disable and
power-mode changes are deliberately **not implemented** in this phase.

### System alerts

`os-assistant --watch-alerts` is a small, model-free loop that sends a desktop
notification when a disk or RAM usage percentage crosses a threshold. It never
calls Ollama or the network and only reads `/proc` and filesystem capacity. Its
state is in memory only, so nothing is persisted; a restart may repeat one
current alert.

- **Usage:** disk percent matches `df` (used / (used + available), so ext4 reserved blocks count as full); RAM is 1 - available/total.
- **Levels:** `ok`, `warning`, `critical`, from the `[alerts]` thresholds
  (defaults: disk 90%/95% for `/`, RAM 85%/95%, checked every 60 s). A level
  rises immediately and clears only once usage is 5 points below its threshold,
  so values near a threshold do not flap. While a metric stays over a threshold
  it is reminded every `repeat_minutes` (60; 0 disables reminders), and one
  low-urgency "back to normal" notice follows recovery.
- **Delivery:** `/usr/bin/notify-send` (app name `os-assistant`) with a fixed
  argv, 5 s timeout and a minimal environment, so popups reach naughty on awesome
  and swaync on Hyprland. The popup id is kept per metric, so updates replace
  the earlier popup instead of stacking.
- **Starting it:** the watcher is read-only and never enables services itself.
  The `system-alerts` plugin starts it from the window manager:
  `pluginctl enable system-alerts`. One instance runs (a lock under
  `$XDG_RUNTIME_DIR/os-assistant/alerts.lock`; a second launch exits 0 silently),
  and it exits when the X or Wayland session goes away or on SIGTERM/SIGINT.
- **Checking:** `os-assistant --check-alerts` evaluates once and prints each
  metric against its thresholds (`--json` for data). The exit status is 0 when
  everything is ok and **6** when any metric is at warning or critical. The
  read-only `alerts_status` tool reports the same plus whether the watcher is
  running, so you can ask "any system alerts?" in chat.
- `--dry-run` is refused, as are prompts, with both alert modes.

### Recursive file sizes

`find_files` already recursively lists the largest matching files and their
relative paths/sizes (at most 20). `directory_usage` measures **real filesystem
metadata**, without reading/copying contents or running a shell. It reports both
logical file bytes (`total_size_bytes`) and allocated file/directory blocks
(`allocated_size_bytes`, using Linux `st_blocks * 512`), plus human-readable values,
cumulative subdirectory totals and optional largest-file sizes.

It is registered for `[paths].allowed_roots` and enabled `[bash].allowed_roots`;
this one-way metadata access never enables Bash for a metadata-only folder.
`root` defaults to the sole approved usage root. `path` selects a subfolder,
default `.`; approved `~/...` aliases work without expanding access.

```sh
assistant="$HOME/.dotfiles/os-assistant/.local/bin/os-assistant"
"$assistant" --tool directory_usage --arguments '{}'
"$assistant" --tool directory_usage --arguments '{"path":"tests","depth":2,"file_limit":5}'
"$assistant" --tool bash --arguments '{"command":"du -sh ~/.dotfiles"}'
```

Recursive metadata scans have separate `[limits]` budgets: **100,000 entries,
10 seconds and depth 64** by default; maxima are 1,000,000 entries, 30 seconds and
depth 128. No 1 MiB file-copy limit applies: large/sparse files use actual size/block
metadata. Deadlines are best-effort between kernel calls, not kernel I/O timeouts.

Results label `scan_complete`, `truncated_scan`, excluded/unavailable entry counts
and `metadata_kind: live_host_metadata_not_snapshot`. Coverage is printed before
potentially long data, so terminal truncation cannot hide an incomplete scan.
Protected paths, symlinks, hardlinks, special files and nested mounts are excluded.
An excluded directory counts as one encountered entry, not all its descendants.
"Complete" means **complete within that permitted view**, not unrestricted `du`
or an atomic filesystem snapshot.

Successful single-call size queries end with a deterministic `result · directory_usage` summary;
the model is not asked to reinterpret numbers or issue another `du` afterward.
Other model explanations remain experimental.

This checkout needed larger local budgets: its permitted-view scan examined about
374,000 entries and reported approximately **30.1 GiB allocated / 29.5 GiB logical
file bytes**, with completeness confirmed. The user's unrestricted `du -sh`
reported **34G**. These are different scopes: the assistant excluded about 165,000
encountered protected/linked/special entries. Values can change with the tree.
Local budgets are now 1,000,000 entries / 30 seconds / depth 64; shipped defaults
remain smaller.

To explicitly authorize a metadata-only folder for a direct invocation:

```sh
assistant="$HOME/.dotfiles/os-assistant/.local/bin/os-assistant"
"$assistant" --allow-root "$HOME/Downloads" --tool directory_usage \
  --arguments "{\"root\":\"$HOME/Downloads\",\"depth\":3,\"limit\":20,\"file_limit\":10}"
```

`depth` (1–8, default 1) controls levels of **reported directory totals**, not
scan recursion: `[limits].usage_depth` limits usage traversal. `limit` (1–20,
default 20) caps directory rows; `file_limit` (0–20, default 0) selects how many
individual files to return. Each directory includes its descendant bytes and
file count. Nested directory totals overlap; **do not sum the rows**. Use
`total_size_bytes` / `files_scanned`, which count each scanned file path once.
Hard-linked files are skipped. Directory rows contain logical file bytes and
allocated file/directory blocks. Empty directories are counted in allocated totals
but have no file data and are not listed as logical-size rows.

`truncated_scan` reports scan bounds/errors; `truncated_directories` and
`truncated_files` separately report output caps. `sample_only` is true when the
scan is incomplete or encounters excluded entries. No file contents are opened.
Search retains its smaller `scan_*` budgets; usage uses the separate `usage_*`
budgets. `--dry-run` previews the
request and skips the scan entirely.

### Web search (optional)

`web_search` is off by default and needs a SearXNG instance that you run
yourself on loopback. Enable it with `[web_search] enabled = true`; `host`
(default `http://127.0.0.1:8888`) must be an HTTP loopback IP with a port, the
same rule as the Ollama host, and `timeout` is 1-30 seconds (default 10).

- Arguments: `query` (1-256 characters) and `limit` (1-10, default 5).
- Every search asks for a typed `yes` that shows the exact query and SearXNG
  host, so non-interactive `--tool web_search` is denied. It is refused in a
  turn that already ran another tool and in multi-call batches.
- The model writes a short summary from the snippets in a zero-tool call that
  treats snippets as untrusted data. The real title/URL list from SearXNG is
  always shown under it. Chat history keeps only a stub, never web text.
- `--dry-run` sends nothing.
- Privacy: the assistant only talks to loopback, but SearXNG forwards the query
  to public search engines (on this machine, over the Mullvad VPN). The Bash
  sandbox stays offline.

Setup is manual. Install SearXNG from the AUR (`searxng-git`) or a container,
for example:

```sh
podman run -d --name searxng -p 127.0.0.1:8888:8080 docker.io/searxng/searxng
```

Enable the JSON API in SearXNG's `settings.yml`, otherwise the tool reports a
403 hint:

```yaml
search:
  formats: [html, json]
```

Bind SearXNG to 127.0.0.1 only.

### Theme control (`themectl`, not `themeclt`)

Opt into `[themes].enabled = true` to trust **this checkout's** `themes/themectl`
pipeline. `theme_status` lists available layouts/palettes and current selections.
`set_theme` additionally requires `[actions].enabled = true` and typed `yes` for
each change. Its only arguments are an existing `layout`, `palette`, or both:

```sh
assistant="$HOME/.dotfiles/os-assistant/.local/bin/os-assistant"
"$assistant" --tool theme_status
"$assistant" --dry-run --tool set_theme --arguments '{"palette":"nord"}'
"$assistant" --dry-run --tool set_theme --arguments '{"layout":"mono","palette":"nord"}'
"$assistant" --dry-run --tool apply_theme
```

Dry-run does **not** execute `themectl`, render previews, create generations or
reload apps. It validates the names, trusted source metadata and exact argv;
it cannot establish that rendering, IPC or app reloads will succeed. Layout
changes require a live AwesomeWM session; palette-only changes also work in
Hyprland. Selecting an existing palette is supported; arbitrary RGB edits,
palette imports, `next`, and arbitrary helper paths/subcommands are not.

`apply_theme` is the zero-argument theme-reapply mutation: it takes **no arguments** and
uses exactly this checkout's `themectl apply` to re-render/reload the current
color palette, without selecting another one or switching desktop layouts.
Like `set_theme`, it requires both opt-ins, an exact command preview and typed
`yes` on every invocation. A dry-run executes nothing; validation has not applied
the real theme or restarted the desktop.

This is a narrow **exception to general configuration-editing restrictions**:
the helper renders app configs, updates links/state, executes repository Lua and
hooks, and runs the repository's reload commands (including shell commands and
possible desktop restarts). Enabling themes explicitly trusts that code as your
user, including its normal config reads and internal temporary-file cleanup.
It does not give the model a shell tool or enable privileged installation.

Known source/dependency metadata is checked for trusted ownership and permissions
and fingerprinted before/after approval. Changes invalidate a prepared request.
The pipeline is bounded to 120 seconds by default (`themes.timeout`, 10–180).
This is not a sandbox or a complete transitive code-integrity guarantee; a
compromised account can still race execution. A nonzero exit, timeout or reported
stderr warning is an error **even if some changes were already applied**. No
automatic retry or rollback is attempted. Check `theme_status` and inspect the
desktop before deciding what to do next; success never verifies visual appearance,
and the helper can silently ignore some reload failures.

### --probe

`--probe` requires a running local Ollama server and the installed MiniCPM5-2B
model (the exact configured tag). It sends 32 public, predefined requests to the
**real model**, scoring the first
tool choice and normalized arguments against a >=90% goal, and reports latency
per request. Its synthetic tools never execute and its example folder is not
scanned. Unit tests mock the model; they are not evidence of real-model accuracy.
A passing routing score is a usability gate, not a safety guarantee. If it fails,
stop and reassess rather than weakening permissions or switching models silently.
**Model-driven requests remain experimental:** MiniCPM passed the tuned 32-case
set but failed the separate 10-request check. Prefer direct `--tool` commands
for predictable diagnostics. Do not enable actions based on the tuned score.
The following model scores predate theme tools and the expanded size schema;
they are not validation of the new optional tools. The built-in 32-case probe
still tests only its original read-only routing cases, with machine-specific
status/theme/action tools excluded from its synthetic schemas.

An additional 12-request, non-executing check with themes/actions enabled and
the expanded size schema scored **9/12 (75%)**, below the target. Its misses
were an empty optional palette (rejected), confusing directory `limit` with
individual `file_limit` (valid but incomplete output), and unrelated read-only
lookups for an unsupported custom-color-file edit. This checked only first-call
routing, not explanations or action success, and no proposed tools were run.
That failed score is retained; the subsequent status additions are a different
expanded tool set. Use explicit `--tool` commands
for the new capabilities; the policy does not guarantee intent matching.

A subsequent **26-request** check with all five status tools and `apply_theme`
offered scored **16/26 (61.5%)**, below the target. It reused the prior 12 requests
and added status/apply requests and unsupported desktop actions; this is not a
blind holdout. Misses included an unrequested palette with a layout change,
brightness/reapply approval prose instead of a tool proposal, confusing directory
`limit` with `file_limit`, redundant read-only calls, asking `display_status` for
the saved wallpaper-set name, and status lookups for unsupported plugin/power/
wallpaper changes. No proposed tools executed, and no further tuning followed.

The score grades first structured calls/arguments only. In particular, the
custom-color-edit request scored a pass because there was **no structured tool
call**, even though its prose promised a theme lookup rather than refusing the
unsupported edit. A correctly scored palette call also invented a layout in its
prose, and a reapply reply invented the current theme. These are not successes
in explanation accuracy or end-to-end behavior. Raw evidence and all failures
are retained locally at `/tmp/opencode/os-assistant-status-tools-zlf8n30d.json`;
the non-executing harness is `/tmp/opencode/os-assistant-status-tools-probe.py`.

The Bash expansion's **44-request** non-executing recheck (the previous 26 cases
plus 18 Bash requests) was blocked before inference: local Ollama was unreachable
at `127.0.0.1:11434`. At that point **no new routing score or end-to-end model
validation was available**, and the failed scores above still applied. No server/service was
started and no model was substituted. The new harness is
`/tmp/opencode/os-assistant-bash-tools-probe.py`; it validates schemas and pure
command plans only, never executes proposals or probes the fictional folders.

Deterministic Bash validation did execute `ls` and a `grep | head` pipeline in
this checkout's read-only sandbox: the listing copied no contents and the search
copied only README.md. Disposable fixtures validated network/host-path isolation,
read-only mounts, strict grammar/flags, credential/link/mount exclusions,
confirmation and supported file operations. A real-checkout `touch` was previewed
only; **no live checkout file mutation through the tool was tested**.

After the recursive-size/argument fixes, a new 12-request first-call check scored
**10/12**, while a constrained four-turn real-read conversation passed **1/4**.
The failures exposed a `~/` guess for "this directory", repeated `ls` calls after
context-shortened output, and a structured attempt to read `.env` (policy blocks it).
Raw evidence is retained at `/tmp/opencode/os-assistant-size-routing-j_6cnqnl.json`.

Adding explicit approved-folder context and deterministic Bash-read completion
then made that same **four-turn live conversation pass 4/4**: the user's initial
size question, `~/.dotfiles` follow-up, `use ls in ~/.dotfiles`, and explicit
`ls -lh .`. Each turn executed exactly one read-only tool; the two size scans were
complete within the permitted view and no source contents or mutations ran.

The separate first-call recheck was nevertheless **9/12 (75%)**, below target.
Misses were a duplicated `.dotfiles` subfolder, dropping the requested `head -n 5`
pipeline, and proposing protected `.env` access instead of refusing without a
call. These are retained failures, not a general success claim. The changes were
informed by known failures; neither set is a blind holdout, and refusal prose is
not semantically graded. At that checkpoint no further tuning had followed. Prefer direct
`--tool` for predictable behavior; the policy does not guarantee intent matching.
Checkpoint raw evidence: `/tmp/opencode/os-assistant-size-routing-_pz0h10w.json`;
harness: `/tmp/opencode/os-assistant-size-routing-probe.py`. Local Ollama was
already running; no model substitution/download or service startup was used.

The next iteration added complete literal-command comparison and explicit
protected-path guidance. Its first-call check remained **9/12**, and the expanded
seven-turn live check passed **5/7**: exact pipelines worked, but the model added
unsupported `du --max-depth` flags in two size turns. These remained blocked,
not auto-corrected or permitted. Evidence:
`/tmp/opencode/os-assistant-size-routing-5mql50ds.json`.

Whole-folder examples and `du` flag guidance then kept first-call routing at
**9/12** and live routing at **4/7**. The model falsely treated `~/.dotfiles` as
outside the approved folder and repeated that claim from history; first-call
misses also included an empty path, command `.` and a dropped pipe. These failures
are retained at `/tmp/opencode/os-assistant-size-routing-1fmv4ll7.json`. The final
follow-up adds an explicit approved-alias mapping rather than widening access.

With the approved-alias mapping, the final local recheck scored **10/12** on raw
first calls and **5/7** on the expanded live conversation. The initial recursive
size query, both plain `ls` requests, allocated/logical-size request and protected
file refusal passed. The bare folder follow-up generated an unsupported shell
chain, and the explicit pipeline lost `head -n 5` twice, including after its one
correction opportunity. **Neither failed turn executed a tool.** First-call
misses remained an empty usage path and a dropped pipe. Raw evidence:
`/tmp/opencode/os-assistant-size-routing-ncyulgin.json`.

The same frozen prompt/config profile was then evaluated once against two
non-executing fixture groups:

| Set | Result | Scope |
| --- | --- | --- |
| Independently authored requests | **16/24 (66.7%)** | Fictional sole Bash root; smaller tool set; reads, sizing, confirmed mutation proposals and refusals |
| Expanded previous requests | **29/44 (65.9%)** | Fictional metadata/Bash roots, all status/theme tools and configured actions |

Neither meets the **90%** target. The independently authored fixture is not a
blind holdout: its worker accidentally saw a few in-progress agent lines and the
lead reviewed the cases before inference. Scoring preserves flags, paths, pipe
stages/counts and requested report fields; extra checks or missing proposals can
fail the score even when harmless. Refusal prose is not semantically graded.
Policy-blocked proposals remain routing failures, not successes. These probes
perform only pure schema/grammar checks: no root probes, approvals, model-selected
tools or mutation operations execute. Runtime preparation can impose additional
refusals that this first-call scorer does not inspect.

All three final groups used the installed tag/digest above with unchanged model
settings; no further prompt tuning or permission relaxation followed them.
Diverse raw evidence: `/tmp/opencode/os-assistant-intent-diverse-nhvecoah.json`;
fixture: `/tmp/opencode/os-assistant-intent-holdout-cases.json`;
harness: `/tmp/opencode/os-assistant-intent-diverse-probe.py`.

These are historical raw-model routing results, recorded before local natural
folder-size routing was added. They do not measure the new deterministic chat
path; its regression and live conversational checks are recorded separately.

Complete literal-command validation improves fail-closed behavior; it does **not**
make MiniCPM's general natural-language routing reliable. Direct `--tool` remains
an optional diagnostic interface for an exact supported command, without relying on
the model to copy it:

```sh
~/.dotfiles/os-assistant/.local/bin/os-assistant --tool bash \
  --arguments '{"command":"ls -lh . | head -n 5"}'
```

Final repository validation passed **1,531 tests and 551 subtests**, plus syntax,
ShellCheck and whitespace checks. An earlier full run during inference timed out
in an unrelated isolated tmux persistence test; its focused rerun and the final
full run both passed. No production file mutation or desktop restart was tested.

Direct local checks verified theme status, a non-executing combined-theme
preview, and recursive per-directory/per-file size output on an owned fixture.
**No real theme change or desktop restart was tested.** Existing palette/layout
selection remained unchanged. Dry-run cannot prove a real change will complete.

Direct checks also returned all five new status results and an `apply_theme`
preview without applying the real theme. The real-home Stow simulation refused
to overwrite the existing local `config.toml`; no assistant links were applied.
Use the checkout launcher or resolve that conflict manually before installing.

### Measured local profile — MiniCPM5-2B, previous default (2026-10-09)

CPU-only Ryzen 7 PRO 5850U laptop, Ollama 0.40.1, the installed Q4_K_M artifact
identified above, 4096 context, thinking requested off, temperature 0 and
512 output tokens:

| Check | Observed result |
| --- | --- |
| Initial first-call routing | 27/32 (84.4%); failed the target |
| Clarified tool descriptions, unchanged 32 requests | 32/32 (100%); passed the fixture target |
| Separate 10-request set, unchanged from the Qwen trial | 8/10 (80%); failed the accuracy target |
| Cold first tool decision (model not resident), revised run | 11.3 seconds |
| Warm tool decisions, median across mixed requests, revised run | 2.2 seconds |
| Warm tool decisions, slowest in that run | 7.2 seconds |
| Complete memory-query flow (tool plus explanation) | 19.5 seconds |
| Complete approved-fixture file-search flow | 8.5 seconds |

The separate phrases were not used for MiniCPM instruction tuning, but were
already known from the Qwen evaluation: this is a small comparison set, not a
blind holdout or a general accuracy claim. Routing tests execute no OS tools and
do not grade refusal prose. The cold/warm rows measure **tool decisions, not
complete tasks**; mixed prompts, caching and system load affect comparisons.

The two additional routing misses were `find_files` with `limit: 100` (policy
rejects it; maximum 20), and a read-only `processes` lookup for a request for full
command lines/environment variables. That lookup is within the tool policy but
cannot return the requested private details. The policy bounds capabilities;
it does not guarantee that every allowed lookup matches the user's intent.

Live smoke checks verified system-status execution, metadata-only owned-fixture
search with symlink exclusion, non-executing dry-run and no tool calls for
deletion. **Those checks did not validate explanation accuracy.** MiniCPM
misstated the total RAM despite receiving the correct bytes and misinterpreted
dry-run as missing tool data. Read the deterministic tool results and
`status: preview`, not unsupported model prose. No live app, volume or brightness
actions were tested; actions remain disabled by default. The user's local opt-ins
are separate from these test results. Further tuning stopped after the
separate-set failure.

### Measured local profile — HISTORICAL QWEN BASELINE (2026-10-09)

**HISTORICAL QWEN BASELINE — these are not MiniCPM5-2B results.** Every score,
timing and digest in this subsection was measured with the previous model,
`qwen3.5:2b-q4_K_M`, which this version no longer runs. They are kept as an
honest record of that trial and must not be read as MiniCPM5-2B measurements.

One CPU-only laptop trial (Ryzen 7 PRO 5850U, Ollama 0.40.1), using the exact
selected Qwen tag of that trial, 4096 context, thinking disabled and temperature 0:

| Check | Observed result (HISTORICAL QWEN BASELINE) |
| --- | --- |
| Initial first-call routing | 28/32 (87.5%); failed the target |
| Revised instructions, unchanged 32 requests | 31/32 (96.9%); passed the target |
| Additional requests not used for instruction tuning | 7/10 (70%); failed the generalization check |
| Cold first tool decision (model not resident) | 10.1 seconds |
| Warm tool decisions, median across mixed requests | 7.2 seconds |
| Warm tool decisions, slowest in that run | 10.2 seconds |
| Complete memory-query flow (tool plus explanation) | 18.2 seconds |
| Complete approved-fixture file-search flow | 14.6 seconds |

Model artifact digest of that historical Qwen baseline:
`1e2d21a4f03ab9e4a9c1976a4b7e88f21de61d65f2c5485d8fde8942be73f1e7`.
The cold/warm rows are **tool-decision timings, not complete task times**. The score reflects
instruction tuning on this fixture set; it is not a general accuracy claim, and
refusal prose is not semantically graded. **Model-driven requests remain
experimental: the additional phrases failed the accuracy target.** Observed
misses included a dropped filename filter, an unrelated read-only lookup for a
move request, and a process limit of 100, which the policy rejects. Prefer direct
`--tool` commands for predictable diagnostics. Do not enable actions on the
strength of the tuned fixture score. One unsupported process-killing
request still triggered a read-only lookup. There is no process-killing tool,
and the permission layer remains independent of model correctness. Actions
remain disabled by default. Performance varies with load and prompt length.

The complete live checks of that same HISTORICAL QWEN BASELINE trial covered
system status, metadata-only fixture search, dry-run and refusal of deletion.
No live app, volume or brightness actions were
tested. Dry-run executed nothing, but the model's explanation confused preview
mode with a missing capability; the deterministic `status: preview` is the
authoritative execution record, not that prose.

To test the CLI without Ollama:

```sh
os-assistant --tool system_status
os-assistant --tool processes --arguments '{"limit": 5}'
os-assistant --dry-run --tool system_status
```

## Configuration

`~/.config/os-assistant/config.toml` is strict TOML: only the sections and keys
shown below exist, and anything else is rejected. Keep secrets out of it.

```toml
[model]
name = 'qwen3:4b-instruct-2507-q4_K_M'
host = 'http://127.0.0.1:11434'   # loopback only; remote hosts are rejected
context = 8192
keep_alive = '2m'                   # 0, 30s, 1m, 2m, 5m or 10m
timeout = 180
max_output_tokens = 768            # 256–1024 generated tokens per reply

[paths]
allowed_roots = []                 # opt in, e.g. ['~/Downloads']

[actions]
enabled = false                    # opt in; each call still needs a typed 'yes'
apps = {}                          # e.g. { firefox = '/usr/bin/firefox' }

[web_search]
enabled = false                    # opt in; needs your own loopback SearXNG, typed 'yes' per search
host = 'http://127.0.0.1:8888'     # HTTP loopback IP with a port
timeout = 10                       # seconds, 1-30

[themes]
enabled = false                    # explicit trust in this checkout's theme pipeline
timeout = 120                      # seconds, 10–180; separate from ordinary tool timeout

[status]
enabled = ['desktop_status', 'power_status', 'plugin_status', 'display_status', 'dotfiles_status', 'alerts_status']
# Remove names to disable individual tools; [] disables all six.

[alerts]
interval = 60                       # seconds between checks, 15-3600
disk_paths = ['/']                  # up to 8 absolute paths (~/... allowed)
disk_warning_percent = 90           # used %, 50-99
disk_critical_percent = 95          # 51-100, must exceed the warning value
memory_warning_percent = 85         # 50-99
memory_critical_percent = 95        # 51-100, must exceed the warning value
repeat_minutes = 60                 # reminder interval while over a threshold, 0-1440; 0 = none

[bash]
enabled = false
allowed_roots = []                  # explicit content-read approval; NOT shared with [paths]
allow_writes = false                # also requires actions.enabled and typed yes for every call

[limits]
max_steps = 6
tool_timeout = 5
scan_entries = 3000
scan_seconds = 3
scan_depth = 8
usage_entries = 100000              # real recursive metadata, separate from snapshots/search
usage_seconds = 10
usage_depth = 64
```

## Safety notes

- Model output never grants authority: the policy layer decides what runs, and
  the model only proposes calls.
- No default arbitrary-folder access (empty `allowed_roots`) and no default action access
  (`enabled = false`); the theme integration is also off by default.
- Machine-specific status reads use fixed paths and can be disabled individually;
  they never expose arbitrary helper paths or additional mutation commands.
- Bash roots explicitly grant ordinary content reads in a filtered, bounded copy;
  automatic commands cannot write the source folder. Supported writes need both
  opt-ins and per-call approval; unknown shells/scripts remain blocked even then.
- Loopback-only model host and no telemetry. Web search is off by default; when
  enabled, each query needs a typed `yes` and goes via your local SearXNG to
  public search engines.
- No conversation history or activity logs are persisted; a session ends when
  the process does. Approved file/theme actions do persist their normal changes.
- No secrets live in this package or its configuration.
- Common credential filenames and protected directories are skipped; this
  denylist cannot identify every sensitive filename. Approve narrow folders,
  not your whole home directory. Tool outputs and scans are bounded.
- Only Bash read commands have an OS sandbox; the overall CLI/actions do not.
  Approved apps run as your
  user and can read their usual profiles; allowlist only apps you trust. Closing
  the assistant does not undo completed actions or close launched apps.
- Theme opt-in trusts user-owned repository code rather than weakening the
  root-owned executable requirement for generic app launching. Theme dry-runs
  never execute the helper; real changes can affect multiple apps and the desktop.

## Tests

```sh
python3 -B -m pytest tests/test_os_assistant_*.py
```

The suite covers the Stow helper (preview mutates nothing, `--apply` links,
conflicts fail, relative `--target` and unknown flags are rejected) and the
launcher/entry point (relocated trees, paths with spaces, symlinked launcher,
isolated interpreter) using throwaway fixture homes and a copied package —
never your real `$HOME`.
