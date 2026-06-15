#!/usr/bin/env python3
"""Validate that the integration manifest version matches a git tag on HEAD."""

import json
import pathlib
import re
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "custom_components" / "robomow_ble" / "manifest.json"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")


def load_manifest_version() -> str:
    """Load and validate the manifest version."""
    with MANIFEST_PATH.open("r", encoding="utf-8") as manifest_file:
        data = json.load(manifest_file)

    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        message = "ERROR: manifest.json must contain a non-empty string 'version' field"
        raise SystemExit(message)

    version = version.strip()
    if not SEMVER_RE.match(version):
        message = (
            "ERROR: manifest.json version must use semantic versioning (X.Y.Z), "
            f"got '{version}'"
        )
        raise SystemExit(message)

    return version


def get_head_tag() -> str | None:
    """Return the semantic version tag on HEAD, or None if there is none."""
    git_executable = shutil.which("git")
    if git_executable is None:
        msg = "ERROR: git executable not found in PATH"
        raise SystemExit(msg)

    try:
        completed = subprocess.run(  # noqa: S603
            [git_executable, "tag", "--points-at", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )
    except subprocess.CalledProcessError as exc:
        message = f"ERROR: unable to read git tags on HEAD: {exc.stderr.strip() or exc}"
        raise SystemExit(message) from exc

    tags = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    for tag in tags:
        if TAG_RE.match(tag):
            return tag
    return None


def main() -> None:
    """Run the manifest version validation."""
    manifest_version = load_manifest_version()
    head_tag = get_head_tag()

    if head_tag is None:
        sys.stdout.write(
            f"No exact git tag on HEAD. manifest.json version is {manifest_version}.\n"
        )
        return

    tag_match = TAG_RE.match(head_tag)
    if tag_match is None:
        message = (
            f"ERROR: git tag {head_tag!r} does not match semantic tag format vX.Y.Z"
        )
        raise SystemExit(message)

    tag_version = tag_match.group(1)
    if tag_version != manifest_version:
        message = (
            "ERROR: manifest.json version does not match the git tag on HEAD. "
            f"manifest.json={manifest_version}, tag={head_tag}"
        )
        raise SystemExit(message)

    sys.stdout.write(
        f"manifest.json version {manifest_version} matches current tag {head_tag}.\n"
    )


if __name__ == "__main__":
    main()
