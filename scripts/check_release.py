"""Check workspace versions, lockfiles, and installed Python package metadata."""

import json
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    versions = {}
    for directory in (".", "apps/api", "apps/mcp-server"):
        path = root / directory / "pyproject.toml"
        project = tomllib.loads(path.read_text())["project"]
        versions[str(path.relative_to(root))] = project["version"]
        if directory != ".":
            versions[f"installed {project['name']}"] = version(project["name"])
    for directory in (".", "apps/web", "packages/tracker"):
        manifest = root / directory / "package.json"
        lock = root / directory / "package-lock.json"
        versions[str(manifest.relative_to(root))] = json.loads(manifest.read_text())["version"]
        locked = json.loads(lock.read_text())
        label = str(lock.relative_to(root))
        versions[label] = locked["version"]
        versions[f"{label} root package"] = locked["packages"][""]["version"]
    for package in tomllib.loads((root / "uv.lock").read_text())["package"]:
        if package["name"] in {"metricairn-workspace", "metricairn-api", "metricairn-mcp"}:
            versions[f"uv.lock {package['name']}"] = package["version"]
    mismatches = [
        f"{label}: {actual} (expected {expected})"
        for label, actual in versions.items()
        if actual != expected
    ]
    if mismatches:
        print("Version mismatch:\n" + "\n".join(mismatches), file=sys.stderr)
        raise SystemExit(1)
    print(f"Workspace manifests, lockfiles, and installed packages agree: {expected}")


if __name__ == "__main__":
    main()
