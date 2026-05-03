"""LLM and search provider definitions for the Setup Wizard."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LLMProvider:
    name: str
    display_name: str
    description: str
    use: str
    models: list[str]
    default_model: str
    env_var: str | None
    package: str | None
    # Optional: some providers use a different field name for the API key in YAML
    api_key_field: str = "api_key"
    # Extra config fields beyond the common ones (merged into YAML)
    extra_config: dict = field(default_factory=dict)
    # Per-model overrides deep-merged on top of extra_config when that model is selected
    model_overrides: dict[str, dict] = field(default_factory=dict)
    auth_hint: str | None = None

    def effective_extra_config(self, model_name: str) -> dict:
        """Return extra_config deep-merged with any per-model overrides."""
        return _deep_merge(self.extra_config, self.model_overrides.get(model_name, {}))


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base without mutating either input."""
    result = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class WebProvider:
    name: str
    display_name: str
    description: str
    use: str
    env_var: str | None  # None = no API key required
    tool_name: str
    extra_config: dict = field(default_factory=dict)


@dataclass
class SearchProvider:
    name: str
    display_name: str
    description: str
    use: str
    env_var: str | None  # None = no API key required
    tool_name: str = "web_search"
    extra_config: dict = field(default_factory=dict)


LLM_PROVIDERS: list[LLMProvider] = [
    LLMProvider(
        name="openai",
        display_name="OpenAI",
        description="GPT-5.5 / GPT-5.4 / o3 / o4-mini (reasoning)",
        use="langchain_openai:ChatOpenAI",
        models=["gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "o3", "o4-mini"],
        default_model="gpt-5.5",
        env_var="OPENAI_API_KEY",
        package="langchain-openai",
        extra_config={
            "request_timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 16384,
            "use_responses_api": True,
            "output_version": "responses/v1",
            "supports_thinking": True,
            "supports_reasoning_effort": True,
            "supports_vision": True,
            "when_thinking_enabled": {"reasoning_effort": "medium"},
            "when_thinking_disabled": {"reasoning_effort": "low"},
        },
        # gpt-5.5-pro defaults to "high" effort when thinking is enabled
        model_overrides={
            "gpt-5.5-pro": {
                "when_thinking_enabled": {"reasoning_effort": "high"},
            },
        },
    ),
    LLMProvider(
        name="anthropic",
        display_name="Anthropic",
        description="Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 (extended thinking)",
        use="langchain_anthropic:ChatAnthropic",
        models=["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
        default_model="claude-sonnet-4-6",
        env_var="ANTHROPIC_API_KEY",
        package="langchain-anthropic",
        extra_config={
            "default_request_timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 16384,
            "supports_thinking": True,
            "supports_vision": True,
            "when_thinking_enabled": {
                "thinking": {"type": "enabled", "budget_tokens": 8192},
            },
            "when_thinking_disabled": {
                "thinking": {"type": "disabled"},
            },
        },
    ),
    LLMProvider(
        name="deepseek",
        display_name="DeepSeek",
        description="V4 / V4-flash (thinking mode supported)",
        use="kiwi.models.patched_deepseek:PatchedChatDeepSeek",
        models=["deepseek-v4", "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-reasoner", "deepseek-chat"],
        default_model="deepseek-v4",
        env_var="DEEPSEEK_API_KEY",
        package="langchain-deepseek",
        extra_config={
            "max_tokens": 8192,
            "supports_thinking": True,
            "when_thinking_enabled": {
                "extra_body": {"thinking": {"type": "enabled"}},
            },
            "when_thinking_disabled": {
                "extra_body": {"thinking": {"type": "disabled"}},
            },
        },
    ),
    LLMProvider(
        name="google",
        display_name="Google Gemini",
        description="Gemini 3.1 Pro / 3 Flash (Deep Think)",
        use="langchain_google_genai:ChatGoogleGenerativeAI",
        models=["gemini-3.1-pro", "gemini-3-pro", "gemini-3-flash"],
        default_model="gemini-3.1-pro",
        env_var="GEMINI_API_KEY",
        package="langchain-google-genai",
        api_key_field="gemini_api_key",
        extra_config={
            "timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 16384,
            "supports_vision": True,
        },
    ),
    LLMProvider(
        name="openrouter",
        display_name="OpenRouter",
        description="OpenAI-compatible gateway with broad model catalog",
        use="langchain_openai:ChatOpenAI",
        models=[
            "anthropic/claude-opus-4-7",
            "anthropic/claude-sonnet-4-6",
            "openai/gpt-5.5",
            "openai/gpt-5.4",
            "google/gemini-3.1-pro",
            "google/gemini-3-flash",
            "deepseek/deepseek-v4",
        ],
        default_model="anthropic/claude-sonnet-4-6",
        env_var="OPENROUTER_API_KEY",
        package="langchain-openai",
        extra_config={
            "base_url": "https://openrouter.ai/api/v1",
            "request_timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 16384,
            "temperature": 0.7,
        },
    ),
    LLMProvider(
        name="vllm",
        display_name="vLLM",
        description="Self-hosted OpenAI-compatible serving",
        use="kiwi.models.vllm_provider:VllmChatModel",
        models=[
            "Qwen/Qwen3-235B-A22B-Thinking",
            "Qwen/Qwen3-32B",
            "Qwen/Qwen3-Coder-32B-Instruct",
            "deepseek-ai/DeepSeek-V4",
        ],
        default_model="Qwen/Qwen3-32B",
        env_var="VLLM_API_KEY",
        package=None,
        extra_config={
            "base_url": "http://localhost:8000/v1",
            "request_timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 8192,
            "supports_thinking": True,
            "supports_vision": False,
            "when_thinking_enabled": {
                "extra_body": {
                    "chat_template_kwargs": {
                        "enable_thinking": True,
                    }
                }
            },
        },
    ),
    LLMProvider(
        name="codex",
        display_name="Codex CLI",
        description="Uses Codex CLI local auth (~/.codex/auth.json)",
        use="kiwi.models.openai_codex_provider:CodexChatModel",
        models=["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"],
        default_model="gpt-5.5",
        env_var=None,
        package=None,
        api_key_field="api_key",
        extra_config={"supports_thinking": True, "supports_reasoning_effort": True},
        auth_hint="Uses existing Codex CLI auth from ~/.codex/auth.json",
    ),
    LLMProvider(
        name="claude_code",
        display_name="Claude Code OAuth",
        description="Uses Claude Code local OAuth credentials",
        use="kiwi.models.claude_provider:ClaudeChatModel",
        models=["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
        default_model="claude-sonnet-4-6",
        env_var=None,
        package=None,
        extra_config={"max_tokens": 16384, "supports_thinking": True},
        auth_hint="Uses Claude Code OAuth credentials from your local machine",
    ),
    LLMProvider(
        name="other",
        display_name="Other OpenAI-compatible",
        description="Custom gateway with base_url and model name",
        use="langchain_openai:ChatOpenAI",
        models=["gpt-5.5"],
        default_model="gpt-5.5",
        env_var="OPENAI_API_KEY",
        package="langchain-openai",
    ),
]

SEARCH_PROVIDERS: list[SearchProvider] = [
    SearchProvider(
        name="ddg",
        display_name="DuckDuckGo (free, no key needed)",
        description="No API key required",
        use="kiwi.community.ddg_search.tools:web_search_tool",
        env_var=None,
        extra_config={"max_results": 5},
    ),
    SearchProvider(
        name="tavily",
        display_name="Tavily",
        description="Recommended, free tier available",
        use="kiwi.community.tavily.tools:web_search_tool",
        env_var="TAVILY_API_KEY",
        extra_config={"max_results": 5},
    ),
    SearchProvider(
        name="infoquest",
        display_name="InfoQuest",
        description="Higher quality vertical search, API key required",
        use="kiwi.community.infoquest.tools:web_search_tool",
        env_var="INFOQUEST_API_KEY",
        extra_config={"search_time_range": 10},
    ),
    SearchProvider(
        name="exa",
        display_name="Exa",
        description="Neural + keyword web search, API key required",
        use="kiwi.community.exa.tools:web_search_tool",
        env_var="EXA_API_KEY",
        extra_config={
            "max_results": 5,
            "search_type": "auto",
            "contents_max_characters": 1000,
        },
    ),
    SearchProvider(
        name="firecrawl",
        display_name="Firecrawl",
        description="Search + crawl via Firecrawl API",
        use="kiwi.community.firecrawl.tools:web_search_tool",
        env_var="FIRECRAWL_API_KEY",
        extra_config={"max_results": 5},
    ),
]

WEB_FETCH_PROVIDERS: list[WebProvider] = [
    WebProvider(
        name="jina_ai",
        display_name="Jina AI Reader",
        description="Good default reader, no API key required",
        use="kiwi.community.jina_ai.tools:web_fetch_tool",
        env_var=None,
        tool_name="web_fetch",
        extra_config={"timeout": 10},
    ),
    WebProvider(
        name="exa",
        display_name="Exa",
        description="API key required",
        use="kiwi.community.exa.tools:web_fetch_tool",
        env_var="EXA_API_KEY",
        tool_name="web_fetch",
    ),
    WebProvider(
        name="infoquest",
        display_name="InfoQuest",
        description="API key required",
        use="kiwi.community.infoquest.tools:web_fetch_tool",
        env_var="INFOQUEST_API_KEY",
        tool_name="web_fetch",
        extra_config={"timeout": 10, "fetch_time": 10, "navigation_timeout": 30},
    ),
    WebProvider(
        name="firecrawl",
        display_name="Firecrawl",
        description="Search-grade crawl with markdown output, API key required",
        use="kiwi.community.firecrawl.tools:web_fetch_tool",
        env_var="FIRECRAWL_API_KEY",
        tool_name="web_fetch",
    ),
]
