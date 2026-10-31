# TODO — Image Toolbox MCP

Last updated 2026-11-01 (portability repair, v0.9.0 candidate). Roadmap: [roadmap.md](roadmap.md). Handover log: [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md).

## Done (agent)
- [x] M0–M4, M6 complete; M5 closed by decision (ADR-0006); M8 docs; M9 agent-side release prep; M10 tools (ADR-0005)
- [x] 11 tools, resumable batches, `--isolate`, `--max-megapixels`, `--log-format json`, `--sbom`
- [x] CI workflow live at `.github/workflows/ci.yml`
- [x] 234 tests pass locally; installed-wheel self-test passes (24 checks)
- [x] Native Windows/macOS and Ubuntu Python 3.10–3.13 matrix plus lint pass after portability and fixture-cleanup repairs; PRs #2 and #1 merged. See the 1 November handover evidence.

## Needs you (phone or GitHub settings — cannot be done by the agent)
- [ ] **Phone install check (15–40 min):** follow `docs/install-termux.md`, run `imagetoolbox-mcp --self-test`, paste the output to Claude. This closes M5 device testing, M7 real-client evidence and M8 screenshots.
- [ ] **Try it from Claude Code or Gemini CLI in Termux** (`docs/clients.md` Path A) and ask it to run one tool. Two clients = M7 exit.
- [ ] **Publish the v0.9.0 pre-release** on github.com (Releases → Draft → tag `v0.9.0`, paste `docs/releases/v0.9.0.md`, tick pre-release). After the phone check passes, 1.0.0 can follow.
- [ ] **GitHub settings:** Settings → Code security → enable secret scanning, push protection and private vulnerability reporting; optionally protect `root` so CI must pass.
