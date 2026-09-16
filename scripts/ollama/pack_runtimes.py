#!/usr/bin/env python3
"""Pack pinned Ollama Linux runtimes from official archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set


SKIP_NAMES = {".DS_Store"}


def load_lock(root: Path) -> dict:
    lock_path = root / "ollama" / "runtimes.lock.json"
    with lock_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_size(path: Path) -> int:
    return path.stat().st_size


def member_matches(member: str, prefix: str) -> bool:
    return member == prefix or member.startswith(prefix.rstrip("/") + "/")


def list_members(archive: Path) -> List[str]:
    proc = subprocess.Popen(
        ["zstd", "-d", "-c", str(archive)],
        stdout=subprocess.PIPE,
    )
    assert proc.stdout is not None
    names: List[str] = []
    with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
        for item in tar:
            names.append(item.name)
    if proc.wait() != 0:
        raise SystemExit(f"failed to decompress {archive}")
    return names


def assert_layout(archive: Path, require: Sequence[str], forbid: Sequence[str]) -> None:
    names = list_members(archive)
    for needed in require:
        if not any(member_matches(name, needed) for name in names):
            raise SystemExit(f"{archive.name} is missing required path {needed}")
    for blocked in forbid:
        hits = [name for name in names if member_matches(name, blocked)]
        if hits:
            raise SystemExit(
                f"{archive.name} contains forbidden path {blocked}: {hits[0]}"
            )


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            "curl",
            "--fail",
            "--location",
            "--retry",
            "5",
            "--retry-delay",
            "2",
            "--connect-timeout",
            "20",
            "--output",
            str(dest),
            url,
        ]
    )


def ensure_source(
    source: dict, cache_dir: Optional[Path], fetch_dir: Path
) -> Path:
    file_name = source["fileName"]
    dest = fetch_dir / file_name
    cached = cache_dir / file_name if cache_dir is not None else None
    if cached is not None and cached.is_file():
        shutil.copy2(cached, dest)
    elif not dest.is_file():
        download(source["url"], dest)
    actual_sha = sha256_file(dest)
    actual_size = file_size(dest)
    if actual_sha != source["sha256"]:
        raise SystemExit(
            f"{file_name} sha256 mismatch: {actual_sha} != {source['sha256']}"
        )
    if actual_size != source["sizeBytes"]:
        raise SystemExit(
            f"{file_name} size mismatch: {actual_size} != {source['sizeBytes']}"
        )
    return dest


def extract_excluding(archive: Path, dest: Path, exclude: Sequence[str]) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    command = ["tar", "--zstd", "-xf", str(archive), "-C", str(dest)]
    for prefix in exclude:
        command.extend(["--exclude", prefix])
    env = os.environ.copy()
    env["COPYFILE_DISABLE"] = "1"
    subprocess.check_call(command, env=env)
    for prefix in exclude:
        leftover = dest.joinpath(*prefix.split("/"))
        if leftover.exists():
            shutil.rmtree(leftover)


def should_skip(name: str) -> bool:
    base = Path(name).name
    return base in SKIP_NAMES or base.startswith("._")


def collect_tree(root: Path) -> List[Path]:
    entries: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if not should_skip(name))
        filenames = sorted(name for name in filenames if not should_skip(name))
        current = Path(dirpath)
        if current != root:
            entries.append(current)
        for name in filenames:
            entries.append(current / name)
    entries.sort(key=lambda path: path.relative_to(root).as_posix())
    return entries


def write_tree_archive(tree: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    proc = subprocess.Popen(
        ["zstd", "-q", "-T0", "-19", "-f", "-o", str(dest)],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    with tarfile.open(
        fileobj=proc.stdin, mode="w|", format=tarfile.GNU_FORMAT
    ) as tar:
        for path in collect_tree(tree):
            arcname = path.relative_to(tree).as_posix()
            info = tar.gettarinfo(str(path), arcname=arcname)
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = 0
            if path.is_symlink():
                info.type = tarfile.SYMTYPE
                info.linkname = os.readlink(path)
                info.size = 0
                tar.addfile(info)
            elif path.is_dir():
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                info.size = 0
                tar.addfile(info)
            else:
                info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
                with path.open("rb") as handle:
                    tar.addfile(info, handle)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"zstd failed writing {dest}")


def write_notices(root: Path, dest: Path) -> None:
    notices = dest / "OLLAMA_NOTICES.txt"
    parts = [
        (root / "ollama" / "NOTICES.md").read_text(encoding="utf-8"),
        "===== OLLAMA MIT LICENSE =====\n",
        (root / "LICENSES" / "ollama-MIT.txt").read_text(encoding="utf-8"),
    ]
    notices.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    shutil.copy2(root / "LICENSES" / "ollama-MIT.txt", dest / "LICENSE")
    shutil.copy2(root / "ollama" / "runtimes.lock.json", dest / "OLLAMA_SOURCE.json")


def pack_one(
    pack: dict,
    source_path: Path,
    output: Path,
    work_dir: Path,
) -> Path:
    dest = output / pack["fileName"]
    transform = pack["transform"]
    if transform == "identity":
        shutil.copy2(source_path, dest)
    elif transform == "exclude":
        tree = work_dir / pack["id"]
        extract_excluding(source_path, tree, pack.get("exclude") or [])
        write_tree_archive(tree, dest)
        shutil.rmtree(tree)
    else:
        raise SystemExit(f"unsupported transform {transform} for {pack['id']}")
    assert_layout(dest, pack.get("require") or [], pack.get("forbid") or [])
    return dest


def selected_packs(lock: dict, pack_id: Optional[str]) -> List[dict]:
    packs = lock["packs"]
    if not pack_id:
        return packs
    matches = [pack for pack in packs if pack["id"] == pack_id]
    if not matches:
        raise SystemExit(f"unknown pack id {pack_id}")
    return matches


def pack_runtimes(root: Path, output: Path, pack_id: Optional[str]) -> None:
    lock = load_lock(root)
    if output.exists():
        raise SystemExit(f"output path already exists: {output}")
    output.mkdir(parents=True)
    work_dir = output / ".work"
    fetch_dir = work_dir / "sources"
    fetch_dir.mkdir(parents=True)
    cache = Path(os.environ["OLLAMA_SOURCE_DIR"]).expanduser() if os.environ.get("OLLAMA_SOURCE_DIR") else None

    packs = selected_packs(lock, pack_id)
    source_ids: Set[str] = {pack["source"] for pack in packs}
    sources: Dict[str, Path] = {}
    for source_id in sorted(source_ids):
        source = lock["sources"][source_id]
        sources[source_id] = ensure_source(source, cache, fetch_dir)

    for pack in packs:
        print(f"packing {pack['id']}", file=sys.stderr)
        pack_one(pack, sources[pack["source"]], output, work_dir)

    write_notices(root, output)
    shutil.rmtree(work_dir)
    checksum_lines = []
    for path in sorted(p for p in output.iterdir() if p.is_file()):
        checksum_lines.append(f"{sha256_file(path)}  {path.name}\n")
    (output / "SHA256SUMS").write_text("".join(checksum_lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("pack", help="download official archives and emit runtime packs")
    pack.add_argument("--root", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--pack", dest="pack_id")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "pack":
        pack_runtimes(args.root.resolve(), args.output.resolve(), args.pack_id)
        return 0
    raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
