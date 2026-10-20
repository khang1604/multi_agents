# V2 phase report — 2026-10-20

## Scope and evidence

Built on baseline 8b2e3d8 plus the earlier operator-approved security policy and Windows
newline fix. No rewrite of Hub/Engine/SQLite/worktree/MCP, no new runtime dependencies,
no GUI/web server. Implementation was prepared in the registered maintenance worktree.
Source update is delivered as an incremental patch; no commit/push/branch merge.

Windows CPython 3.13.15 / Git 2.54.0.windows.1: **98 tests passed in 55.011 seconds**,
including 47 V2 checks and the 51 earlier regression checks. The final offline demo
completed with simulated failover, 4 fixture tests passing, original source unchanged
and 0 real model calls. setup.ps1 syntax was parsed without running installation.
No live provider tests, sign-ins, account changes, user PATH installation or real client
config changes were made during V2 development. The launcher itself was tested offline
from a synthetic Unicode project. Linux and end-to-end IDE checks remain unrun.

## Phase 1: automatic discovery

Files: agenthub/registry.py, settings.py, tests/test_v2.py.
PATH/common Windows locations resolve through the existing safe executable resolver.
IDE availability is separate from CLI/login. Optional bounded version/help and official
Codex/Claude auth-status probes discard raw account diagnostics. Copilot/Antigravity
auth stays UNKNOWN when no implemented official noninteractive probe is verified.
Tests cover absent, installed, ready, unknown, failed probes and account-output removal.
Remaining: actual installed provider versions and live capability/auth checks.

## Phase 2: model policy

Files: registry.py, adapters.py, engine.py, policy.py.
INHERIT omits the model flag; AUTO is capability-gated; MANUAL uses provider-advertised
catalogs, retaining legacy model entries. Unknown/retired models fail or use explicitly
authorized INHERIT fallback inside the original call budget. Actual model metadata is
kept in attempt usage when present. Tests use synthetic catalogs, model metadata and
model-unavailable output. Some CLIs expose no catalog: INHERIT is the honest fallback;
no current model IDs or IDE defaults are invented. Live model choices remain unverified.

## Phase 3: dynamic selection

Files: settings.py, wizard.py, policy.py, engine.py.
Space/Enter checkbox with arrows/j/k and basic-terminal fallback; per-project overlays,
supported-role validation, disabled-agent exclusion and no-coding-agent failure before
spending calls. Settings are atomic/backed up, cannot be changed while workflow active,
and cannot reenable a globally disabled agent through an override. Tests cover key
events, idempotency, active-workflow guard, project routing and incompatible roles.

## Phases 4–5: ma and setup

Files: ma.py, ma.cmd, ma, setup.ps1, cli.py, wizard.py, lifecycle.py.
New command/menu delegates to the same existing Hub. Legacy hub.py init behavior is
preserved. Setup checks prerequisites, probes without model calls when run normally,
offers model/role/agent settings and explicitly asks before PATH/client writes.
Owned launcher pins interpreter/home, refuses command collisions, handles Unicode/spaces
and deduplicates its PATH entry. Rollback preserves previous config/backups. CMD percent
sign installation paths are refused explicitly. Tests cover source launcher, fake PATH
install/uninstall/collision/rollback and wizard failure rollback. Real user-registry
installation and a complete interactive wizard session remain unrun in this phase.

## Phase 6: project/shared context

Files: project_context.py, settings.py, store.py, workspace.py.
ma init finds Git root, records language/framework/dependency facts and bounded project
documents, tracks hashes/version, distinguishes AI inference, and reuses context in
Context Pack. All internal state is outside source; no instructions/ignore/hooks/MCP
files are created there. Unknown verification stays unconfigured and cannot dispatch;
dotnet init does not invent test success for an app without a test project. Tests cover
unchanged file map/Git status, stale context, stable identity, Unicode and sensitive-path
exclusions. This is bounded indexing, not a whole-program semantic/code-graph analysis.

## Phases 7 and 14: MCP and multiple entry clients

Files: mcp.py, integrations.py, api.py, adapters.py.
Eleven V2 tools extend the seven original tools. Configuration mutation needs explicit
operator permission. MCP init only refreshes approved registered projects. All clients
share the same home/Store/context/Engine; client provenance and request-key deduplication
are persisted; worker dispatch recursion is rejected. Terminal fallback always exists.
External user configs for Antigravity, VS Code, Copilot and Claude are selectively
merged with backup/ownership. Codex uses official MCP CLI registration, not parsing
non-MCP settings. Tests use temporary JSON/TOML, fake CLI callbacks and stdio requests;
verify legacy aliases, dispatch deduplication, permission and arbitrary-path refusal.
Remaining: actual tool discovery/connection in each installed client. No arbitrary
provider chat is claimed to support MCP automatically.

## Phase 8: workflow

Files: api.py, engine.py, policy.py, config.py.
Existing durable lifecycle, single-writer worktree, failover, budget, independent tests,
review, repair, cancellation and recovery are reused. New default standard/complex
repair cap is 3, still constrained by CLI call cap; old configurations keep their budget.
One-provider self-review is explicitly non-independent. Regression tests cover failover,
recovery/cancellation/timeout/cap, review/repair and ZIP-before-cleanup; V2 tests add
per-project routing, no coding agent, self-review and authorized model fallback.

## Phase 9: terminal monitor

Files: monitor.py, cli.py, engine.py.
Plain-text status/watch derives task, provider/role/model, attempts, elapsed time,
checks, changed-file events, verification/failover from actual state. Unknown remains
unknown; no fake percentage or LLM status calls. Ctrl+C only closes monitoring.
Tests cover queued/event rendering and absence of percentage guesses; lifecycle
regression tests validate persisted events used by the renderer.

## Phases 10 and 13: reliability and local-only data

Files: settings.py, lifecycle.py, project_context.py, workspace.py, security.py.
ma home defaults to LocalAppData/MultiAgents; legacy home is never silently relocated.
SQLite remains the authoritative central workflow DB; external per-project folders hold
context/settings instead of duplicating orchestrators/databases. Init rejects an internal
home before creating files. Unregister retains source/history; uninstall removes only
an unchanged owned launcher/PATH entry. Migration copies a stopped legacy store using
SQLite backup/staging, refuses active worktrees/workflows and symlinks, retains old data
as backup and remaps copied delivery paths. A failed staging folder is retained, not
recursively deleted. Tests include Windows file-handle closure, migration safety,
ownership/collision, sensitive paths, recursive dispatch and bypass-flag rejection.
CLI sandboxes are preserved; no claim of OS ACL/firewall/DLP implementation is made.

## Phases 11–12: documentation and tests

Files: README.md, AGENTS.md, VERIFICATION.md, docs/ARCHITECTURE.md, WINDOWS.md,
SECURITY.md, V2_GUIDE.md, V2_IMPLEMENTATION_PLAN.md, V2_PHASE_REPORT.md, tests/test_v2.py.
Quickstart prioritizes setup.ps1 -> ma init -> ma. Detailed guide explains model/auth
evidence, selection, external data, compatibility, MCP clients, monitoring, migration,
ownership and troubleshooting. Tests use standard library unittest and fake providers.
Existing GitHub Actions example remains an example; no external CI was enabled.

## Explicitly unverified or limited

- No live provider auth/model execution or end-to-end MCP client handshake was tested.
- No live IDE credential/model config is inspected; provider default may remain Unknown.
- MANUAL validation depends on a provider-reported catalog; unsupported catalog means INHERIT/fallback.
- Antigravity/Copilot remain planner/reviewer adapters; neither is promoted to coding.
- No actual PATH registry changes or client configs were installed in this phase.
- No Linux rerun, automated full interactive terminal session, OS ACL, firewall or full DLP certification.
- No original runtime state was migrated, security flags changed, autostart enabled or paid task started.
