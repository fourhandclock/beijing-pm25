import zipfile

import pytest

from beijing_pm25.acquire import acquire, iter_station_csvs, sha256_file, verify_raw
from conftest import csv_bytes, hourly_rows, write_archive


@pytest.mark.parametrize("nested", [False, True])
def test_only_original_station_members_loaded(tmp_path, nested):
    archive = write_archive(tmp_path / "input.zip", {"Alpha": hourly_rows()}, nested=nested)
    members = list(iter_station_csvs(archive))
    assert len(members) == 1
    assert members[0][0] == "Alpha"
    assert members[0][2] == csv_bytes(hourly_rows())


def test_import_preserves_raw_bytes_and_records_unverified_origin(tmp_path):
    archive = write_archive(tmp_path / "input.zip", {"Alpha": hourly_rows()})
    project = tmp_path / "project"
    preserved, manifest = acquire(project, archive)
    assert preserved.read_bytes() == archive.read_bytes()
    assert manifest["sha256"] == sha256_file(archive)
    assert manifest["source"]["kind"] == "local_import"
    assert "not independently verified" in manifest["origin_note"]
    assert verify_raw(project)[1] == manifest
    before = preserved.stat().st_mtime_ns
    assert acquire(project, archive)[1] == manifest
    assert preserved.stat().st_mtime_ns == before
    assert not list(preserved.parent.glob("*.part"))


def test_different_import_cannot_overwrite_preserved_raw(tmp_path):
    first = write_archive(tmp_path / "first.zip", {"Alpha": hourly_rows()})
    second = write_archive(tmp_path / "second.zip", {"Alpha": hourly_rows(offset=100)})
    preserved, _ = acquire(tmp_path / "project", first)
    original_bytes = preserved.read_bytes()
    with pytest.raises(ValueError, match="different archive"):
        acquire(tmp_path / "project", second)
    assert preserved.read_bytes() == original_bytes


def test_fresh_clone_with_committed_manifest_restores_matching_archive(tmp_path):
    archive = write_archive(tmp_path / "input.zip", {"Alpha": hourly_rows()})
    project = tmp_path / "project"
    preserved, manifest = acquire(project, archive)
    manifest_text = (preserved.parent / "provenance.json").read_text(encoding="utf-8")
    preserved.unlink()  # what a fresh clone looks like: manifest committed, archive gitignored
    restored, restored_manifest = acquire(project, archive)
    assert restored.read_bytes() == archive.read_bytes()
    assert restored_manifest == manifest
    assert (restored.parent / "provenance.json").read_text(encoding="utf-8") == manifest_text
    assert verify_raw(project)[1] == manifest
    assert not list(restored.parent.glob("*.part"))


def test_fresh_clone_rejects_archive_not_matching_committed_manifest(tmp_path):
    first = write_archive(tmp_path / "first.zip", {"Alpha": hourly_rows()})
    second = write_archive(tmp_path / "second.zip", {"Alpha": hourly_rows(offset=100)})
    project = tmp_path / "project"
    preserved, _ = acquire(project, first)
    preserved.unlink()
    with pytest.raises(ValueError, match="does not match the SHA-256"):
        acquire(project, second)
    assert not preserved.exists()
    assert not list(preserved.parent.glob("*.part"))


def test_tampered_raw_archive_rejected(tmp_path):
    archive = write_archive(tmp_path / "input.zip", {"Alpha": hourly_rows()})
    preserved, _ = acquire(tmp_path / "project", archive)
    preserved.write_bytes(preserved.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_raw(tmp_path / "project")


def test_failed_import_leaves_no_false_provenance_or_raw_file(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("data.csv", "not,the,dataset\n")
    root = tmp_path / "project"
    with pytest.raises(ValueError, match="no original"):
        acquire(root, bad)
    assert not (root / "data" / "raw" / "uci_beijing_multi_site.zip").exists()
    assert not (root / "data" / "raw" / "provenance.json").exists()
    assert not list((root / "data" / "raw").glob("*.part"))


def test_duplicate_station_members_rejected(tmp_path):
    path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(path, "w") as z:
        for folder in ("first", "second"):
            z.writestr(f"{folder}/PRSA_Data_Alpha_20130301-20170228.csv", csv_bytes(hourly_rows()))
    with pytest.raises(ValueError, match="Duplicate station"):
        list(iter_station_csvs(path))


def test_unsafe_archive_paths_rejected(tmp_path):
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("../PRSA_Data_Alpha_20130301-20170228.csv", csv_bytes(hourly_rows()))
    with pytest.raises(ValueError, match="Unsafe archive"):
        list(iter_station_csvs(path))
