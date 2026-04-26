"""skill_search — discover specialized skills from the on-demand library.

The skill library (skill-library/<name>/SKILL.md) contains specialized
workflows that are NOT injected into the system prompt up front. The agent
calls this tool with a regex/keyword query to find candidates, then
read_files the returned path to load the workflow.

Mirrors the deferred-tool pattern in tool_search but for SKILL.md files.
There is no "promote" step — once the agent has the path, it loads the
content via the existing sandbox read_file tool.
"""

import json
import logging

from langchain_core.tools import tool

from deerflow.skill_library.registry import MAX_RESULTS, get_library_registry

logger = logging.getLogger(__name__)


@tool
def skill_search(query: str) -> str:
    """Discover specialized skills from the skill library by name/description match.

    The skill library contains specialized workflows that are NOT loaded into
    your context up front. Search for them when a user task matches. Each
    result includes the SKILL.md path — call `read_file` on it to load the
    full workflow before executing.

    Query forms:
      - "select:name1,name2"  — fetch these exact skills by name
      - "+keyword rest"       — require "keyword" in the name, rank by rest
      - "data analysis"       — regex/keyword search over name + description

    Args:
        query: Pattern to find skills. Use "select:<name>" for direct lookup,
               or keywords/regex to search.

    Returns:
        JSON array of {name, description, path}. Empty list when no matches.
    """
    registry = get_library_registry()
    if registry is None or len(registry) == 0:
        return "No skill library available."

    matched = registry.search(query, max_results=MAX_RESULTS)
    if not matched:
        return f"No skills found matching: {query}"

    return json.dumps(
        [{"name": e.name, "description": e.description, "path": e.container_path} for e in matched],
        indent=2,
        ensure_ascii=False,
    )
