# Ubuntu readiness evidence — 2026-10-20

**Ready within tested scope: terminal setup/init and completed Codex/Copilot workflows.**
**Not yet accepted: ordinary chat UI dispatch and receipt when the host chat has no quota.**
This is not a claim that every feature works on every Ubuntu installation.

Environment actually exercised: Ubuntu 24.04.5 LTS, Python 3.12.3, Git 2.43.0,
Node 20.20.2. Provider executables: Codex 0.163.0-alpha.10.2, Claude Code 2.1.197,
Copilot 1.0.100, Antigravity 1.4.3. Login remains with each official CLI.

| QA layer | Status | Evidence and limits |
|---|---|---|
| 1 Requirements | Partial | Preserves setup in Hub root → init in project → ordinary prompt. Final UI step not accepted yet. |
| 2 Static/build | Passed selected checks | Python compilation/shell syntax/diff checks; default commands contain no developer-machine paths. |
| 3 Units | Passed selected checks | 175 Python cases: 168 passed, 7 Windows-only skipped; fake providers, no model calls. Includes Node handler/transport regression. |
| 4 Integration/data | Passed selected checks | Real SQLite, Git worktrees, baseline verifier and MCP initialize/18 tools. POSIX launcher executes from a different cwd with Unicode, spaces and quotes. |
| 5 End to end | Partial | Actual setup/init and two completed real-provider workflows, verified exported code. Chat UI path not exercised. |
| 6 Usability/compatibility | Partial | Ubuntu terminal prompts observed; PATH command is explicit and no shell profile is silently changed. Other Ubuntu/Python matrices and GUI accessibility untested. |
| 7 Security/resilience | Partial | Real Codex sandbox read/write/delete probe, owned archive CRC/SHA, original source unchanged. Fake quota failover tests; no OS/DLP security audit or load guarantee. |

## Actual model-backed runs

- `291108b023e8`: Codex plan → Codex implement → independent verifier → Codex review.
  Completed in 3 CLI invocations. This is self-review by one provider, not independent models.
- `49eaebd4781b`: reuse the first paid plan on the identical unchanged synthetic source;
  Codex implement → independent verifier → Copilot review. Completed in 2 CLI invocations.
  The external-plan label is historical bookkeeping, not proof Antigravity planned this run.
- Each delivery ZIP passed CRC and per-file SHA checks. Its overlay was applied to a
  separate clone of the original synthetic source; exported tests ran and direct behavior
  checks covered all/done/pending, trimmed Unicode query, combined filters, invalid status,
  empty input and unchanged original input. No package installation or application API.
- One final Antigravity CLI natural-language read-only status attempt returned official
  `RESOURCE_EXHAUSTED / 429 / Individual quota reached` before answering. This proves that
  CLI/account was quota-blocked; it does not establish IDE chat quota behavior.
- Total authorized model CLI invocations: 6; used: 5 Hub invocations + 1 Antigravity attempt.
  No further model calls are authorized by that rehearsal budget.

## Confirmed defects addressed

- Ubuntu launcher was not executable and install-command assumed Windows registry/PATH.
  POSIX launcher now pins Python/home, keeps cwd, rejects collisions/tampering, and leaves
  shell profiles unchanged. Windows behavior is retained through its original branch.
- VS Code MCP path used Windows AppData on Linux. It now respects Linux XDG config paths.
- A test claimed a fixture was outside Git even when TMPDIR was inside a parent repository.
  The negative test now sets a Git discovery ceiling for that fixture; product discovery
  still follows real Git roots rather than hiding a valid parent checkout.
- Default Codex command previously depended on a desktop installation path. Defaults now
  use portable CLI names; native user-local binaries can be found before a PATH refresh.

## Gates before filming the full chat journey

1. Use a clean clone containing these Ubuntu fixes, with a fresh demo home/fixture.
2. During setup explicitly choose the client integration and refresh it; do not overwrite
   a conflicting installation or silently remove previous rehearsal data.
3. Observe an ordinary prompt in the actual IDE producing a Hub workflow ID for the right
   initialized project. MCP initialization instructions alone are insufficient evidence.
4. Separately exercise quota-limited UI if that feature is to be claimed. Existing tests
   prove handler code avoids the host model, not that the IDE always invokes the handler.
5. Agree a new finite model budget before generating another task for the recording.

No credentials, machine runtime configs, raw model logs, OAuth state, generated worktrees
or provider binaries belong in the published repository. Local evidence is separate.
