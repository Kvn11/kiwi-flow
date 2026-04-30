"""Tests for the /mnt/skill-library virtual-path branches in kiwi.sandbox.tools."""

from pathlib import Path
from unittest.mock import patch

import pytest

from kiwi.sandbox.tools import (
    _is_library_path,
    _resolve_library_path,
    mask_local_paths_in_output,
    replace_virtual_paths_in_command,
    validate_local_bash_command_paths,
    validate_local_tool_path,
)

_THREAD_DATA = {
    "workspace_path": "/tmp/kiwi-flow/threads/t1/user-data/workspace",
    "uploads_path": "/tmp/kiwi-flow/threads/t1/user-data/uploads",
    "outputs_path": "/tmp/kiwi-flow/threads/t1/user-data/outputs",
}


@pytest.fixture(autouse=True)
def _clear_caches():
    # Reset module-level caches between tests so each test sees the patched value.
    from kiwi.sandbox import tools as sandbox_tools

    for name in (
        "_get_skills_container_path",
        "_get_skills_host_path",
        "_get_library_container_path",
        "_get_library_host_path",
        "_get_custom_mounts",
    ):
        fn = getattr(sandbox_tools, name)
        if hasattr(fn, "_cached"):
            delattr(fn, "_cached")
    yield


def test_is_library_path_recognises_root_and_subpaths():
    with patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"):
        assert _is_library_path("/mnt/skill-library")
        assert _is_library_path("/mnt/skill-library/foo/SKILL.md")
        assert not _is_library_path("/mnt/skills/public/foo/SKILL.md")
        assert not _is_library_path("/mnt/skill-library2")  # prefix-similar but not under


def test_resolve_library_path_maps_to_host(tmp_path: Path):
    with (
        patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"),
        patch("kiwi.sandbox.tools._get_library_host_path", return_value=str(tmp_path)),
    ):
        resolved = _resolve_library_path("/mnt/skill-library/foo/SKILL.md")
        assert resolved == f"{tmp_path}/foo/SKILL.md"

        # Container root maps directly to host root
        assert _resolve_library_path("/mnt/skill-library") == str(tmp_path)


def test_resolve_library_path_raises_when_host_unavailable():
    with (
        patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"),
        patch("kiwi.sandbox.tools._get_library_host_path", return_value=None),
    ):
        with pytest.raises(FileNotFoundError):
            _resolve_library_path("/mnt/skill-library/foo/SKILL.md")


def test_validate_local_tool_path_allows_library_read():
    with patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"):
        # Should not raise
        validate_local_tool_path("/mnt/skill-library/foo/SKILL.md", _THREAD_DATA, read_only=True)


def test_validate_local_tool_path_rejects_library_write():
    with patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"):
        with pytest.raises(PermissionError, match="skill library"):
            validate_local_tool_path("/mnt/skill-library/foo/SKILL.md", _THREAD_DATA, read_only=False)


def test_validate_local_tool_path_rejects_library_traversal():
    with patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"):
        with pytest.raises(PermissionError, match="path traversal"):
            validate_local_tool_path("/mnt/skill-library/../../etc/passwd", _THREAD_DATA, read_only=True)


def test_validate_local_bash_command_paths_allows_library():
    with patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"):
        # Should not raise
        validate_local_bash_command_paths("cat /mnt/skill-library/foo/SKILL.md", _THREAD_DATA)


def test_replace_virtual_paths_in_command_substitutes_library(tmp_path: Path):
    with (
        patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"),
        patch("kiwi.sandbox.tools._get_library_host_path", return_value=str(tmp_path)),
    ):
        cmd = "cat /mnt/skill-library/foo/SKILL.md"
        result = replace_virtual_paths_in_command(cmd, _THREAD_DATA)
        assert result == f"cat {tmp_path}/foo/SKILL.md"


def test_mask_local_paths_in_output_masks_library(tmp_path: Path):
    """Host library paths in tool output should be rewritten to virtual /mnt/skill-library form."""
    with (
        patch("kiwi.sandbox.tools._get_library_container_path", return_value="/mnt/skill-library"),
        patch("kiwi.sandbox.tools._get_library_host_path", return_value=str(tmp_path)),
    ):
        raw = f"loaded from {tmp_path}/foo/SKILL.md successfully"
        masked = mask_local_paths_in_output(raw, _THREAD_DATA)
        assert "/mnt/skill-library/foo/SKILL.md" in masked
        assert str(tmp_path) not in masked
