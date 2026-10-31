"""A small CycloneDX 1.5 SBOM of this install, built from installed package metadata.

Standard library only (``importlib.metadata``), so it works on a phone without extra tools.
It lists ``imagetoolbox-mcp`` and every installed package reachable through its runtime
``Requires-Dist`` (extras and environment markers are evaluated for this interpreter), with
version, licence and a ``pkg:pypi`` purl. It does not contact the network.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from importlib import metadata

from . import __version__

ROOT = "imagetoolbox-mcp"
# Runtime dependencies from pyproject.toml, used when the package runs from a source tree
# (not pip-installed) and so has no metadata of its own.
DECLARED = ("pillow", "mcp")
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements(dist: metadata.Distribution, extras: frozenset[str]) -> list[str]:
    out = []
    for req in dist.requires or []:
        spec, _, marker = req.partition(";")
        m = _NAME.match(spec)
        if not m:
            continue
        marker = marker.strip()
        if marker and not _marker_ok(marker, extras):
            continue
        out.append(m.group(1))
    return out


def _marker_ok(marker: str, extras: frozenset[str]) -> bool:
    try:
        from packaging.markers import Marker  # usually present (pip vendors it too)
    except ImportError:  # pragma: no cover - conservative fallback
        return "extra" not in marker
    try:
        m = Marker(marker)
        if "extra" in marker:
            return any(m.evaluate({"extra": e}) for e in extras)
        return m.evaluate()
    except Exception:  # noqa: BLE001 - an unparsable marker is treated as "not needed"
        return False


def _license(dist: metadata.Distribution) -> str | None:
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr.strip()
    lic = (md.get("License") or "").strip()
    if lic and "\n" not in lic and len(lic) <= 80 and lic.upper() != "UNKNOWN":
        return lic
    for c in md.get_all("Classifier") or []:
        if c.startswith("License :: OSI Approved :: "):
            return c.rsplit(" :: ", 1)[-1]
    return None


def collect(root: str = ROOT) -> list[dict]:
    """Breadth-first walk of installed runtime dependencies. Missing ones are skipped."""
    seen: dict[str, dict] = {}
    queue = [(root, frozenset())]
    while queue:
        name, extras = queue.pop(0)
        key = _norm(name)
        if key in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            if key == _norm(ROOT):
                seen[key] = {"name": ROOT, "version": __version__, "license": "MIT",
                             "requires": sorted(DECLARED)}  # fmt: skip
                queue.extend((d, frozenset()) for d in DECLARED)
            continue
        seen[key] = {
            "name": dist.metadata["Name"],
            "version": dist.version,
            "license": _license(dist),
            "requires": sorted({_norm(r) for r in _requirements(dist, extras)}),
        }
        for r in _requirements(dist, extras):
            queue.append((r, frozenset()))
    return list(seen.values())


def build(root: str = ROOT) -> dict:
    comps = collect(root)
    by = {_norm(c["name"]): c for c in comps}
    main = by.get(_norm(root), {"name": root, "version": __version__, "requires": []})

    def ref(c):
        return f"pkg:pypi/{_norm(c['name'])}@{c['version']}"

    def component(c):
        d = {"type": "library", "bom-ref": ref(c), "name": c["name"], "version": c["version"],
             "purl": ref(c)}  # fmt: skip
        if c.get("license"):
            key = (
                "expression"
                if any(t in c["license"] for t in (" OR ", " AND ", " WITH "))
                else None
            )
            d["licenses"] = (
                [{"expression": c["license"]}] if key else [{"license": {"name": c["license"]}}]
            )
        return d

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tools": {
                "components": [{"type": "application", "name": ROOT, "version": __version__}]
            },  # fmt: skip
            "component": {**component(main), "type": "application"},
        },
        "components": [component(c) for c in comps if c is not main],
        "dependencies": [
            {"ref": ref(c), "dependsOn": [ref(by[r]) for r in c["requires"] if r in by]}
            for c in comps
        ],
    }


def dump(root: str = ROOT) -> str:
    return json.dumps(build(root), indent=2, ensure_ascii=False) + "\n"
