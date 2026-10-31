# Maintenance research and execution — 1 November 2026

## Plan and authentication

The owner requested a repository cleanup and then a research-first development sprint on the most useful unblocked project. This independent MCP was selected because it supports image compression, conversion and privacy-aware metadata handling across the ecosystem without a paid API or a production deployment.

GitHub reads and writes use the existing authenticated connection as Cowlsly. Changes use separate branches, pull requests and expected-head merges. No credentials are read or stored. Repository deletion/archive administration is not exposed by this connection; code edits and PR integration are available.

Execution sequence: inspect pinned PR/code/state and CI → research primary documentation → reproduce demonstrated failures → repair narrowly → run full tests/lint/self-test and installed-wheel checks → inspect native CI → merge verified heads → record any phone/release blockers. Recheck heads before each merge; preserve unrelated changes.

## Research findings

- Python's [`os.set_blocking`](https://docs.python.org/3.13/library/os.html#os.set_blocking) is limited to pipes on Windows. Calling it on a regular image descriptor raises an OS error that the old engine misreported as a decode failure. Regular files are already checked with `fstat`; POSIX `O_NONBLOCK` is unnecessary for their reads, while keeping it on the initial open prevents a swapped FIFO from hanging before that check.
- [`PurePath.is_absolute`](https://docs.python.org/3.13/library/pathlib.html#pathlib.PurePath.is_absolute) requires both drive and root for Windows paths. Rooted-relative and drive-relative paths still have an anchor and can reset a path join. They must be rejected before `lstat`, rather than relying on the absolute-path branch.
- The documented no-`..` policy must be checked before `normpath`, which otherwise removes traversal from an absolute path that ends inside the allowed root.

## Reproduction and verification

- Inspected PR #1 at `322405bcefc5d6acfcf24ea3f56ef53e1e2ed80c`; all 76 files were hash-verified during materialization.
- Historical Windows job: https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly/actions/runs/40163382669/job/121079400247 . It ended with 32 failures, 101 errors and 8 skips. Linux/macOS and lint passed on that run.
- Baseline Linux suite: 232 tests passed. New blocking/path regressions and expanded absolute traversal case failed before the repair, then passed afterward.
- Repaired Linux suite: 234 tests passed; self-test: 24 checks passed, including all 11 tools and real stdio communication; lint/format passed.
- Environment: Python 3.12.14, Pillow 13.0.0, MCP 2.3.0, Pydantic 2.14.2; isolated virtual environment, generated images only.

Native repair-head CI and built-wheel results must be recorded after they run. A simulated Windows lexical test is not native Windows evidence. The known Windows directory-swap residual in the threat model remains; this repair does not close it. Android/Termux installation, two real client checks and release publication remain separate gates.
