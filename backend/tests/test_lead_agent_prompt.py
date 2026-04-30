import threading
from types import SimpleNamespace

import anyio

from kiwi.agents.lead_agent import prompt as prompt_module
from kiwi.skills.types import Skill


def test_build_custom_mounts_section_returns_empty_when_no_mounts(monkeypatch):
    config = SimpleNamespace(sandbox=SimpleNamespace(mounts=[]))
    monkeypatch.setattr("kiwi.config.get_app_config", lambda: config)

    assert prompt_module._build_custom_mounts_section() == ""


def test_build_custom_mounts_section_lists_configured_mounts(monkeypatch):
    mounts = [
        SimpleNamespace(container_path="/home/user/shared", read_only=False),
        SimpleNamespace(container_path="/mnt/reference", read_only=True),
    ]
    config = SimpleNamespace(sandbox=SimpleNamespace(mounts=mounts))
    monkeypatch.setattr("kiwi.config.get_app_config", lambda: config)

    section = prompt_module._build_custom_mounts_section()

    assert "**Custom Mounted Directories:**" in section
    assert "`/home/user/shared`" in section
    assert "read-write" in section
    assert "`/mnt/reference`" in section
    assert "read-only" in section


def test_apply_prompt_template_includes_custom_mounts(monkeypatch):
    mounts = [SimpleNamespace(container_path="/home/user/shared", read_only=False)]
    config = SimpleNamespace(
        sandbox=SimpleNamespace(mounts=mounts),
        skills=SimpleNamespace(container_path="/mnt/skills"),
    )
    monkeypatch.setattr("kiwi.config.get_app_config", lambda: config)
    monkeypatch.setattr(prompt_module, "_get_enabled_skills", lambda: [])
    monkeypatch.setattr(prompt_module, "get_deferred_tools_prompt_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_build_acp_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_get_memory_context", lambda agent_name=None: "")
    monkeypatch.setattr(prompt_module, "get_agent_soul", lambda agent_name=None: "")

    prompt = prompt_module.apply_prompt_template()

    assert "`/home/user/shared`" in prompt
    assert "Custom Mounted Directories" in prompt


def test_apply_prompt_template_includes_relative_path_guidance(monkeypatch):
    config = SimpleNamespace(
        sandbox=SimpleNamespace(mounts=[]),
        skills=SimpleNamespace(container_path="/mnt/skills"),
    )
    monkeypatch.setattr("kiwi.config.get_app_config", lambda: config)
    monkeypatch.setattr(prompt_module, "_get_enabled_skills", lambda: [])
    monkeypatch.setattr(prompt_module, "get_deferred_tools_prompt_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_build_acp_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_get_memory_context", lambda agent_name=None: "")
    monkeypatch.setattr(prompt_module, "get_agent_soul", lambda agent_name=None: "")

    prompt = prompt_module.apply_prompt_template()

    assert "Treat `/mnt/user-data/workspace` as your default current working directory" in prompt
    assert "`hello.txt`, `../uploads/data.csv`, and `../outputs/report.md`" in prompt


def test_refresh_skills_system_prompt_cache_async_reloads_immediately(monkeypatch, tmp_path):
    def make_skill(name: str) -> Skill:
        skill_dir = tmp_path / name
        return Skill(
            name=name,
            description=f"Description for {name}",
            license="MIT",
            skill_dir=skill_dir,
            skill_file=skill_dir / "SKILL.md",
            relative_path=skill_dir.relative_to(tmp_path),
            category="custom",
            enabled=True,
        )

    state = {"skills": [make_skill("first-skill")]}
    monkeypatch.setattr(prompt_module, "load_skills", lambda enabled_only=True: list(state["skills"]))
    prompt_module._reset_skills_system_prompt_cache_state()

    try:
        prompt_module.warm_enabled_skills_cache()
        assert [skill.name for skill in prompt_module._get_enabled_skills()] == ["first-skill"]

        state["skills"] = [make_skill("second-skill")]
        anyio.run(prompt_module.refresh_skills_system_prompt_cache_async)

        assert [skill.name for skill in prompt_module._get_enabled_skills()] == ["second-skill"]
    finally:
        prompt_module._reset_skills_system_prompt_cache_state()


def test_clear_cache_does_not_spawn_parallel_refresh_workers(monkeypatch, tmp_path):
    started = threading.Event()
    release = threading.Event()
    active_loads = 0
    max_active_loads = 0
    call_count = 0
    lock = threading.Lock()

    def make_skill(name: str) -> Skill:
        skill_dir = tmp_path / name
        return Skill(
            name=name,
            description=f"Description for {name}",
            license="MIT",
            skill_dir=skill_dir,
            skill_file=skill_dir / "SKILL.md",
            relative_path=skill_dir.relative_to(tmp_path),
            category="custom",
            enabled=True,
        )

    def fake_load_skills(enabled_only=True):
        nonlocal active_loads, max_active_loads, call_count
        with lock:
            active_loads += 1
            max_active_loads = max(max_active_loads, active_loads)
            call_count += 1
            current_call = call_count

        started.set()
        if current_call == 1:
            release.wait(timeout=5)

        with lock:
            active_loads -= 1

        return [make_skill(f"skill-{current_call}")]

    monkeypatch.setattr(prompt_module, "load_skills", fake_load_skills)
    prompt_module._reset_skills_system_prompt_cache_state()

    try:
        prompt_module.clear_skills_system_prompt_cache()
        assert started.wait(timeout=5)

        prompt_module.clear_skills_system_prompt_cache()
        release.set()
        prompt_module.warm_enabled_skills_cache()

        assert max_active_loads == 1
        assert [skill.name for skill in prompt_module._get_enabled_skills()] == ["skill-2"]
    finally:
        release.set()
        prompt_module._reset_skills_system_prompt_cache_state()


def test_warm_enabled_skills_cache_logs_on_timeout(monkeypatch, caplog):
    event = threading.Event()
    monkeypatch.setattr(prompt_module, "_ensure_enabled_skills_cache", lambda: event)

    with caplog.at_level("WARNING"):
        warmed = prompt_module.warm_enabled_skills_cache(timeout_seconds=0.01)

    assert warmed is False
    assert "Timed out waiting" in caplog.text


# ---------------------------------------------------------------------------
# Discover section (skill_search) — gated on skill_library state
# ---------------------------------------------------------------------------


def _make_registry(length: int):
    """Build a tiny stand-in for SkillLibraryRegistry that supports ``len()``.

    SimpleNamespace can't carry a working ``__len__`` because dunder lookup
    bypasses instance attributes, so we use a small class instead.
    """

    class _Reg:
        def __len__(self) -> int:
            return length

    return _Reg()


def _patch_library_state(monkeypatch, *, enabled: bool, registry_len: int) -> None:
    """Configure the skill library so _is_skill_library_active returns the desired result."""
    config = SimpleNamespace(
        sandbox=SimpleNamespace(mounts=[]),
        skills=SimpleNamespace(container_path="/mnt/skills"),
        skill_library=SimpleNamespace(enabled=enabled),
        skill_evolution=SimpleNamespace(enabled=False),
    )
    monkeypatch.setattr("kiwi.config.get_app_config", lambda: config)
    monkeypatch.setattr(
        "kiwi.skill_library.registry.get_library_registry",
        lambda: _make_registry(registry_len),
    )


def test_is_skill_library_active_returns_false_when_master_switch_disabled(monkeypatch):
    _patch_library_state(monkeypatch, enabled=False, registry_len=3)
    assert prompt_module._is_skill_library_active() is False


def test_is_skill_library_active_returns_false_when_registry_empty(monkeypatch):
    _patch_library_state(monkeypatch, enabled=True, registry_len=0)
    assert prompt_module._is_skill_library_active() is False


def test_is_skill_library_active_returns_true_when_enabled_and_populated(monkeypatch):
    _patch_library_state(monkeypatch, enabled=True, registry_len=2)
    assert prompt_module._is_skill_library_active() is True


def test_is_skill_library_active_returns_false_when_config_load_fails(monkeypatch, caplog):
    def _raise():
        raise RuntimeError("config exploded")

    monkeypatch.setattr("kiwi.config.get_app_config", _raise)

    with caplog.at_level("DEBUG", logger=prompt_module.__name__):
        assert prompt_module._is_skill_library_active() is False

    # Per-render path uses debug-level logging to avoid spam.
    assert "Failed to load app config" in caplog.text


def test_is_skill_library_active_returns_false_when_registry_load_fails(monkeypatch, caplog):
    config = SimpleNamespace(
        skill_library=SimpleNamespace(enabled=True),
    )
    monkeypatch.setattr("kiwi.config.get_app_config", lambda: config)

    def _raise():
        raise RuntimeError("registry exploded")

    monkeypatch.setattr("kiwi.skill_library.registry.get_library_registry", _raise)

    with caplog.at_level("DEBUG", logger=prompt_module.__name__):
        assert prompt_module._is_skill_library_active() is False

    assert "Failed to load skill library registry" in caplog.text


def test_build_discover_section_empty_when_inactive(monkeypatch):
    _patch_library_state(monkeypatch, enabled=False, registry_len=0)
    assert prompt_module._build_discover_section() == ""


def test_build_discover_section_contains_workflow_when_active(monkeypatch):
    _patch_library_state(monkeypatch, enabled=True, registry_len=1)

    section = prompt_module._build_discover_section()

    assert section.startswith("<discover_system>")
    assert section.endswith("</discover_system>")
    assert "DISCOVER → CLARIFY → PLAN → ACT" in section
    assert "skill_search(" in section
    # Must explicitly tell the agent to search before clarification/planning.
    assert "BEFORE `ask_clarification`" in section
    assert "BEFORE `write_todos`" in section


def _patch_template_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(prompt_module, "_get_enabled_skills", lambda: [])
    monkeypatch.setattr(prompt_module, "get_deferred_tools_prompt_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_build_acp_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_build_custom_mounts_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_get_memory_context", lambda agent_name=None: "")
    monkeypatch.setattr(prompt_module, "get_agent_soul", lambda agent_name=None: "")


def test_apply_prompt_template_includes_discover_section_when_library_active(monkeypatch):
    _patch_library_state(monkeypatch, enabled=True, registry_len=2)
    _patch_template_dependencies(monkeypatch)

    rendered = prompt_module.apply_prompt_template()

    # The actual section opens at the start of a line; the clarification system
    # only references it in prose. Distinguish by anchoring on a body marker.
    assert "<discover_system>\n**WORKFLOW PRIORITY" in rendered
    assert "MANDATORY FIRST STEP for non-trivial requests" in rendered


def test_apply_prompt_template_excludes_discover_section_when_library_inactive(monkeypatch):
    _patch_library_state(monkeypatch, enabled=True, registry_len=0)
    _patch_template_dependencies(monkeypatch)

    rendered = prompt_module.apply_prompt_template()

    assert "<discover_system>\n**WORKFLOW PRIORITY" not in rendered
    assert "MANDATORY FIRST STEP for non-trivial requests" not in rendered
    # The clarification system header always lists the new ordering for clarity,
    # even when no discover phase is active in the current render.
    assert "WORKFLOW PRIORITY: DISCOVER → CLARIFY → PLAN → ACT" in rendered
