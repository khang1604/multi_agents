# Test-only security boundary

V2 preserves the selected synthetic-data/isolation attestations. `ma` uses a home
outside the source; `ma init` creates no repository metadata. There is no HTTP
listener or public port. By default, setup changes no client config/PATH until the
operator selects it; backups, ownership checks, and rollback are provided.
`ma config --allow-mcp-config true` separately permits MCP to change enabled/model;
it does not permit security/command changes or arbitrary budget increases.
Workers cannot dispatch recursive workflows. Sandbox bypass flags in extra_args
are blocked. Context excludes .env, credential/private-key files, appsettings, and
credential directories; this is not comprehensive DLP or an OS ACL. Source must
still be approved and synthetic.

Hub blocks real workflows by default before creating worktrees/reading context.
The `--simulate` demo still uses generated fixtures without calling models. Every
real CLI call receives GLOBAL_RULES.md.

Interactive `ma init` receives direct confirmation for the exact source/synthetic/
no-API scope and stores `projects/ID/scope.json` outside the repository. This does
not change global isolation policy, claim isolation, or enable API networking.
Other projects do not inherit this record. SDK runtime accepts only directory
values for ANDROID_HOME/ANDROID_SDK_ROOT; projects cannot override PATH, commands,
or credential variables. The chat bridge respects Workspace Trust, dispatches
only registered projects matching the workspace, does not call the IDE's host
model, and does not change security flags. Stopping chat does not cancel the daemon.

## Prerequisites before enabling

1. The user authorizes the specific source and confirms synthetic data only. Do
   not open secrets, .env, real databases, or user logs. Do not put real data into
   Git/tasks/memory.
2. OS isolation is required only when requested by the user. For a demo project
   confirmed to contain only synthetic data, the user may select
   `require_isolation: false`; do not falsely claim isolation. Unknown data scope
   still blocks real workflows.
3. If APIs are used, use only test accounts and approved endpoints/ports/methods.
   Do not use unrestricted `--network`. Preserve CLI sandbox/permissions without
   bypass flags.
4. The security block below applies to the whole Hub home, not one project. Only
   register authorized, synthetic-confirmed source there; use a separate `--home`
   for another scope. Values are operator decisions/attestations. Agents may update
   them only on explicit user instruction, never self-attest data or isolation to
   evade errors.

Example where the user confirms synthetic data and does not request OS isolation:

```json
"security": {
  "require_isolation": false,
  "isolated_test_environment": false,
  "synthetic_data_only": true,
  "isolation_description": ""
}
```

The new default is `require_isolation: false`, but `synthetic_data_only` remains
false, so real workflows stay blocked until user confirmation. Legacy configs
without `require_isolation` still require isolation; the operator must explicitly
choose true/false to change policy. Use JSON booleans, not strings "false"/"true".

If the user requests isolation, set `require_isolation: true`; real workflows stay
blocked until the user confirms `isolated_test_environment: true` and a nonempty
`isolation_description`. This requires a VM/container or separate OS account with
only approved source and synthetic data, without home/secrets/production mounts.
Block tool networking by default with a firewall/proxy, allowlist exact test APIs,
and separate model-provider networking. Test commands also run inside the requested
boundary.

Hub does not implement file-read ACLs, a firewall allowlist, or complete redaction/
DLP. Codex workspace-write does not guarantee blocking every read outside the repo.
Other CLIs do not share a uniform sandbox. RULE files alone therefore cannot
guarantee exclusion of real data. Never claim isolation that does not exist.
Do not use `--network`: Hub blocks it in real workflows because endpoints cannot
be verified. Do not set provider flags that bypass permissions/sandbox.

## Installing global rules on Windows

```powershell
python scripts/install_global_rules.py
# Review the four PREVIEW paths, then apply when desired:
python scripts/install_global_rules.py --apply
```

The script preserves existing content, updates only Hub's marker block, and creates
`.backup-TIMESTAMP`. Start a new agent session. To uninstall, remove the marker
block or restore the backup.
Codex: `$CODEX_HOME/AGENTS.md` or `~/.codex/AGENTS.md`.
Claude Code: `~/.claude/CLAUDE.md`. Copilot CLI: `~/.copilot/copilot-instructions.md`.
Antigravity: `~/.gemini/GEMINI.md`. Copilot CLI instructions may not apply to every
IDE extension. Product instruction precedence may affect global rules; gates and
sandboxes must remain independent. The installer sets no firewall or credentials.

Hub data stays local by default. Model providers still receive approved context
under their own data policies. Keep secrets/real data out of source, tasks, logs,
and packs.
