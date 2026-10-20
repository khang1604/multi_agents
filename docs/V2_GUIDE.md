# Multi Agents V2: setup and IDE chat

## Giao việc trong chat, ít dùng CLI

1. Chạy `setup.ps1` một lần; chọn launcher và cài @hub vào VS Code Copilot Chat.
2. Trong terminal của source được phép, chạy `ma init`. Xác nhận source/synthetic/
   không gọi API ứng dụng cho project này. Init giữ scope ngoài repo, không thay
   đổi yêu cầu cách ly OS đã chọn. Cần Git baseline sạch và dependencies đã chuẩn bị.
3. Init nhận diện verifier và SDK Android khi có, lưu riêng biến SDK cho worker và
   verifier trong worktree. Chạy baseline trong worktree riêng và kiểm tra stdio MCP.
   Test lỗi thì dừng tại đây, chưa tốn lượt gọi AI; log ở home của Hub.
   Với Codex Windows, init còn chạy một lệnh in chuỗi cố định trong sandbox, không
   gọi model. Executor lỗi thì yêu cầu sửa setup sandbox trước; worker cũng kiểm tra
   lại trước khi tiêu call. Không tự chuyển sandbox, bật bypass hoặc cấp thêm calls.
4. Reload VS Code sau lần cài extension, mở Copilot Chat và nhập `@hub /agents`.
   Giao việc bằng `@hub Thêm tài liệu hướng dẫn chạy dự án, kiểm tra thay đổi`.
   Participant sticky nên thường không phải gõ lại @hub ở lượt kế tiếp.

Setup cũ có thể cài bridge bằng `ma integrations chat --apply`. Extension chỉ dùng
Node runtime có sẵn trong VS Code; người dùng không cần npm install hay Python package.
Nó gọi Hub qua stdio, không đọc source/history chat hoặc gọi model của chat IDE.
Hub vẫn dùng CLI provider đã đăng nhập và quota của chính provider đó. Extension chưa
được kiểm chứng trong UI Copilot khi tài khoản hết quota; không cam kết vượt cơ chế
giới hạn của IDE. Khung chat riêng của Antigravity chưa có API bridge được xác minh.

Lệnh chat: `@hub /status`, `/watch`, `/agents`, `/retry`, `/cancel`. Có thể thêm ID
workflow sau lệnh; ID phải thuộc project đang mở. Retry giữ nguyên call cap. Nút dừng
chat chỉ đóng theo dõi; `/cancel` mới yêu cầu dừng workflow. Workflow đang waiting
quota sẽ trả checkpoint và thời gian thử lại, không giữ chat/poll model liên tục.
Prompt mới khi project đang có workflow chưa kết thúc sẽ không tạo task trùng.
Những câu hỏi tiếp theo được coi là task mới, không tự gửi toàn bộ lịch sử chat.

## Setup

Requirements: Python 3.11+, Git, Windows PowerShell/CMD/Windows Terminal. The Hub itself
uses only Python standard library. Provider CLIs and project dependencies are separate.

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
```

If PowerShell blocks scripts, use `py -3 ma.py setup`; do not bypass ExecutionPolicy.
The wizard checks prerequisites, lists CLI discoveries, selects agents (Space/Enter
with arrows or j/k on an interactive Windows terminal), model policy and roles. A
basic input fallback works without advanced TUI support. Keep selection unchanged
by keeping current values; deselecting every agent is valid but cannot code a task.

Choose the model policy once for all selected agents. Native AUTO capability is still
checked separately; one explicit fallback approval covers selected agents without
native AUTO. Roles are kept automatically. Per-agent model/role questions appear only
after opting into Advanced customization. Invalid role input is corrected in place;
press Enter (do not type the help text) to keep current roles. MANUAL applies one
model ID only when every selected provider advertises it; otherwise use INHERIT or
Advanced settings to choose different provider-specific models.

The wizard asks separately before installing the owned `ma` launcher or changing a
client configuration. It never installs/logs into providers, changes security
attestations, starts a paid task or enables autostart. Failures restore prior Hub
configuration and attempt to undo newly owned launcher/client entries. Backups remain;
any rollback needing manual review is stated. A changed user-owned entry is preserved.

After installing the user PATH entry, open a new terminal. `ma --help` works anywhere;
`ma` opens the terminal menu. The launcher pins the chosen interpreter and home.
An existing different `ma` command causes refusal, not an overwrite. The V1 `hub`
launchers remain callable by explicit source path. Installing the owned V2 launcher
backs up the user PATH and removes this same checkout's legacy PATH entry, keeping
one pinned `ma` launcher first. Other tool paths are retained; existing terminals
must be reopened to receive the updated user PATH. Percent signs in CMD launcher installation paths are explicitly
unsupported; Unicode and spaces are supported.

## Discovery and authentication

All `ma` commands show compact plain text by default, including setup and logs.
For scripts or full diagnostics, append `--json` (for example `ma config --json`).
Existing scripts parsing the former JSON defaults must add this flag. Interactive
setup/configure remain plain text; `mcp` keeps its JSON-RPC protocol and `mcp-config`
keeps importable JSON. `diff` shows the requested patch; use `diff --json` for export.
Monitoring shows the latest three attempts and two events without raw JSON payloads;
use `status --json` to obtain the full persisted snapshot.

```powershell
ma agents list
ma agents list --check
ma agents list --check --json
ma doctor --offline
ma doctor
```

Agent lists use one header and one line per agent, including enabled state,
discovery state, authentication, model policy and a short Vietnamese reason. Reasons
distinguish disabled agents, missing CLI/PATH, missing login, unverified login,
probe errors and an unrecognized adapter. UNKNOWN is not proof of a failed login.
Add `--json` for full diagnostics;
`--check` still caches all details. READY does not confirm quota or a live model call.

On Windows, Antigravity discovery also checks `%LOCALAPPDATA%\agy\bin\agy.exe`,
the official installer location, even if the current terminal still has its old PATH.
To use `agy` directly after installation, reopen the terminal or temporarily add that
directory to `$env:Path`. IDE login alone is not CLI authentication evidence; the
current Antigravity adapter keeps authentication UNKNOWN when it cannot verify it.

After you personally receive a successful AI reply, record that report with:

```powershell
ma agents confirm antigravity --worked
ma agents list --check
# To remove the report:
ma agents confirm antigravity --revoke
```

This makes the state READY, with a short operator-confirmed reason and no daily
expiry. CLI/protocol checks must pass first. Authentication remains UNKNOWN unless
an official auth probe verifies it, and live_verified stays false: this records your
report, not an automatic model test. No prompt is sent. The external home stores
only the confirmation time and a command/binary/model fingerprint, without response payloads
or credentials. Changing the binary, command or model invalidates the report;
missing CLI, failed probes, lost protocol or negative auth evidence take priority.
Existing expiring reports keep their expiry until explicitly confirmed again.
Terminal lists, setup and MCP read the same reports. These reports do not alter
workflow security attestations, permissions, provider health or execution budgets.

Without `--check`, discovery only resolves executable paths. Checks run bounded
official version/help/auth-status commands in a temporary working directory, never
an AI prompt. Raw auth output/account identifiers are discarded. Credential files,
cookies, IDE login state and provider history are not inspected.

| State | Meaning |
|---|---|
| NOT_INSTALLED | No resolvable execution command |
| INSTALLED | Executable found; no successful authentication evidence yet |
| AUTHENTICATED | Official auth probe confirms login; adapter protocol not detected |
| READY | Auth probe succeeds or operator confirms an AI reply with a checked adapter; see confirmation_source; quota/live execution unverified |
| UNKNOWN | Authentication cannot be verified noninteractively with the implemented probe |
| UNAVAILABLE | Safe probe failed or timed out |

Codex uses `login status`; Claude uses JSON `auth status`. Copilot and Antigravity
authentication currently remain UNKNOWN, rather than scraping or making paid calls.
Run the login hint manually only when needed. An IDE install/login is not proof of
CLI install/login; MCP client availability is also separate from provider capability.
No live provider/client execution has been verified by V2 tests.

## Agents and model policy

```powershell
ma agents configure
ma agents disable copilot
ma agents enable claude
ma agents disable codex --project my-app
ma agents models
ma agents model codex INHERIT
ma agents model copilot AUTO
ma agents model claude AUTO --fallback INHERIT
ma agents model codex MANUAL --model PROVIDER_REPORTED_ID
```

INHERIT sends no model flag, even if an older model value is still saved. It does not
read or change the model selected in an IDE. AUTO uses a verified adapter capability
(currently Copilot `--model auto`); unsupported AUTO needs explicit INHERIT fallback.
MANUAL requires a model ID in the catalog advertised by the provider help probe and
cached by `agents list --check`. No hardcoded model list or paid catalog probing is
used. Some versions expose no machine-readable catalog: use Provider Default or an
explicit fallback; do not claim their models were validated. Legacy `model` entries
without a policy retain their previous behavior.

When a chosen model becomes unavailable, only an explicitly selected INHERIT fallback
can switch that workflow to Provider Default. The event is persisted, the retry
consumes the existing call budget, and global/IDE model settings remain unchanged.
Actual model metadata is stored per attempt only when the provider reports it;
configured model and actually used model are different evidence.

Codex/Claude may implement; Antigravity/Copilot remain planner/reviewer adapters.
Thus Antigravity+Copilot alone cannot code and is refused without spending a planning
call. A single coding provider can self-review for standard work, explicitly marked
as non-independent. Complex work requiring two different reviewers remains
needs_review if the combination cannot provide them. Disabled agents never fail over
back into the pool. Project overrides can restrict global settings, not reenable a
globally disabled provider. Changes are refused while any workflow is active rather
than interrupting a writer. Role configuration is offered by the terminal wizard.

## Initialize an approved project

```powershell
cd C:\Projects\MyApp
ma init
ma context
ma projects list
```

`ma init --register-only` (or `--json`, or redirected/noninteractive output) resolves
Git root, identifies language/framework/dependency metadata and bounded documents,
stores hashes/version locally, and does not execute project build/test scripts.
Interactive `ma init` additionally confirms scope and runs baseline checks as above.
Facts and AI inference are separate. Context
refreshes only when relevant hashes change; `ma context` reports stale status.
Context Packs reuse shared metadata and selected excerpts, not the full codebase.

No .ma/.ai metadata, AGENTS.md, .gitignore, MCP file, hooks, Git config edits or temp
files are created by init inside the repository. A clean Git status stays clean.
Worktrees used for coding live under the external Hub home. Git's own worktree
administrative records are necessary during coding and interactive baseline checks.

Command detection is heuristic. If a command cannot be selected, init still creates
an unconfigured registration and dispatch is blocked. Fill missing commands explicitly:

```powershell
ma init --verify '[["dotnet","build","App/App.csproj","--no-restore"]]'
```

For one command, avoid JSON quoting entirely with `--verify-command`, placed last:

```powershell
ma init --verify-command dotnet build App/App.csproj --no-restore
# Android/Gradle example, if this task exists in the project:
ma init --verify-command cmd.exe /d /c gradlew.bat --offline testDebugUnitTest
```

Register-only initialization records the command without executing it; interactive
initialization runs the baseline before reporting PASS. Gradle offline mode requires cached
dependencies; a missing cache is a failed prerequisite, not a passing test. Existing
verification settings remain protected from accidental replacement.

V2 also detects Gradle wrappers in nested projects, including untracked files in a
new Git repository. Detection uses filenames only: one wrapper with Gradle project
markers and unit-test sources produces an offline `test` command using a relative
`--project-dir`. Multiple candidate builds or missing test sources require an
explicit command. Root and nested paths with spaces are supported. Initialization
checks named Gradle wrapper/project paths before saving. Interactive init may repair
a missing stored Gradle wrapper path only when one valid verifier is detected, with
backup; valid custom commands remain unchanged. The register-only mode never executes Gradle.

To intentionally repair a previously stored verifier, preserve the project/history
and save the previous command with:

```powershell
ma init --replace-verify --verify-command cmd.exe /d /c SkillNovaApp\gradlew.bat --project-dir SkillNovaApp --offline testDebugUnitTest
# Or redetect a single supported build:
ma init --replace-verify
```

Replacement is blocked while any workflow is active. Cached context also receives
the updated verifier. `Tests configured: yes | Tests run: no` means the command has
been saved, not passed. Offline errors about missing cached JUnit/coroutines or
other artifacts mean dependencies must be prepared before verification can pass;
Hub does not silently switch to online mode, change network/security permissions,
or count a failed build as a successful check.

This example verifies compilation, not behavior/unit tests. Choose actual test
commands for your project. An existing nonempty command list is not overwritten by
init. PowerShell 5.1 quoting may require PowerShell 7 or using a small Python script
calling `initialize()` with a list of argument arrays. No fake always-success command
is installed. Changing unknown/unsafe scripts into trusted test commands is an
operator decision.

`ma projects remove NAME` marks registration removed and preserves source, history,
worktrees and deliveries. It refuses active workflows. Explicit `ma init` in the
same repo can re-register it without losing its stable identity/history.

## Dispatch and monitoring

```powershell
ma run "Add status filtering and meaningful tests" --max-calls 6 --request-key filter-1
ma run "Add status filtering" --project my-app --mode standard --max-calls 6
ma status --watch
ma logs
ma diff
ma cancel WORKFLOW_ID
ma retry WORKFLOW_ID --extra-calls 2
```

Registered source must be committed and clean before creating a coding worktree.
No automatic commit/stash/reset, dependency install, merge or push occurs. Synthetic
data/source approval and the existing security gate still apply. Setup does not
confirm them. Isolation is required only when the operator requires it, per SECURITY.

The existing engine runs plan -> implement -> verify -> review, repairs and failover.
New standard/complex configs permit up to 3 repair rounds; the CLI-call cap is still
hard and may stop the workflow sooner. Old configs keep their own budgets. One CLI
launch may make several provider requests; this is not an exact token/USD cap.

The monitor derives agent/role/model, task, repairs, elapsed time, checks, changed-file
events and failover from SQLite. Unknown values remain unknown; no percentage or LLM
status guesses. Ctrl+C closes monitoring without cancelling the daemon/workflow.
Logs/diff default to the latest workflow for the current registered project. Specify
an ID to inspect a different one. Completed code is in a verified ZIP or retained
worktree; the user's original working copy is not automatically changed.

## MCP and multiple entry clients

```powershell
ma integrations command antigravity
ma integrations install antigravity --apply
ma integrations install vscode --apply
ma integrations install copilot --apply
ma integrations install claude --apply
ma integrations install codex --apply
ma config --default-client vscode
```

Without `--apply`, these commands only preview. The operator chooses each client;
there is no mandatory default. JSON clients receive only an owned `multi_agents`
stdio entry in their official user configuration, preserving other servers/settings
and backing up existing files. Different entries with the same ID are refused.
An empty/whitespace-only configuration is treated as a new document and still
backed up; UTF-8 BOM input is supported. Invalid JSON or a non-object server map is
preserved and rejected. The installer never overwrites malformed configuration.
Codex is registered with its official `codex mcp add` CLI and a backup of config.toml;
non-MCP settings are not parsed or printed. Client-owned credentials are not copied
into Hub JSON. Client configuration may need a reload/refresh and tool trust approval.
Generated configuration is not proof of an active IDE connection. Refresh the MCP
manager and check its tool list. Chat-driven tool calls also need the chat model's
quota; `ma run` submits workflows directly and is not an MCP installation command.

User config targets: Antigravity `~/.gemini/config/mcp_config.json`; VS Code
`%APPDATA%/Code/User/mcp.json`; Copilot `$COPILOT_HOME/mcp-config.json` or
`~/.copilot/mcp-config.json`; Claude `~/.claude.json`. All Hub integration receipts
live outside user projects. `ma integrations remove CLIENT` removes only the exact
owned entry, refuses changed entries, and leaves unrelated settings alone.

Tools: list_agents, get_agent_status, get_agent_models, set_agent_enabled,
set_agent_model, initialize_project, get_project_context, dispatch_task,
get_workflow_status, get_workflow_events, cancel_workflow. All seven V1 names remain.
initialize_project only refreshes a pre-registered project, never arbitrary paths.
Config mutation is blocked by default; the operator can explicitly grant
`ma config --allow-mcp-config true` (revoke with false). Security/commands are not
MCP-configurable. Every client uses the same home, Store, context and Engine. Use a
stable request_key across retries; executing workers cannot dispatch recursively.

First connection check, after the user signs into their chosen client: ask it to
call projects_list and recover_context only. Verify the actual tool response before
dispatch. A usable initial prompt is: "Use Multi Agents MCP. Recover this registered
project first. Dispatch my task using enabled agents and a stable request key. Do
not implement directly or start duplicate workflows. Report verification evidence."
Client chats without supported MCP should use `ma run`, not pretend to be connected.

## Background operation, update, migration and removal

```powershell
ma start
ma stop
ma restart
ma update
ma update --apply
ma uninstall
```

The daemon uses hidden local processes, PID/lock/generation fencing and stdio. No
network listener, Windows Service, Administrator privilege or automatic Windows startup
is added. Closing a menu/client does not cancel an already authorized task. Restart
waits for the old daemon to stop before starting another; a timeout preserves state.

Update refuses a dirty source tree, never resets/stashes user changes. Preview makes
no network call; explicit --apply runs fast-forward-only Git update. Application data
is external, retained, and not migrated merely by fetching new source. Uninstall
removes only the exact owned launcher/PATH entry, preserves all data/projects/provider
installs and leaves client removal to explicit integrations remove commands.

V1 default `data/` remains untouched. V2 default is `%LOCALAPPDATA%/MultiAgents` on
Windows and `$XDG_DATA_HOME/MultiAgents` or `~/.local/share/MultiAgents` elsewhere.
Set `--home` or AGENT_HUB_HOME explicitly to choose an external directory. Existing
SQLite and config.json formats remain the authoritative state; per-project context
and settings use projects/<stable-id>/ rather than duplicating the workflow store.

```powershell
ma --home C:\LocalData\MultiAgentsV2 migrate --from C:\Tools\multi_agents\data
```

Migration is explicit, requires an empty destination, takes the old daemon lock,
rejects active workflows/live worktrees and symlinks, uses SQLite backup into staging,
copies known Hub data and publishes only the completed destination. Original data is
retained as backup. A failed staging copy is retained for inspection, not deleted.
Delivery paths are adjusted for copied archives; historical log references may still
refer to the retained old home. Never use this to copy OS-dependent live worktrees
between Linux and Windows.

## Troubleshooting

- UNKNOWN auth: use the provider's official interactive status/login; do not scrape tokens.
- Model catalog unknown: INHERIT is supported; do not invent available model IDs.
- No coding agent: enable a supported Codex/Claude adapter or use planning only outside a coding workflow.
- Configuration locked: finish/cancel the active workflow and allow its writer to stop.
- Init says internal home: choose --home outside the repo before retrying.
- Dirty working tree: preserve and commit/stash your own changes intentionally before dispatch.
- Sandbox/permission error: fix the approved environment; never add bypass flags.
- No MCP tool response: reload the selected client, inspect its local MCP output and check the configured Python path/home.
- PATH collision: keep the existing ma command; use an absolute ma.cmd/ma.py path until you intentionally resolve the collision.

## Official references used for adapter/configuration design

- [Codex commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
- [Claude CLI](https://code.claude.com/docs/en/cli-reference)
- [GitHub Copilot CLI](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)
- [Antigravity MCP](https://antigravity.google/docs/mcp)
- [VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)

These sources inform the implementation; mock tests do not certify provider versions,
subscription access, actual model availability or end-to-end IDE integration.
