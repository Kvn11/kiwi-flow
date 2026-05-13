"""Unit tests for `kiwi.credentials.parser.parse_skill_credentials`."""

from __future__ import annotations

from pathlib import Path

import pytest

from kiwi.credentials import CredentialField, CredentialSchema, parse_skill_credentials


def _write_skill(tmp_path: Path, frontmatter: str, body: str = "") -> Path:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(f"---\n{frontmatter}\n---\n{body}", encoding="utf-8")
    return skill_file


def test_returns_none_when_file_missing(tmp_path: Path) -> None:
    assert parse_skill_credentials(tmp_path / "SKILL.md") is None


def test_returns_none_when_filename_wrong(tmp_path: Path) -> None:
    other = tmp_path / "README.md"
    other.write_text("---\nname: x\ndescription: y\n---\n", encoding="utf-8")
    assert parse_skill_credentials(other) is None


def test_returns_none_when_no_frontmatter(tmp_path: Path) -> None:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("# Hello\nNo frontmatter here.\n", encoding="utf-8")
    assert parse_skill_credentials(skill_file) is None


def test_returns_none_when_no_credentials_block(tmp_path: Path) -> None:
    skill_file = _write_skill(tmp_path, "name: foo\ndescription: bar")
    assert parse_skill_credentials(skill_file) is None


def test_parses_minimal_credentials_block(tmp_path: Path) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: kalshi",
                "description: Trade prediction markets",
                "credentials:",
                "  fields:",
                "    - { name: api_key_id, label: 'API Key ID', type: text }",
                "    - { name: api_private_key, label: 'Private Key (PEM)', type: textarea }",
            ]
        ),
    )

    schema = parse_skill_credentials(skill_file)

    assert schema == CredentialSchema(
        skill_name="kalshi",
        fields=(
            CredentialField(name="api_key_id", label="API Key ID", type="text"),
            CredentialField(name="api_private_key", label="Private Key (PEM)", type="textarea"),
        ),
    )


def test_defaults_type_to_text(tmp_path: Path) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: bar",
                "credentials:",
                "  fields:",
                "    - { name: api_key, label: 'API Key' }",
            ]
        ),
    )
    schema = parse_skill_credentials(skill_file)
    assert schema is not None
    assert schema.fields[0].type == "text"


def test_rejects_invalid_type(tmp_path: Path) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: bar",
                "credentials:",
                "  fields:",
                "    - { name: x, label: 'X', type: number }",
            ]
        ),
    )
    assert parse_skill_credentials(skill_file) is None


def test_rejects_missing_name(tmp_path: Path) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: bar",
                "credentials:",
                "  fields:",
                "    - { label: 'X' }",
            ]
        ),
    )
    assert parse_skill_credentials(skill_file) is None


def test_rejects_missing_label(tmp_path: Path) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: bar",
                "credentials:",
                "  fields:",
                "    - { name: x }",
            ]
        ),
    )
    assert parse_skill_credentials(skill_file) is None


def test_rejects_duplicate_field_names(tmp_path: Path) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: bar",
                "credentials:",
                "  fields:",
                "    - { name: api_key, label: 'A' }",
                "    - { name: api_key, label: 'B' }",
            ]
        ),
    )
    assert parse_skill_credentials(skill_file) is None


def test_rejects_empty_fields_list(tmp_path: Path) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: bar",
                "credentials:",
                "  fields: []",
            ]
        ),
    )
    assert parse_skill_credentials(skill_file) is None


def test_rejects_credentials_block_that_is_not_a_mapping(tmp_path: Path) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: bar",
                "credentials: [a, b, c]",
            ]
        ),
    )
    assert parse_skill_credentials(skill_file) is None


def test_returns_none_on_malformed_yaml(tmp_path: Path) -> None:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("---\nname: foo\n  bad indent: [unclosed\n---\n", encoding="utf-8")
    assert parse_skill_credentials(skill_file) is None


def test_existing_skill_parser_unaffected_by_credentials_block(tmp_path: Path) -> None:
    """Defense in depth: the credentials block must NOT leak into Skill metadata."""
    from kiwi.skills.parser import parse_skill_file

    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: A skill that needs credentials",
                "credentials:",
                "  fields:",
                "    - { name: api_key, label: 'API Key' }",
            ]
        ),
    )

    skill = parse_skill_file(skill_file, category="custom")
    assert skill is not None
    assert skill.name == "foo"
    assert skill.description == "A skill that needs credentials"
    # The Skill object must NOT carry any 'credentials' attribute.
    assert not hasattr(skill, "credentials")
    assert not hasattr(skill, "credentials_schema")


@pytest.mark.parametrize("input_type", ["text", "textarea"])
def test_accepts_valid_types(tmp_path: Path, input_type: str) -> None:
    skill_file = _write_skill(
        tmp_path,
        "\n".join(
            [
                "name: foo",
                "description: bar",
                "credentials:",
                "  fields:",
                f"    - {{ name: x, label: 'X', type: {input_type} }}",
            ]
        ),
    )
    schema = parse_skill_credentials(skill_file)
    assert schema is not None
    assert schema.fields[0].type == input_type
