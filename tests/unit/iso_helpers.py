"""Module-level helpers for test_isolation (a spawned child must be able to import them)."""

import os
import time

from imagetoolbox_mcp.engine import EngineError


def slow(seconds):
    time.sleep(seconds)
    return "finished"


def refuse():
    raise EngineError("not_found", "no such image")


def crash():
    os._exit(11)  # what a C-level decoder crash looks like to the parent


def boom():
    raise KeyError("/secret/path/should/not/leak")


def add(a, b=0):
    return a + b
