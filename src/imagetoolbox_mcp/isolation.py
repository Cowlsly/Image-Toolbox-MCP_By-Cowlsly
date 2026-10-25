"""Optional parser isolation with a hard per-call timeout (threat model R2).

With ``--isolate SECONDS`` every engine call runs in a short-lived child process. If the
child does not finish in time it is killed and the tool returns ``[timed_out]``; a crash
inside a C decoder (segfault, abort) becomes ``[decode_failed]`` instead of taking the
server down. Off by default: starting a process per call costs roughly 0.3-1 s, which is
noticeable on a phone.

The child uses the ``spawn`` start method (no inherited state, works the same on Linux,
Termux, macOS and Windows). Arguments and results are pickled; ``EngineError`` is sent back
as ``(code, message)`` so it survives the trip unchanged.
"""

from __future__ import annotations

import functools
import multiprocessing as mp
from collections.abc import Callable
from typing import Any

from .engine import EngineError

MIN_TIMEOUT = 1.0
MAX_TIMEOUT = 600.0


def _child(conn, fn, args, kwargs) -> None:  # pragma: no cover - runs in the child
    try:
        conn.send(("ok", fn(*args, **kwargs)))
    except EngineError as err:
        conn.send(("engine_error", (err.code, err.message)))
    except MemoryError:
        conn.send(("engine_error", ("out_of_memory", "The image needs more memory than is free.")))
    except BaseException as exc:  # noqa: BLE001 - report the type only, never the message
        conn.send(("exception", type(exc).__name__))
    finally:
        conn.close()


def run_isolated(fn: Callable[..., Any], *args, timeout: float, **kwargs) -> Any:
    """Run ``fn(*args, **kwargs)`` in a child process; raise ``EngineError`` on timeout/crash."""
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child, fn, args, kwargs), daemon=True)
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise EngineError(
                "timed_out",
                f"The operation took longer than {timeout:g} s and was stopped. "
                "Try a smaller image or a simpler setting.",
            )
        try:
            kind, payload = parent.recv()
        except EOFError:
            raise EngineError(
                "decode_failed", "The image could not be processed (the decoder stopped)."
            ) from None
    finally:
        parent.close()
        if proc.is_alive():
            proc.kill()
        proc.join(5)
    if kind == "ok":
        return payload
    if kind == "engine_error":
        raise EngineError(*payload)
    raise RuntimeError(f"isolated call failed: {payload}")


def isolated(fn: Callable[..., Any], timeout: float | None) -> Callable[..., Any]:
    """Return ``fn`` unchanged when ``timeout`` is None, else a process-isolated wrapper."""
    if timeout is None:
        return fn
    if not MIN_TIMEOUT <= float(timeout) <= MAX_TIMEOUT:
        raise ValueError(f"isolation timeout must be {MIN_TIMEOUT:g}-{MAX_TIMEOUT:g} seconds")

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return run_isolated(fn, *args, timeout=float(timeout), **kwargs)

    return wrapper
