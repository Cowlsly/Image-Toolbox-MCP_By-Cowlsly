# Install on an Android phone (Termux)

Status: **VERIFY** — written from the project's cloud tests and public Termux reports; not yet run on a real phone. When you try it, note what happened (especially step 3) so the guide can be corrected.

Tested elsewhere: version 0.8.0 passes `--self-test` on Python 3.13 / Pillow 12.3 / MCP SDK 2.3 (Linux x86_64). Phones are ARM64 (aarch64), so some dependencies are compiled on the phone — that is the slow, risky part.

## 1. Get Termux

Install **Termux from F-Droid or its GitHub releases**, not the old Play Store build (it no longer receives package updates). Open it once and let it finish setting up.

## 2. System packages

```sh
pkg update && pkg upgrade -y
pkg install -y python git python-pillow python-cryptography
termux-setup-storage        # tap "Allow"; creates ~/storage/ links to your phone folders
```

Why: `python-pillow` and `python-cryptography` are prebuilt Termux packages, so pip does not have to compile them. Do **not** run `pip install --upgrade pip` in Termux; Termux manages pip itself and the upgrade is known to fail.

## 3. Install the server

```sh
pip install "git+https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly@root"
```

What to expect: pip downloads the MCP SDK and its dependencies. Two of them, `pydantic-core` and `rpds-py`, are written in Rust and have no ready-made Android wheels, so pip may compile them. If it stops with **"can't find Rust compiler"** or **"aarch64-linux-android-ar not found"**:

```sh
pkg install -y rust binutils build-essential
pip install "git+https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly@root"
```

Compiling can take **10–30 minutes** and gets the phone warm. Keep Termux in the foreground and the screen on (or pull down the Termux notification → "Acquire wakelock").

## 4. Check the install (one command)

```sh
imagetoolbox-mcp --self-test
```

It makes a throw-away folder with two generated pictures, runs every tool on them, starts the real server once the way an assistant app does, and prints one line per check. Nothing of yours is read or changed. A good result ends with:

```
PASS  stdio server — child process answered image_inspect
PASS  originals unchanged — source files byte-identical after all tools
PASS  outputs written — 9 new files in the output folder
SELF-TEST PASSED: 20 checks.
```

`WARN` lines are OK (for example `codec webp` missing only means the WebP format is unavailable; fix with `pkg install libwebp` and reinstall `python-pillow`). Any `FAIL` line means something is broken — see Troubleshooting.

Please paste this output (it contains only versions, no personal data) into a GitHub issue or a chat with the agent, so the guide can be marked as verified.

## 5. Use it from an assistant

The server does nothing on its own; an MCP client starts it. On a phone that means an agent CLI running in Termux — setup for Claude Code and Gemini CLI is in [clients.md](clients.md) (Path A). The usual folder to give it is your Pictures folder:

```sh
imagetoolbox-mcp --root ~/storage/pictures
```

(Run that by hand only to see that it starts; it then waits silently for a client. Press Ctrl+C to stop.) New files go to `~/storage/pictures/imagetoolbox-out/`; your originals are never overwritten.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `imagetoolbox-mcp: command not found` | Close and reopen Termux, or run `python -m imagetoolbox_mcp --self-test`. |
| `can't find Rust compiler` / linker `ar` not found | Step 3 second block: `pkg install rust binutils build-essential`. |
| Build killed / phone very slow during step 3 | Out of memory while compiling. Close other apps and retry; `pip install --no-cache-dir ...` uses less space. |
| `FAIL  pillow — cannot import` | `pkg install python-pillow` (do not `pip install pillow`; it would need to compile). |
| `FAIL  codec jpg` or `codec zlib` | Pillow was built without JPEG/PNG support: `pkg reinstall python-pillow`. |
| `FAIL  mcp sdk — cannot import` | Re-run step 3 and read the first red error line; that dependency failed to build. |
| `FAIL  stdio server` but the other tools pass | The package is not importable from a new process. Run `python -m imagetoolbox_mcp --version`; if that fails, reinstall in step 3. |
| `[not_found]` / `[outside_root]` errors in the assistant | Paths are relative to `--root`. `termux-setup-storage` must have been allowed; check `ls ~/storage/pictures`. |
| Big photos are slow | Expected on a phone: limits are 64 MP / 64 MiB per image; PNG conversion of a 50 MP photo can take tens of seconds. |

## Update or remove

```sh
pip install --upgrade --force-reinstall --no-deps "git+https://github.com/Cowlsly/Image-Toolbox-MCP_By-Cowlsly@root"
pip uninstall imagetoolbox-mcp
```

The `--no-deps` update only replaces this project, so nothing is recompiled.

## Sources

- [Installing pydantic on Termux (Rust + binutils needed)](https://velog.io/@shyim/Install-FastAPI-Pydantic-on-termux-LOL) — report of the build errors and fixes in step 3; also notes that upgrading pip fails in Termux.
- [pydantic-core on PyPI](https://pypi.org/project/pydantic-core/) — publishes wheels for common desktop/server platforms, not for Android/Termux.
