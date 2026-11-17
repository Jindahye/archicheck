import json
import sqlite3
from pathlib import Path

import pytest

from server.store.report_store import ReportStore

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "report.json"


@pytest.fixture
def sample():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path):
    return ReportStore(tmp_path / "test.db")


def test_init_creates_table(tmp_path):
    path = tmp_path / "sub" / "t.db"
    ReportStore(path)
    with sqlite3.connect(path) as c:
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert "reports" in names


def test_save_and_get_preserves_structure(store, sample):
    store.save(sample)
    assert store.get(sample["id"]) == sample


def test_get_missing_returns_none(store):
    assert store.get("nope") is None


def test_list_empty(store):
    assert store.list() == []


def test_list_newest_first(store, sample):
    old = {**sample, "id": "a", "createdAt": "2026-11-17T00:00:00+09:00"}
    new = {**sample, "id": "b", "createdAt": "2026-11-18T00:00:00+09:00"}
    store.save(old)
    store.save(new)
    assert [r["id"] for r in store.list()] == ["b", "a"]


def test_resave_same_id_overwrites(store, sample):
    store.save(sample)
    store.save({**sample, "status": "resolved"})
    assert len(store.list()) == 1
    assert store.get(sample["id"])["status"] == "resolved"


def test_persists_across_instances(tmp_path, sample):
    ReportStore(tmp_path / "p.db").save(sample)
    assert ReportStore(tmp_path / "p.db").get(sample["id"]) == sample


def _ids(store):
    return [r["id"] for r in store.list()]


def test_list_missing_created_at_is_oldest(store, sample):
    no_field = {k: v for k, v in sample.items() if k != "createdAt"}
    store.save({**no_field, "id": "none"})
    store.save({**sample, "id": "ok", "createdAt": "2026-11-18T00:00:00+09:00"})
    assert _ids(store) == ["ok", "none"]


@pytest.mark.parametrize("bad", ["not-a-date", "", None, 123])
def test_list_invalid_created_at_is_oldest(store, sample, bad):
    store.save({**sample, "id": "bad", "createdAt": bad})
    store.save({**sample, "id": "ok", "createdAt": "2026-11-18T00:00:00+09:00"})
    assert _ids(store) == ["ok", "bad"]


def test_list_mixed_aware_and_naive(store, sample):
    # naive 는 UTC 로 간주: 10:00 UTC(naive) vs 10:00+09:00 = 01:00 UTC
    store.save({**sample, "id": "naive", "createdAt": "2026-11-18T10:00:00"})
    store.save({**sample, "id": "aware", "createdAt": "2026-11-18T10:00:00+09:00"})
    assert _ids(store) == ["naive", "aware"]


def test_list_different_utc_offsets(store, sample):
    # 실제 시각: a=00:00Z, b=02:00-05:00 → 07:00Z, c=08:00+09:00 → 전날 23:00Z
    store.save({**sample, "id": "a", "createdAt": "2026-11-18T00:00:00+00:00"})
    store.save({**sample, "id": "b", "createdAt": "2026-11-18T02:00:00-05:00"})
    store.save({**sample, "id": "c", "createdAt": "2026-11-18T08:00:00+09:00"})
    assert _ids(store) == ["b", "a", "c"]


def test_list_does_not_modify_created_at(store, sample):
    originals = {
        "naive": "2026-11-18T10:00:00",
        "bad": "not-a-date",
        "aware": "2026-11-18T10:00:00+09:00",
    }
    for rid, value in originals.items():
        store.save({**sample, "id": rid, "createdAt": value})
    assert {r["id"]: r["createdAt"] for r in store.list()} == originals
    assert store.get("naive")["createdAt"] == originals["naive"]
