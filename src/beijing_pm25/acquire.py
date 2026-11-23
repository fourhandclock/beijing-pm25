"""Immutable raw-archive acquisition with hashes and explicit provenance.

Uses only Python's standard library, so the download/import command also works
before the analysis dependencies are installed.
"""

from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
import urllib.request
import zipfile


SOURCE_PAGE = "https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data"
SOURCE_URL = "https://archive.ics.uci.edu/static/public/501/beijing+multi+site+air+quality+data.zip"
SOURCE_DOI = "https://doi.org/10.24432/C5RK5G"
ARCHIVE_NAME = "uci_beijing_multi_site.zip"
STATION_PATTERN = re.compile(r"PRSA_Data_([A-Za-z0-9]+)_\d{8}-\d{8}\.csv$")
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value):
    """Replace generated JSON atomically and reject non-JSON NaN/Infinity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         delete=False, suffix=".tmp") as handle:
            temporary = Path(handle.name)
            handle.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def iter_station_csvs(archive_path: Path):
    """Read original station CSVs in place, including UCI's nested ZIP layout.

    Auxiliary CSVs in the UCI wrapper are intentionally excluded. No archive
    paths are extracted to disk. Duplicate station members are rejected.
    """
    seen = set()
    expanded = 0

    def walk(archive, prefix="", depth=0):
        nonlocal expanded
        if depth > 2:
            raise ValueError("Unexpected archive nesting (maximum depth 2).")
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe archive member: {info.filename}")
            match = STATION_PATTERN.fullmatch(path.name)
            nested = path.suffix.lower() == ".zip"
            if not match and not nested:
                continue
            expanded += info.file_size
            if info.file_size > MAX_MEMBER_BYTES or expanded > MAX_TOTAL_BYTES:
                raise ValueError("Archive exceeds the documented decompression size limit.")
            content = archive.read(info)
            member = f"{prefix}{info.filename}"
            if nested:
                with zipfile.ZipFile(io.BytesIO(content)) as inner:
                    yield from walk(inner, member + "!", depth + 1)
            else:
                station = match.group(1)
                if station in seen:
                    raise ValueError(f"Duplicate station CSV in archive: {station}")
                seen.add(station)
                yield station, member, content

    with zipfile.ZipFile(archive_path) as outer:
        yield from walk(outer)
    if not seen:
        raise ValueError("Archive contains no original PRSA_Data_<station>_<dates>.csv files.")


def _validate_archive(path: Path):
    # Exhaust the iterator to validate all CRCs and reject duplicate stations.
    return [station for station, _, _ in iter_station_csvs(path)]


def verify_raw(project_root: Path):
    raw = project_root / "data" / "raw"
    path = raw / ARCHIVE_NAME
    manifest_path = raw / "provenance.json"
    if not path.is_file() or not manifest_path.is_file():
        raise ValueError(
            "Raw data/provenance are missing. Run 'python -m beijing_pm25 download' "
            "or 'python -m beijing_pm25 download --import-archive /path/to/UCI.zip'."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("sha256") != sha256_file(path):
        raise ValueError("Raw archive checksum mismatch; raw data were changed. Do not overwrite them.")
    if manifest.get("size_bytes") != path.stat().st_size:
        raise ValueError("Raw archive size differs from its provenance manifest.")
    return path, manifest


def acquire(project_root: Path, import_archive: Path | None = None, timeout=30):
    raw = project_root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    destination = raw / ARCHIVE_NAME
    manifest_path = raw / "provenance.json"
    if destination.exists():
        path, manifest = verify_raw(project_root)
        if import_archive is not None and sha256_file(import_archive) != manifest["sha256"]:
            raise ValueError("A different archive is already preserved; use a separate project copy.")
        return path, manifest
    # A fresh clone has the committed manifest but not the (gitignored) archive.
    # Fetch the bytes again and accept them only if they match the recorded hash,
    # leaving the committed provenance untouched.
    expected = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    if not 1 <= timeout <= 120:
        raise ValueError("Download timeout must be between 1 and 120 seconds.")

    temporary = None
    started = time.monotonic()
    source = {"kind": "local_import", "imported_from": str(import_archive)}
    try:
        with tempfile.NamedTemporaryFile("wb", dir=raw, suffix=".part", delete=False) as handle:
            temporary = Path(handle.name)
            if import_archive is not None:
                if not import_archive.is_file():
                    raise ValueError(f"Import archive not found: {import_archive}")
                if import_archive.stat().st_size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Import archive exceeds the 64 MiB size limit.")
                with import_archive.open("rb") as original:
                    shutil.copyfileobj(original, handle)
            else:
                request = urllib.request.Request(
                    SOURCE_URL, headers={"User-Agent": "BeijingPM25CourseProject/0.1"},
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    source = {
                        "kind": "official_uci_download", "requested_url": SOURCE_URL,
                        "resolved_url": response.url,
                        "http_status": response.status,
                        "etag": response.headers.get("ETag"),
                        "last_modified": response.headers.get("Last-Modified"),
                        "content_type": response.headers.get("Content-Type"),
                    }
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            raise ValueError("Download exceeds the 64 MiB size limit.")
                        if time.monotonic() - started > 120:
                            raise TimeoutError("Download exceeded its two-minute total time budget.")
                        handle.write(chunk)
        stations = _validate_archive(temporary)
        if expected is not None:
            if (sha256_file(temporary) != expected.get("sha256")
                    or temporary.stat().st_size != expected.get("size_bytes")):
                raise ValueError(
                    "The fetched archive does not match the SHA-256 recorded in "
                    "data/raw/provenance.json, so the committed results may not reproduce. "
                    "Import the original archive with --import-archive, or delete "
                    "provenance.json to record new provenance (results will then cite a different archive)."
                )
            os.link(temporary, destination)
            return destination, expected
        manifest = {
            "dataset": "UCI Beijing Multi-Site Air Quality", "uci_id": 501,
            "doi": SOURCE_DOI, "source_page": SOURCE_PAGE,
            "official_download_url": SOURCE_URL,
            "citation": "Chen, S. (2017). Beijing Multi-Site Air Quality [Dataset]. UCI Machine Learning Repository.",
            "license": "CC BY 4.0", "retrieved_at_utc": utc_now(),
            "version_note": "No release version asserted; identify these exact bytes by SHA-256.",
            "archive_name": ARCHIVE_NAME, "sha256": sha256_file(temporary),
            "size_bytes": temporary.stat().st_size, "stations": stations,
            "source": source,
            "origin_note": (
                "Retrieved directly from UCI."
                if import_archive is None else
                "User-supplied local file; content hash recorded, original download origin not independently verified."
            ),
        }
        # Refuse to clobber a raw file even if another process raced this one.
        # The temporary file is in this directory, so a hard link installs the
        # fully written bytes atomically and fails if destination already exists.
        os.link(temporary, destination)
        write_json(manifest_path, manifest)
        return destination, manifest
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
