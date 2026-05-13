"""On-disk credential store: a single JSON file at `$KIWI_FLOW_HOME/credentials.json`.

The file is created with mode 0o600 and lives outside every sandbox `/mnt/*`
mapping. Concurrent access from the Gateway process and the LangGraph runtime
is serialized via an exclusive `fcntl.flock` on a sidecar `.lock` file (POSIX);
the lock is best-effort on platforms where `fcntl` is unavailable.

Public API: a `CredentialStore` class with read/write/delete operations. The
broker is the only intended consumer — skill code should call broker functions,
not this class directly.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .types import StoredEntry, Token

logger = logging.getLogger(__name__)

try:
    import fcntl  # POSIX only

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover — Windows / non-POSIX
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False


_FILE_MODE = 0o600
_DIR_MODE = 0o700


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class CredentialStore:
    """Atomic, locked, mode-0o600 JSON store for skill credentials and tokens."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            from kiwi.config.paths import get_paths

            path = get_paths().credentials_file
        self._path = Path(path)
        self._lock_path = self._path.with_suffix(self._path.suffix + ".lock")

    @property
    def path(self) -> Path:
        return self._path

    # ── Public API ───────────────────────────────────────────────────────

    def read_all(self) -> dict[str, StoredEntry]:
        """Return all entries as a dict keyed by skill name. Empty dict if file missing."""
        with self._locked():
            raw = self._read_raw()
        return {name: self._entry_from_dict(value) for name, value in raw.items() if isinstance(value, dict)}

    def read_one(self, skill_name: str) -> StoredEntry | None:
        with self._locked():
            raw = self._read_raw()
        entry = raw.get(skill_name)
        if not isinstance(entry, dict):
            return None
        return self._entry_from_dict(entry)

    def write_values(self, skill_name: str, values: dict[str, str]) -> None:
        """Replace the `values` dict for a skill. Token is left untouched.

        Empty-string values are kept as empty strings (treated as "field cleared"
        by the broker). To remove a field entirely, omit it.
        """
        self._update_entry(skill_name, lambda entry: entry.update({"values": dict(values)}))

    def merge_values(self, skill_name: str, partial: dict[str, str]) -> StoredEntry:
        """Atomic read-modify-write: merge `partial` into the existing values dict.

        Used by the broker's PUT path so two concurrent partial updates can't lose
        each other's keys. Returns the post-merge entry so callers don't need a
        second read to compute status.
        """
        new_raw = self._update_entry(
            skill_name,
            lambda entry: entry.update({"values": {**entry.get("values", {}), **partial}}),
        )
        return self._entry_from_dict(new_raw)

    def write_token(self, skill_name: str, token: Token | None) -> None:
        """Set or clear the cached token for a skill. Values are left untouched.

        If the skill has no entry yet, a new entry is created with empty values.
        """

        def mutate(entry: dict[str, Any]) -> None:
            if token is None:
                entry.pop("token", None)
            else:
                entry["token"] = {
                    "access_token": token.access_token,
                    "expires_at": token.expires_at,
                    "scope": token.scope,
                }
            entry.setdefault("values", {})

        self._update_entry(skill_name, mutate, touch_updated_at=False)

    def delete(self, skill_name: str) -> None:
        """Remove the entry for a skill entirely (both values and token). Idempotent."""
        with self._locked():
            raw = self._read_raw()
            if raw.pop(skill_name, None) is not None:
                self._atomic_write(raw)

    def _update_entry(
        self,
        skill_name: str,
        mutate: Callable[[dict[str, Any]], None],
        *,
        touch_updated_at: bool = True,
    ) -> dict[str, Any]:
        """Locked read-modify-write of a single entry. Returns the resulting raw dict."""
        with self._locked():
            raw = self._read_raw()
            entry = raw.get(skill_name)
            if not isinstance(entry, dict):
                entry = {}
            mutate(entry)
            if touch_updated_at:
                entry["updated_at"] = _utcnow_iso()
            raw[skill_name] = entry
            self._atomic_write(raw)
            return entry

    def _read_raw(self) -> dict[str, Any]:
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("credentials.json at %s is unreadable (%s); treating as empty", self._path, exc)
            return {}
        if not isinstance(data, dict):
            logger.error("credentials.json at %s is not a JSON object; treating as empty", self._path)
            return {}
        return data

    def _atomic_write(self, data: dict[str, Any]) -> None:
        self._ensure_dir()
        # Use mkstemp in the same directory so os.replace is atomic on the same filesystem.
        # Set mode 0o600 immediately on the temp file so the final file is created with
        # restrictive permissions — relying on os.replace to *preserve* mode would leave
        # a brief window with default umask permissions on first creation.
        fd, tmp_path = tempfile.mkstemp(prefix=".credentials-", suffix=".json.tmp", dir=str(self._path.parent))
        try:
            os.fchmod(fd, _FILE_MODE)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
        # Defensive re-chmod after replace in case the destination already existed
        # with a different mode (some platforms preserve dest mode).
        with contextlib.suppress(OSError):
            os.chmod(self._path, _FILE_MODE)

    def _ensure_dir(self) -> None:
        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True)
        # Tighten only if the dir looks freshly umask-created — don't downgrade a mode
        # the user deliberately set more permissively.
        try:
            current_mode = parent.stat().st_mode & 0o777
            if current_mode in (0o755, 0o775, 0o777):
                os.chmod(parent, _DIR_MODE)
        except OSError:
            pass

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        """Acquire an exclusive file lock for the duration of the block."""
        if not _HAS_FCNTL:
            # No-op on platforms without fcntl; rely on cooperative use.
            yield
            return
        self._ensure_dir()
        # Open the lock file separately so unlinking the credentials file doesn't
        # break the lock; create it lazily.
        lock_fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    @staticmethod
    def _entry_from_dict(raw: dict[str, Any]) -> StoredEntry:
        values = raw.get("values")
        if not isinstance(values, dict):
            values = {}
        # Coerce all values to str — they should already be, but defensive.
        clean_values: dict[str, str] = {str(k): ("" if v is None else str(v)) for k, v in values.items()}

        token: Token | None = None
        token_raw = raw.get("token")
        if isinstance(token_raw, dict):
            access = token_raw.get("access_token")
            if isinstance(access, str) and access:
                expires_at = token_raw.get("expires_at")
                if not isinstance(expires_at, int):
                    expires_at = None
                scope = token_raw.get("scope")
                if scope is not None and not isinstance(scope, str):
                    scope = None
                token = Token(access_token=access, expires_at=expires_at, scope=scope)

        updated_at = raw.get("updated_at")
        if not isinstance(updated_at, str):
            updated_at = None

        return StoredEntry(values=clean_values, token=token, updated_at=updated_at)
