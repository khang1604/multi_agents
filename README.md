# Multi Agents

Documentation and interface language: **English**.

Coordinate Codex, Claude Code, Copilot CLI and Antigravity CLI for planning,
implementation, testing and review. Install only the tools you need; Codex/Claude
handle code changes. The core uses the Python standard library and Git.

## Features

| Feature | Behavior |
|---|---|
| Roles and task sizing | Route work to suitable tools with a bounded number of CLI calls. |
| Leader failover and quota waits | Save checkpoints, switch to eligible tools or wait for the next retry; never raise budgets automatically. |
| Shared context and Handoff v2 | Transfer intent, attempted approaches, rejection reasons, constraints and next actions, with hashes and test evidence. |
| Durable state | SQLite stores local workflows, memory, checkpoints and provider state. |
| Worktrees and verification | Work in an isolated checkout, run project checks and review the result. |
| Review and accept | Native VS Code diff, accept all or individual files; integrity-checked ZIPs remain available for recovery. |
| Chat and MCP | Submit tasks through Copilot Chat `@hub` or Hub MCP tools in a connected client. |
| Quick setup | One selection screen for CLIs/integrations, shared INHERIT policy, auth checks and optional official login. |

## Get started: setup → init → prompt

Requires **Git, Python >= 3.11** and at least Codex CLI or Claude Code CLI for code changes.
Install the AI CLIs separately; an IDE extension does not imply its CLI is installed.
Use only authorized source, synthetic data and approved test APIs.

### 1. Set up once

Clone into a new directory, then run setup from the Multi Agents directory:

**Windows — PowerShell:**

```powershell
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
.\setup.ps1
```

**Ubuntu:**

```bash
git clone https://github.com/khang1604/multi_agents.git
cd multi_agents
./setup.sh
```

Setup opens a **selection screen in the terminal**; it does not automatically open VS Code.
Select CLIs and optional integrations: the `ma` command, VS Code `@hub`, VS Code MCP,
and, on Windows, automatic queue wake checks. Only selected actions are applied.
INHERIT uses each CLI's default model. Setup keeps configuration backups.
Auth checks do not call models; `UNKNOWN` means unverified, not necessarily logged out.
Use the optional official login flow inside setup when needed; never paste tokens into chat.

After installing/updating the Hub extension, run this from any directory to open
**Quick Setup in VS Code**:

```text
ma setup interface
```

This sends an open request without applying settings. Requires `code` on PATH and
the Hub extension installed by the same Hub source/home in the default VS Code profile.
If the extension is missing, run `ma setup` and select **Connect VS Code @hub** first.
If the interface does not appear, reload VS Code and retry, or use the Command Palette:


1. Press `Ctrl+Shift+P` → **Multi Agents: Quick Setup**.
2. Existing CLI logins are checked automatically. Verified sessions show **Sign out**;
   other states show **Login**, including unselected agents. Missing CLIs must be installed first.
   Status refreshes after the auth terminal ends, keeping your unsaved choices.
   For Copilot/Antigravity sign-out, enter `/logout` in that terminal, then exit.
   UNKNOWN means unverified; it does not mean you must log in again.
3. Click **Apply once**. For individual model/role settings, use `ma setup --advanced`.

Open a new terminal on Windows after installing the command. On Ubuntu, add the launcher
directory to PATH using the command printed by setup; setup does not edit shell profiles.
Reload VS Code if prompted. If the script cannot run, use `py -3 ma.py setup` (Windows)
or `python3 ma.py setup` (Ubuntu).

### 2. Initialize your project

Open a Git repository with a commit and a working verification command, then run:

```text
ma init
```

Confirm the source/data scope when prompted. Init prepares the project and checks
verification and connections; resolve reported errors before submitting work.
You do not need a separate copy of Hub in each project.

### 3. Write a prompt in chat

In Copilot Chat with Hub installed:

```text
@hub Add task filtering by status and keyword. Preserve existing calls, add tests and review the changes.
```

Hub returns a workflow ID and progress. Once complete, choose **Review changes**,
then **Accept all** or **Accept individual files**.
Acceptance applies files without committing or pushing. Other chat clients need Hub MCP tools.
A workflow ID confirms the request reached Hub.

## Common commands

Run in your project directory, except setup/demo. `ID` means workflow ID.

| Command | Purpose |
|---|---|
| `ma setup` | Terminal setup screen; does not launch the VS Code interface. |
| `ma setup interface` | Open VS Code Quick Setup; select options and click Apply. |
| `ma setup --advanced` | Configure individual providers, models and roles. |
| `ma init` | Prepare or recheck the current project. |
| `ma agents list --check` | Detect CLIs and report status with short reasons; no model calls. |
| `ma status --watch` / `ma logs` | Follow progress / inspect attempts and errors. |
| `ma handoff ID` | Read the saved handoff and next action. |
| `ma review ID` / `ma diff ID` | List delivery files / inspect the diff. |
| `ma accept ID` | Apply the entire completed result. |
| `ma accept ID --file app/tasks.py` | Accept one file; repeat `--file` to select more. |
| `ma auto-accept on` / `off` / `status` | Control automatic acceptance for this project; off by default. |
| `ma retry ID` / `ma cancel ID` | Resume within the remaining budget / stop and keep checkpoints. |
| `ma run "Your request"` | Submit work through the terminal if preferred. |
| `ma doctor` / `ma --help` | Diagnose problems / read command help. |

### `@hub` commands in Copilot Chat

| Command | Purpose and example |
|---|---|
| `@hub <request>` | Submit work for the open project, e.g. `@hub Add task filtering and tests`. Hub returns a workflow ID. |
| `@hub /agents` | List detected agent CLIs and known status; no model call. Copilot Chat and Copilot CLI are separate. |
| `@hub /status [ID]` | Read the saved state, current phase/provider, call budget and available report once. Example: `@hub /status abc123`. |
| `@hub /watch [ID]` | Follow progress for up to about 10 minutes per view. Stopping the view does not cancel work. |
| `@hub /retry [ID]` | Resume after fixing a blocker; keeps the existing call budget. Example: `@hub /retry abc123`. |
| `@hub /cancel [ID]` | Request cancellation while retaining saved code and checkpoints; does not delete files. |
| `@hub /accept [ID]` | Confirm applying the completed delivery to project files in the VS Code dialog; no commit or push. |
| `@hub /autoaccept on` | Enable automatic acceptance for this project after confirmation; conflicting source edits block application. |
| `@hub /autoaccept off` | Disable automatic acceptance; future results wait for your approval. |
| `@hub /autoaccept status` | Check this project's automatic acceptance setting; off by default. |

`[ID]` is optional: replace it with a workflow ID without brackets, or omit it to
select the latest workflow in the open project. IDs from other projects are refused.
A new prompt is not dispatched while the project has unfinished work; watch or cancel it first.
After completion, **Review changes**, **Accept all** and **Accept individual files** provide
native diff and acceptance controls; `/accept` applies the whole delivery.
Status/agent/progress commands do not ask a model for updates; submitting work or
retrying can run provider CLIs within the remaining budget. Hub acceptance does not
change CLI sandbox permissions or bypass the host chat's quota limits.

Try without AI from the Multi Agents directory:

```bash
python3 ma.py demo --simulate
```

On Windows, replace `python3` with `py -3`. Providers are simulated; Git and tests still run.

## Status and contributions

Work in progress: smooth operation on every machine or chat client is not guaranteed.
A host chat quota limit may block a prompt before it reaches Hub; MCP cannot bypass that limit.
Tasks already submitted can switch to another available CLI. Budgets count CLI invocations,
not exact tokens or cost. Windows and Ubuntu have separate verification evidence.

See [verification results](VERIFICATION.md), [fixed issues and contribution tasks](docs/KNOWN_ISSUES.md),
[contributing](CONTRIBUTING.md), [Handoff v2](docs/HANDOFF.md) and the [detailed guide](docs/V2_GUIDE.md).
Read [global rules](GLOBAL_RULES.md) and [security](docs/SECURITY.md) before real runs:
no real user data/secrets, preserve CLI sandboxes, and use OS isolation when requested by the user.
Supporting technical documents are also available in English.

Built from the author's ideas, with inspiration from [Maestro](https://github.com/RunMaestro/Maestro),
[agent-intern](https://github.com/SinanTufekci/agent-intern),
[Agent Deck](https://github.com/asheshgoplani/agent-deck) and
[AI Maestro](https://github.com/23blocks-OS/ai-maestro).
