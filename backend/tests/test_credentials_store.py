"""Tests for `kiwi.credentials.store.CredentialStore`.

Covers atomic write semantics, mode-0o600 enforcement, partial updates that
preserve unrelated entries/fields, and concurrent-access serialization via the
sidecar lock file.
"""

from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path

from kiwi.credentials import Token
from kiwi.credentials.store import CredentialStore


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_read_all_empty_when_file_missing(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    assert store.read_all() == {}


def test_write_values_creates_file_with_mode_0600(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "key"})

    assert store.path.exists()
    assert _mode(store.path) == 0o600


def test_write_values_round_trip(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("kalshi", {"api_key_id": "abc", "api_private_key": "PEM-DATA"})

    entry = store.read_one("kalshi")
    assert entry is not None
    assert entry.values == {"api_key_id": "abc", "api_private_key": "PEM-DATA"}
    assert entry.token is None
    assert entry.updated_at is not None  # ISO 8601 stamp set by write_values


def test_write_token_creates_entry_when_none_existed(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_token("kalshi", Token(access_token="tok", expires_at=1700000000, scope="trade"))

    entry = store.read_one("kalshi")
    assert entry is not None
    assert entry.values == {}
    assert entry.token == Token(access_token="tok", expires_at=1700000000, scope="trade")


def test_write_token_preserves_existing_values(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("kalshi", {"api_key_id": "abc"})
    store.write_token("kalshi", Token(access_token="tok"))

    entry = store.read_one("kalshi")
    assert entry is not None
    assert entry.values == {"api_key_id": "abc"}
    assert entry.token is not None
    assert entry.token.access_token == "tok"


def test_write_values_preserves_existing_token(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_token("kalshi", Token(access_token="tok"))
    store.write_values("kalshi", {"api_key_id": "abc"})

    entry = store.read_one("kalshi")
    assert entry is not None
    assert entry.values == {"api_key_id": "abc"}
    assert entry.token is not None
    assert entry.token.access_token == "tok"


def test_write_token_none_clears_just_the_token(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("kalshi", {"api_key_id": "abc"})
    store.write_token("kalshi", Token(access_token="tok"))

    store.write_token("kalshi", None)

    entry = store.read_one("kalshi")
    assert entry is not None
    assert entry.values == {"api_key_id": "abc"}
    assert entry.token is None


def test_delete_removes_entry_entirely(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("kalshi", {"api_key_id": "abc"})
    store.write_values("other", {"api_key_id": "xyz"})

    store.delete("kalshi")

    assert store.read_one("kalshi") is None
    assert store.read_one("other") is not None


def test_delete_missing_entry_is_no_op(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.delete("nonexistent")  # must not raise


def test_unrelated_skills_are_independent(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("a", {"k": "1"})
    store.write_values("b", {"k": "2"})
    store.write_token("a", Token(access_token="ta"))

    a = store.read_one("a")
    b = store.read_one("b")
    assert a is not None and b is not None
    assert a.values == {"k": "1"}
    assert b.values == {"k": "2"}
    assert a.token is not None and a.token.access_token == "ta"
    assert b.token is None


def test_atomic_write_does_not_leave_temp_files_on_success(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("kalshi", {"api_key_id": "abc"})

    leftover = list(tmp_path.glob(".credentials-*.json.tmp"))
    assert leftover == []


def test_corrupt_json_treated_as_empty(tmp_path: Path) -> None:
    cred_path = tmp_path / "credentials.json"
    cred_path.write_text("{not valid json", encoding="utf-8")
    store = CredentialStore(cred_path)

    # read_all returns empty dict instead of raising
    assert store.read_all() == {}

    # subsequent write succeeds and replaces the corrupt content
    store.write_values("kalshi", {"api_key_id": "abc"})
    parsed = json.loads(cred_path.read_text(encoding="utf-8"))
    assert "kalshi" in parsed


def test_concurrent_writes_do_not_corrupt_file(tmp_path: Path) -> None:
    """Many threads writing different skills concurrently — every entry should survive."""
    store = CredentialStore(tmp_path / "credentials.json")
    n_threads = 20
    barrier = threading.Barrier(n_threads)

    def worker(i: int) -> None:
        barrier.wait()
        store.write_values(f"skill-{i}", {"k": f"v{i}"})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_entries = store.read_all()
    assert set(all_entries.keys()) == {f"skill-{i}" for i in range(n_threads)}
    for i in range(n_threads):
        assert all_entries[f"skill-{i}"].values == {"k": f"v{i}"}


def test_lock_file_is_separate_from_credentials_file(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("kalshi", {"api_key_id": "abc"})

    assert store.path.exists()
    lock_path = store.path.with_suffix(store.path.suffix + ".lock")
    assert lock_path.exists()
    # Sanity: the credentials file does not contain lock metadata.
    parsed = json.loads(store.path.read_text(encoding="utf-8"))
    assert "kalshi" in parsed


def test_write_token_serialization_format(tmp_path: Path) -> None:
    """Lock down the on-disk JSON shape so consumers can rely on it."""
    store = CredentialStore(tmp_path / "credentials.json")
    store.write_values("kalshi", {"api_key_id": "abc"})
    store.write_token("kalshi", Token(access_token="tok", expires_at=1700000000, scope="trade"))

    parsed = json.loads(store.path.read_text(encoding="utf-8"))
    assert "kalshi" in parsed
    entry = parsed["kalshi"]
    assert entry["values"] == {"api_key_id": "abc"}
    assert entry["token"] == {"access_token": "tok", "expires_at": 1700000000, "scope": "trade"}
    assert isinstance(entry["updated_at"], str)


def test_existing_file_with_default_mode_is_chmodded_to_0600(tmp_path: Path) -> None:
    cred_path = tmp_path / "credentials.json"
    cred_path.write_text("{}", encoding="utf-8")
    os.chmod(cred_path, 0o644)

    store = CredentialStore(cred_path)
    store.write_values("kalshi", {"api_key_id": "abc"})

    assert _mode(cred_path) == 0o600


def _delay_for_lock_test_seconds() -> float:
    """Tunable delay used by the lock-serialization test."""
    return 0.05


def test_lock_serializes_writers(tmp_path: Path, monkeypatch) -> None:
    """If two threads enter write_values, the second observes the first's effects."""
    store = CredentialStore(tmp_path / "credentials.json")

    # Slow down the first write so the second has to wait on the lock.
    real_atomic_write = store._atomic_write

    delay = _delay_for_lock_test_seconds()

    def slow_write(data):
        time.sleep(delay)
        return real_atomic_write(data)

    monkeypatch.setattr(store, "_atomic_write", slow_write)

    results: list[dict[str, str]] = []

    def writer1():
        store.write_values("kalshi", {"api_key_id": "first"})

    def writer2():
        # Small head-start to ensure writer1 has acquired the lock.
        time.sleep(delay / 4)
        # Restore fast write for writer2 so the test doesn't drag.
        monkeypatch.setattr(store, "_atomic_write", real_atomic_write)
        store.write_values("kalshi", {"api_key_id": "second"})
        entry = store.read_one("kalshi")
        if entry is not None:
            results.append(entry.values)

    t1 = threading.Thread(target=writer1)
    t2 = threading.Thread(target=writer2)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    final = store.read_one("kalshi")
    assert final is not None
    # The second writer's value wins because lock-serialization means it ran AFTER the first.
    assert final.values == {"api_key_id": "second"}
    # And writer2 observed the second value when it read.
    assert results == [{"api_key_id": "second"}]
