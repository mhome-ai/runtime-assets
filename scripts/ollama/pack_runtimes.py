#!/usr/bin/env python3
"""Pack pinned Ollama Linux runtimes from official archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SOURCE_FILES = {
    "linux-amd64": "ollama-linux-amd64.tar.zst",
    "linux-arm64": "ollama-linux-arm64.tar.zst",
}


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


def upstream_dir(root: Path) -> Path:
    return root / "ollama" / "upstream"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    if partial.exists():
        partial.unlink()
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
            str(partial),
            url,
        ]
    )
    partial.replace(dest)


def cache_matches(path: Path, sha256: str, size_bytes: int) -> bool:
    return (
        path.is_file()
        and file_size(path) == size_bytes
        and sha256_file(path) == sha256
    )


def ensure_source(source: dict, cache_dir: Path) -> Path:
    file_name = source["fileName"]
    dest = cache_dir / file_name
    if cache_matches(dest, source["sha256"], source["sizeBytes"]):
        print(f"using cached {file_name}", file=sys.stderr)
        return dest
    if dest.exists():
        print(f"replacing mismatched {file_name}", file=sys.stderr)
        dest.unlink()
    print(f"downloading {file_name}", file=sys.stderr)
    download(source["url"], dest)
    if not cache_matches(dest, source["sha256"], source["sizeBytes"]):
        dest.unlink(missing_ok=True)
        raise SystemExit(
            f"{file_name} did not match pinned sha256 or size after download"
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
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        try:
            os.link(source_path, dest)
        except OSError:
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


def parse_sha256sum(text: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise SystemExit(f"invalid sha256sum line: {line}")
        mapping[parts[-1].lstrip("*")] = parts[0].lower()
    return mapping


def curl_bytes(url: str) -> bytes:
    return subprocess.check_output(
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
            url,
        ]
    )


def curl_content_length(url: str) -> int:
    headers = subprocess.check_output(
        ["curl", "--fail", "--location", "--silent", "--head", url],
        text=True,
    )
    length = None
    for line in headers.splitlines():
        key, _, value = line.partition(":")
        if key.lower() == "content-length" and value.strip().isdigit():
            length = int(value.strip())
    if not length:
        raise SystemExit(f"could not read Content-Length for {url}")
    return length


def official_url(version: str, file_name: str) -> str:
    return (
        f"https://github.com/ollama/ollama/releases/download/v{version}/{file_name}"
    )


def bump_runtimes(
    root: Path,
    version: str,
    license_file: Optional[Path] = None,
    checksums: Optional[Dict[str, str]] = None,
    sizes: Optional[Dict[str, int]] = None,
) -> None:
    if not VERSION_RE.match(version):
        raise SystemExit(f"version must be X.Y.Z, got {version}")
    lock = load_lock(root)
    lock["engineVersion"] = version
    lock["publicTag"] = f"ollama-v{version}"
    lock["displayName"] = f"Ollama Linux runtimes {version}"
    lock["upstreamTag"] = f"v{version}"
    lock["license"]["url"] = (
        f"https://raw.githubusercontent.com/ollama/ollama/v{version}/LICENSE"
    )

    if license_file is not None:
        license_bytes = license_file.read_bytes()
    else:
        license_bytes = curl_bytes(lock["license"]["url"])
    license_text = license_bytes.decode("utf-8")
    if not license_text.endswith("\n"):
        license_text += "\n"
        license_bytes = license_text.encode("utf-8")
    (root / "LICENSES" / "ollama-MIT.txt").write_bytes(license_bytes)
    lock["license"]["sha256"] = hashlib.sha256(license_bytes).hexdigest()

    if checksums is None:
        checksums = parse_sha256sum(
            curl_bytes(official_url(version, "sha256sum.txt")).decode("utf-8")
        )

    for source_id, file_name in SOURCE_FILES.items():
        source = lock["sources"][source_id]
        source["url"] = official_url(version, file_name)
        source["fileName"] = file_name
        if file_name not in checksums:
            raise SystemExit(f"{file_name} is not in upstream sha256sum.txt")
        source["sha256"] = checksums[file_name]
        if sizes is not None and file_name in sizes:
            source["sizeBytes"] = sizes[file_name]
        else:
            source["sizeBytes"] = curl_content_length(source["url"])

    lock_path = root / "ollama" / "runtimes.lock.json"
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(f"pinned Ollama {version} -> {lock_path}", file=sys.stderr)


def pack_runtimes(root: Path, output: Path, pack_id: Optional[str]) -> None:
    lock = load_lock(root)
    if output.exists():
        raise SystemExit(f"output path already exists: {output}")
    output.mkdir(parents=True)
    work_dir = output / ".work"
    work_dir.mkdir(parents=True)
    cache_dir = upstream_dir(root)
    cache_dir.mkdir(parents=True, exist_ok=True)

    packs = selected_packs(lock, pack_id)
    source_ids: Set[str] = {pack["source"] for pack in packs}
    sources: Dict[str, Path] = {}
    for source_id in sorted(source_ids):
        source = lock["sources"][source_id]
        sources[source_id] = ensure_source(source, cache_dir)

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
    bump = sub.add_parser("bump", help="retarget the lockfile to an official Ollama version")
    bump.add_argument("--root", type=Path, required=True)
    bump.add_argument("--version", required=True)
    bump.add_argument("--license-file", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "pack":
        pack_runtimes(args.root.resolve(), args.output.resolve(), args.pack_id)
        return 0
    if args.command == "bump":
        license_file = args.license_file.resolve() if args.license_file else None
        bump_runtimes(args.root.resolve(), args.version, license_file)
        return 0
    raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
