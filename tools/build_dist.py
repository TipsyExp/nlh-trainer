#!/usr/bin/env python3
"""
Allowlist-only packer.

Usage (from repo root):
  python tools/build_dist.py --include-file dist-include.txt --out-dir dist [--dry-run] [--verbose]

Creates: dist/nlh-trainer-<shortsha>.zip
"""
from __future__ import annotations

import argparse
import os
import sys
import zipfile
import subprocess
from datetime import datetime
from pathlib import Path
import glob
import hashlib
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]  # repo root (../.. from tools/)
DEFAULT_OUT = ROOT / "dist"


def read_patterns(file_path: Path) -> list[str]:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    pats: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Normalize slashes for glob
        line = line.replace("\\", "/")
        pats.append(line)
    return pats


def collect_files(patterns: list[str]) -> list[Path]:
    files: set[Path] = set()
    cwd = os.fspath(ROOT)
    for pat in patterns:
        # Expand relative to ROOT; ensure recursive globbing works for **
        matches = glob.glob(pat, recursive=True, root_dir=cwd)
        # If glob doesn't support root_dir (older Python), fallback:
        if not matches:
            matches = glob.glob(os.path.join(cwd, pat), recursive=True)
        for m in matches:
            p = Path(m)
            # If path is absolute because of fallback, relativize to ROOT
            if p.is_absolute():
                try:
                    p = p.relative_to(ROOT)
                except ValueError:
                    pass
            # Only include regular files
            if (ROOT / p).is_file():
                files.add(p)
            elif (ROOT / p).is_dir():
                # If a directory matched, include its files recursively
                for sub in (ROOT / p).rglob("*"):
                    if sub.is_file():
                        files.add(sub.relative_to(ROOT))
    # Filter out obvious junk (safety net; primary control is the allowlist)
    ignored_suffixes = {".pyc", ".pyo", ".DS_Store"}
    return [f for f in sorted(files) if f.suffix not in ignored_suffixes]


def short_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT)
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return datetime.utcnow().strftime("%Y%m%d%H%M%S")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_dist_contents(stage_root: Path, relpaths: list[str]) -> None:
    """Write DIST-CONTENTS.md into stage_root describing the staged payload."""
    out = stage_root / "DIST-CONTENTS.md"
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    # Prefer CI-provided SHA, fall back to local short sha
    commit = os.environ.get("GITHUB_SHA") or short_sha()
    lines: list[str] = []
    lines.append("# Distribution Contents")
    lines.append("")
    lines.append(f"Built from commit {commit} on {now}")
    lines.append("")
    lines.append("## Files")
    for rp in sorted(relpaths):
        size = (stage_root / rp).stat().st_size
        lines.append(f"- {rp}  ({size} bytes)")
    lines.append("")
    lines.append("## Checksums (SHA256)")
    for rp in sorted(relpaths):
        sha = _sha256(stage_root / rp)
        lines.append(f"{sha}  {rp}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--include-file",
        required=True,
        type=Path,
        help="Allowlist file with glob patterns",
    )
    ap.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT, help="Output directory for archive"
    )
    ap.add_argument("--name", type=str, default=None, help="Override archive base name")
    ap.add_argument(
        "--dry-run", action="store_true", help="List files but do not create zip"
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="Print matched files")
    args = ap.parse_args()

    include_path = (
        args.include_file
        if args.include_file.is_absolute()
        else ROOT / args.include_file
    )
    if not include_path.exists():
        print(
            f"[packer] ERROR: include file not found: {include_path}", file=sys.stderr
        )
        return 2

    patterns = read_patterns(include_path)
    if not patterns:
        print("[packer] ERROR: allowlist is empty.", file=sys.stderr)
        return 2

    files = collect_files(patterns)
    if not files:
        print("[packer] ERROR: no files matched the allowlist.", file=sys.stderr)
        if args.verbose:
            print("[packer] patterns:", patterns, file=sys.stderr)
        return 3

    if args.verbose:
        for f in files:
            print(f"[include] {f}")

    if args.dry_run:
        print(f"[packer] DRY RUN — would include {len(files)} files.")
        return 0

    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    base = args.name or f"nlh-trainer-{short_sha()}"
    out_zip = out_dir / f"{base}.zip"

    # Stage allowlisted files, generate DIST-CONTENTS.md, then zip from the stage.
    with tempfile.TemporaryDirectory(prefix="dist-stage-") as tmpdir:
        stage_root = Path(tmpdir)

        # Copy allowlisted files into the staging directory (preserve structure).
        relpaths_posix: list[str] = []
        for relpath in files:
            src = ROOT / relpath
            dst = stage_root / relpath
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            relpaths_posix.append(relpath.as_posix())

        # Create the manifest inside the staged payload.
        _write_dist_contents(stage_root, relpaths_posix)

        # Zip everything from staging (so the manifest is included).
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in stage_root.rglob("*"):
                if p.is_file():
                    arcname = p.relative_to(stage_root).as_posix()
                    z.write(p, arcname)

    size_kib = out_zip.stat().st_size / 1024.0
    print(f"[packer] wrote {out_zip} ({size_kib:.1f} KiB)")
    print(f"[packer] included {len(files)} files from allowlist {include_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
