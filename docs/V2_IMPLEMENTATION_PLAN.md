# V2 audit and implementation plan

Baseline: 8b2e3d8 plus the operator-approved isolation policy and Windows newline test fix. Audit covers tracked Python, launchers, scripts, examples, tests and documentation; excludes runtime data, secrets and provider history. No live provider tests are authorized.

| Phase | Audit classification | Implementation dependency |
|---|---|---|
| 1 discovery/auth | Partial: executable resolution and version doctor only | Registry of official safe probes; unknown auth remains unknown |
| 2 models | Partial: optional model argument | INHERIT/AUTO/MANUAL validation and explicit fallback |
| 3 selection | Partial: enabled/roles already respected | Config transactions, project overrides, terminal checkbox |
| 4 ma | Missing | Compatibility entrypoint reusing hub CLI and engine |
| 5 wizard | Missing | Registry + transactional config + owned PATH installer |
| 6 context | Partial: here and Context Pack | External project context manifests with hashes |
| 7 MCP | Partial: seven stable tools | Add aliases and permission-gated configuration tools |
| 8 workflow | Already implemented, extend | Project settings, max repair policy, self-review evidence |
| 9 monitoring | Partial: JSON polling | Event-derived text rendering, no LLM supervision |
| 10 security | Already implemented, extend | Denied secrets/context paths, config mutation guard, recursion guard |
| 11 docs | Needs extension | CLI/setup/model/MCP/monitor/troubleshooting docs |
| 12 tests | Partial: 51 offline tests | Fake probes, CLI integration and no-repo-write tests |
| 13 local-only | Partial: stdio and hidden daemon already exist | Separate ma default home, safe explicit migration, unregister only |
| 14 multi-entry | Partial: MCP and CLI share one store | External per-client configs, caller provenance, bounded recursion |

Order: registry/settings -> ma and context -> wizard/integrations -> engine/MCP/monitor -> offline tests/docs -> verified source archive. Preserve hub.py init semantics and existing home for legacy users; ma uses an external default home. No automatic migration of live Git worktrees. No automatic commit, push, merge, provider install/login, security attestations or autostart.

Implementation lives in the existing registered worktree. Export a verified archive and patch before any optional cleanup; retain the worktree. Actual provider/client authentication and model execution remain unverified until a separately authorized live test.
