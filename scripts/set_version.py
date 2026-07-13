#!/usr/bin/env python3
"""Stamp a release version into blender_manifest.toml and repo.json.

The git tag is the single source of truth for release versions: CI invokes
this script with the tag name before zipping, then again with --archive to
fill in the zip size and hash. It can also be run locally to preview a bump:

    python scripts/set_version.py 0.2.0
    python scripts/set_version.py 0.2.0 --archive MeddleTools-0.2.0.zip
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "MeddleTools" / "blender_manifest.toml"
REPO_JSON = ROOT / "repo.json"
DOWNLOAD_URL = "https://github.com/PassiveModding/MeddleTools/releases/download/{version}/MeddleTools-{version}.zip"


def stamp_manifest(version: str) -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    new_text, count = re.subn(r'^version = ".*"$', f'version = "{version}"', text, flags=re.MULTILINE)
    if count != 1:
        sys.exit(f"Expected exactly one 'version = ...' line in {MANIFEST}, found {count}")
    MANIFEST.write_text(new_text, encoding="utf-8")
    print(f"{MANIFEST.relative_to(ROOT)}: version = {version}")


def stamp_repo_json(version: str, archive: Path | None) -> None:
    repo = json.loads(REPO_JSON.read_text(encoding="utf-8"))
    repo["version"] = version

    entry = repo["data"][0]
    entry["version"] = version
    entry["archive_url"] = DOWNLOAD_URL.format(version=version)

    if archive is not None:
        data = archive.read_bytes()
        entry["archive_size"] = len(data)
        entry["archive_hash"] = "sha256:" + hashlib.sha256(data).hexdigest()
        print(f"{REPO_JSON.relative_to(ROOT)}: archive_size = {len(data)}, archive_hash updated")

    REPO_JSON.write_text(json.dumps(repo, indent=4) + "\n", encoding="utf-8")
    print(f"{REPO_JSON.relative_to(ROOT)}: version = {version}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", help="Release version (X.Y.Z), normally the git tag name")
    parser.add_argument("--archive", type=Path, help="Path to the release zip; fills in archive size and hash")
    args = parser.parse_args()

    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error(f"version must be semantic (X.Y.Z), got: {args.version!r}")
    if args.archive is not None and not args.archive.is_file():
        parser.error(f"archive not found: {args.archive}")

    stamp_manifest(args.version)
    stamp_repo_json(args.version, args.archive)


if __name__ == "__main__":
    main()
