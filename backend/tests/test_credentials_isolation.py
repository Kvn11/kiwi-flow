"""Regression tests proving the credentials file cannot be reached via the sandbox.

Even with path-traversal attempts, the LLM's bash/file tools must never resolve
to `Paths.credentials_file`. This is the structural defense-in-depth backing the
"LLM cannot directly access" requirement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kiwi.config.paths import Paths


def test_credentials_file_is_not_inside_any_sandbox_mount(tmp_path: Path) -> None:
    paths = Paths(base_dir=tmp_path)
    cred_path = paths.credentials_file.resolve()

    for thread_id in ("t1", "alpha", "abc-123"):
        for sandbox_dir in (
            paths.sandbox_user_data_dir(thread_id),
            paths.sandbox_work_dir(thread_id),
            paths.sandbox_uploads_dir(thread_id),
            paths.sandbox_outputs_dir(thread_id),
            paths.acp_workspace_dir(thread_id),
        ):
            sandbox_root = sandbox_dir.resolve()
            # Credentials file must not live inside the sandbox root nor be the
            # sandbox root itself.
            assert cred_path != sandbox_root
            try:
                cred_path.relative_to(sandbox_root)
                pytest.fail(f"credentials_file is reachable from sandbox dir {sandbox_root}")
            except ValueError:
                pass  # not relative — good


def test_resolve_virtual_path_rejects_traversal_to_credentials(tmp_path: Path) -> None:
    """Path-traversal attempts via /mnt/user-data/../credentials.json must be rejected."""
    paths = Paths(base_dir=tmp_path)
    paths.ensure_thread_dirs("t1")
    # Make sure the credentials file actually exists, so a successful resolution would be obvious.
    paths.credentials_file.write_text("{}", encoding="utf-8")

    attacks = [
        "/mnt/user-data/../../../credentials.json",
        "/mnt/user-data/../../credentials.json",
        "/mnt/user-data/workspace/../../../credentials.json",
        "/mnt/user-data/uploads/../../../../credentials.json",
        "/mnt/user-data/outputs/../../../credentials.json",
    ]
    for path in attacks:
        with pytest.raises(ValueError):
            paths.resolve_virtual_path("t1", path)


def test_resolve_virtual_path_only_accepts_user_data_prefix(tmp_path: Path) -> None:
    """Only `/mnt/user-data/...` is a valid virtual path; other prefixes are rejected."""
    paths = Paths(base_dir=tmp_path)
    paths.ensure_thread_dirs("t1")

    bad_prefixes = [
        "/credentials.json",
        "/mnt/credentials.json",
        "/mnt/skills/credentials.json",
        "/mnt/anywhere-else/credentials.json",
        f"{tmp_path}/credentials.json",  # raw host path
    ]
    for path in bad_prefixes:
        with pytest.raises(ValueError):
            paths.resolve_virtual_path("t1", path)


def test_credentials_file_lives_alongside_memory_file(tmp_path: Path) -> None:
    """Sanity check: same parent dir as memory.json (i.e., $KIWI_FLOW_HOME)."""
    paths = Paths(base_dir=tmp_path)
    assert paths.credentials_file.parent == paths.memory_file.parent
    assert paths.credentials_file.parent == paths.base_dir
    assert paths.credentials_file.name == "credentials.json"
