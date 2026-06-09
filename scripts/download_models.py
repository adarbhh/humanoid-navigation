"""
Download Unitree G1 model from MuJoCo Menagerie (google-deepmind/mujoco_menagerie).

Uses the GitHub Contents API so we fetch only the G1 subtree, not the full repo.
Output: robot/model/g1/  (XML + mesh assets)
"""

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO      = "google-deepmind/mujoco_menagerie"
BRANCH    = "main"
MODEL_DIR = "unitree_g1"
OUT_DIR   = Path(__file__).parent.parent / "robot" / "model" / "g1"

API_BASE  = f"https://api.github.com/repos/{REPO}/contents/{MODEL_DIR}?ref={BRANCH}"
RAW_BASE  = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{MODEL_DIR}"

# SHA-256 checksums for key files — filled in after first download.
# If non-empty, verified on subsequent runs.
CHECKSUMS: dict[str, str] = {}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "robotics-assignment-setup"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _list_files(api_url: str) -> list[dict]:
    """Recursively list all files under a GitHub Contents API URL."""
    items = json.loads(_get(api_url))
    files = []
    for item in items:
        if item["type"] == "file":
            files.append(item)
        elif item["type"] == "dir":
            files.extend(_list_files(item["url"]))
    return files


def download():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching file list from {REPO}/{MODEL_DIR} ...")
    files = _list_files(API_BASE)
    print(f"  Found {len(files)} files.")

    for item in files:
        rel_path = item["path"].removeprefix(f"{MODEL_DIR}/")
        dest = OUT_DIR / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            existing = _sha256(dest.read_bytes())
            if rel_path in CHECKSUMS and existing == CHECKSUMS[rel_path]:
                print(f"  [skip] {rel_path} (checksum ok)")
                continue

        raw_url = f"{RAW_BASE}/{rel_path}"
        print(f"  [dl]   {rel_path}")
        data = _get(raw_url)
        dest.write_bytes(data)

        if rel_path in CHECKSUMS:
            got = _sha256(data)
            if got != CHECKSUMS[rel_path]:
                print(f"  ERROR: checksum mismatch for {rel_path}")
                print(f"    expected: {CHECKSUMS[rel_path]}")
                print(f"    got:      {got}")
                sys.exit(1)

    print(f"\nModel downloaded to: {OUT_DIR}")

    # Emit a manifest for reproducibility auditing
    manifest_path = OUT_DIR / "MANIFEST.txt"
    with manifest_path.open("w") as f:
        f.write(f"# MuJoCo Menagerie G1 model manifest\n")
        f.write(f"# repo: {REPO}  branch: {BRANCH}\n\n")
        for item in sorted(files, key=lambda x: x["path"]):
            rel = item["path"].removeprefix(f"{MODEL_DIR}/")
            dest = OUT_DIR / rel
            sha = _sha256(dest.read_bytes()) if dest.exists() else "MISSING"
            f.write(f"{sha}  {rel}\n")
    print(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    download()
