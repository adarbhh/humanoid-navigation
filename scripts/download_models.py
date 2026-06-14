"""
Download Unitree G1 model from MuJoCo Menagerie (google-deepmind/mujoco_menagerie).

Uses the GitHub Contents API so we fetch only the G1 subtree, not the full repo.
Output: robot/model/g1/  (XML + mesh assets)

SSL fallback: if the system SSL store rejects GitHub's certificate (common on
corporate networks or fresh Windows installs), the script retries with
verification disabled and prints a warning.
"""

import hashlib
import json
import ssl
import sys
import time
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

# Set to True by _get() if SSL verification had to be disabled.
_SSL_DISABLED = False


def _make_context(verify: bool) -> ssl.SSLContext | None:
    if verify:
        return None  # urllib default — uses system trust store
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _get(url: str, verify: bool = True) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "robotics-assignment-setup"})
    with urllib.request.urlopen(req, timeout=30, context=_make_context(verify)) as r:
        return r.read()


def _get_with_fallback(url: str, retries: int = 3) -> bytes:
    """
    Try with SSL verification first. On SSL error, retry without verification
    (prints a one-time warning). Other errors are retried with backoff.
    """
    global _SSL_DISABLED
    last_exc = None

    for attempt in range(1, retries + 1):
        try:
            return _get(url, verify=not _SSL_DISABLED)
        except ssl.SSLError as exc:
            if not _SSL_DISABLED:
                print(
                    "\n  [warn] SSL verification failed — retrying without SSL verification."
                    "\n         This is safe on a trusted network but avoid on public Wi-Fi."
                    f"\n         Reason: {exc}\n"
                )
                _SSL_DISABLED = True
            try:
                return _get(url, verify=False)
            except Exception as exc2:
                last_exc = exc2
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                print(f"  [warn] attempt {attempt} failed ({exc}), retrying in {2**attempt}s ...")
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Failed to download after {retries} attempts: {url}") from last_exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _list_files(api_url: str) -> list[dict]:
    """Recursively list all files under a GitHub Contents API URL."""
    items = json.loads(_get_with_fallback(api_url))
    files = []
    for item in items:
        if item["type"] == "file":
            files.append(item)
        elif item["type"] == "dir":
            files.extend(_list_files(item["url"]))
    return files


def download():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Fast-path: skip network if required files already present ─────────────
    required = ["scene.xml", "g1.xml"]
    if all((OUT_DIR / r).exists() for r in required):
        print(f"Model already present at: {OUT_DIR}")
        print(f"  (delete {OUT_DIR} and re-run to force a fresh download)")
        return

    # ── Fetch file list ───────────────────────────────────────────────────────
    print(f"Fetching file list from {REPO}/{MODEL_DIR} ...")
    try:
        files = _list_files(API_BASE)
    except Exception as exc:
        print(f"\nERROR: Could not reach GitHub API: {exc}")
        print("Check your internet connection and try again.")
        sys.exit(1)
    print(f"  Found {len(files)} files.")

    # ── Download each file ────────────────────────────────────────────────────
    downloaded = 0
    skipped = 0
    failed: list[str] = []

    for item in files:
        rel_path = item["path"].removeprefix(f"{MODEL_DIR}/")
        dest = OUT_DIR / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            if rel_path in CHECKSUMS:
                if _sha256(dest.read_bytes()) == CHECKSUMS[rel_path]:
                    print(f"  [skip] {rel_path} (checksum ok)")
                    skipped += 1
                    continue
            else:
                skipped += 1
                continue

        raw_url = f"{RAW_BASE}/{rel_path}"
        print(f"  [dl]   {rel_path}")
        try:
            data = _get_with_fallback(raw_url)
        except RuntimeError as exc:
            print(f"  ERROR: {exc}")
            failed.append(rel_path)
            continue

        dest.write_bytes(data)
        downloaded += 1

        if rel_path in CHECKSUMS:
            got = _sha256(data)
            if got != CHECKSUMS[rel_path]:
                print(f"  ERROR: checksum mismatch for {rel_path}")
                print(f"    expected: {CHECKSUMS[rel_path]}")
                print(f"    got:      {got}")
                dest.unlink()
                failed.append(rel_path)

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\nDownloaded {downloaded} files, skipped {skipped} (already present).")

    if _SSL_DISABLED:
        print("  [warn] SSL verification was disabled for this download.")

    if failed:
        print(f"\nERROR: {len(failed)} file(s) failed to download:")
        for f in failed:
            print(f"  - {f}")
        sys.exit(1)

    # ── Verify required files exist ───────────────────────────────────────────
    missing = [r for r in required if not (OUT_DIR / r).exists()]
    if missing:
        print(f"\nERROR: Required model file(s) missing after download: {missing}")
        print(f"  Output directory: {OUT_DIR}")
        sys.exit(1)

    print(f"Model ready at: {OUT_DIR}")

    # ── Write SHA-256 manifest ────────────────────────────────────────────────
    manifest_path = OUT_DIR / "MANIFEST.txt"
    with manifest_path.open("w", encoding="utf-8") as f:
        f.write(f"# MuJoCo Menagerie G1 model manifest\n")
        f.write(f"# repo: {REPO}  branch: {BRANCH}\n\n")
        for item in sorted(files, key=lambda x: x["path"]):
            rel = item["path"].removeprefix(f"{MODEL_DIR}/")
            dest = OUT_DIR / rel
            sha = _sha256(dest.read_bytes()) if dest.exists() else "MISSING"
            f.write(f"{sha}  {rel}\n")
    print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    download()
