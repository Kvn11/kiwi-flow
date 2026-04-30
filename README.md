# Kiwi

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-22%2B-339933?logo=node.js&logoColor=white)](./Makefile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

> [!IMPORTANT]
> **This repository is a fork of the original [DeerFlow](https://github.com/bytedance/deer-flow) project by ByteDance.** It is maintained independently and may diverge from upstream. For the canonical project, see [bytedance/deer-flow](https://github.com/bytedance/deer-flow).

Kiwi is a fork of DeerFlow — a LangGraph-based super agent harness that orchestrates sub-agents, memory, and sandboxes to do almost anything, powered by extensible skills. The fork is named after the Edgerunners character; the rebrand reflects that this codebase has diverged enough from upstream to warrant its own identity.

## What's different from upstream

- **On-demand skill library**: in addition to the always-loaded `skills/` directory, Kiwi adds a `skill-library/` registry whose contents are *not* injected into the system prompt. The agent discovers them at runtime via a `skill_search` tool (`select:`, `+keyword`, or regex queries) and loads matched skills with `read_file`. Per-skill toggle in Settings; master switch in `config.yaml`. Borrowed from a Praetorian blog post on keeping context windows lean for specialized workflows.
- **Per-subagent skill allowlists**: subagents inherit a curated subset of the lead agent's skills with a fixed inheritance order; the broken inheritance from earlier work has been corrected.
- **Guardrails**: pluggable `GuardrailMiddleware` evaluates each tool call before execution, with a built-in `AllowlistProvider` plus support for OAP policy providers and custom providers.
- **MCP multi-provider OAuth**: HTTP/SSE MCP servers support `client_credentials` and `refresh_token` flows with automatic token refresh.
- **Kubernetes provisioner**: provisioner mode runs sandbox containers as Kubernetes pods, in addition to Docker.
- **Strict App↔Harness boundary**: a CI test ensures `packages/harness/kiwi/` never imports from `app/*`, so the harness package stays publishable independently.

The rest of the README documents how to set up and run the system. Most of it is unchanged from upstream — only the names and paths have moved.

## Table of Contents

- [Quick Start](#quick-start)
  - [Configuration](#configuration)
  - [Running the Application](#running-the-application)
  - [Startup Modes](#startup-modes)
- [Advanced](#advanced)
  - [Sandbox Mode](#sandbox-mode)
  - [MCP Server](#mcp-server)
  - [IM Channels](#im-channels)
  - [Tracing](#tracing)
- [Core Features](#core-features)
- [Embedded Python Client](#embedded-python-client)
- [Documentation](#documentation)
- [Security Notice](#security-notice)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Quick Start

### Configuration

1. **Clone the repository**

   ```bash
   git clone <your-fork-url>
   cd kiwi-flow
   ```

2. **Run the setup wizard**

   From the project root directory (`kiwi-flow/`), run:

   ```bash
   make setup
   ```

   This launches an interactive wizard that guides you through choosing an LLM provider, optional web search, and execution/safety preferences such as sandbox mode, bash access, and file-write tools. It generates a minimal `config.yaml` and writes your keys to `.env`. Takes about 2 minutes.

   Run `make doctor` at any time to verify your setup and get actionable fix hints.

   > **Advanced / manual configuration**: If you prefer to edit `config.yaml` directly, run `make config` instead to copy the full template. See `config.example.yaml` for the complete reference including CLI-backed providers (Codex CLI, Claude Code OAuth), OpenRouter, Responses API, and more.

   <details>
   <summary>Manual model configuration examples</summary>

   ```yaml
   models:
     - name: gpt-4o
       display_name: GPT-4o
       use: langchain_openai:ChatOpenAI
       model: gpt-4o
       api_key: $OPENAI_API_KEY

     - name: openrouter-gemini-2.5-flash
       display_name: Gemini 2.5 Flash (OpenRouter)
       use: langchain_openai:ChatOpenAI
       model: google/gemini-2.5-flash-preview
       api_key: $OPENROUTER_API_KEY
       base_url: https://openrouter.ai/api/v1

     - name: gpt-5-responses
       display_name: GPT-5 (Responses API)
       use: langchain_openai:ChatOpenAI
       model: gpt-5
       api_key: $OPENAI_API_KEY
       use_responses_api: true
       output_version: responses/v1

     - name: qwen3-32b-vllm
       display_name: Qwen3 32B (vLLM)
       use: kiwi.models.vllm_provider:VllmChatModel
       model: Qwen/Qwen3-32B
       api_key: $VLLM_API_KEY
       base_url: http://localhost:8000/v1
       supports_thinking: true
       when_thinking_enabled:
         extra_body:
           chat_template_kwargs:
             enable_thinking: true
   ```

   For vLLM 0.19.0, use `kiwi.models.vllm_provider:VllmChatModel`. For Qwen-style reasoning models, Kiwi toggles reasoning with `extra_body.chat_template_kwargs.enable_thinking` and preserves vLLM's non-standard `reasoning` field across multi-turn tool-call conversations. Legacy `thinking` configs are normalized automatically.

   CLI-backed provider examples:

   ```yaml
   models:
     - name: gpt-5.4
       display_name: GPT-5.4 (Codex CLI)
       use: kiwi.models.openai_codex_provider:CodexChatModel
       model: gpt-5.4
       supports_thinking: true
       supports_reasoning_effort: true

     - name: claude-sonnet-4.6
       display_name: Claude Sonnet 4.6 (Claude Code OAuth)
       use: kiwi.models.claude_provider:ClaudeChatModel
       model: claude-sonnet-4-6
       max_tokens: 4096
       supports_thinking: true
   ```

   - Codex CLI reads `~/.codex/auth.json`
   - Claude Code accepts `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_CREDENTIALS_PATH`, or `~/.claude/.credentials.json`
   - On macOS, export Claude Code auth explicitly if needed:

   ```bash
   eval "$(python3 scripts/export_claude_code_oauth.py --print-export)"
   ```

   API keys can also be set manually in `.env` (recommended) or exported in your shell:

   ```bash
   OPENAI_API_KEY=your-openai-api-key
   TAVILY_API_KEY=your-tavily-api-key
   ```

   </details>

### Running the Application

#### Deployment Sizing

| Deployment target | Starting point | Recommended | Notes |
|---|---|---|---|
| Local evaluation / `make dev` | 4 vCPU, 8 GB RAM, 20 GB free SSD | 8 vCPU, 16 GB RAM | Good for one developer or one light session with hosted model APIs. |
| Docker development / `make docker-start` | 4 vCPU, 8 GB RAM, 25 GB free SSD | 8 vCPU, 16 GB RAM | Image builds, bind mounts, and sandbox containers need more headroom. |
| Long-running server / `make up` | 8 vCPU, 16 GB RAM, 40 GB free SSD | 16 vCPU, 32 GB RAM | Preferred for shared use, multi-agent runs, or heavier sandbox workloads. |

These numbers cover Kiwi itself. If you also host a local LLM, size that service separately. Linux + Docker is the recommended deployment target for a persistent server.

#### Option 1: Docker (Recommended)

**Development** (hot-reload, source mounts):

```bash
make docker-init    # Pull sandbox image (only once or when image updates)
make docker-start   # Start services (auto-detects sandbox mode from config.yaml)
```

`make docker-start` starts `provisioner` only when `config.yaml` uses provisioner mode (`sandbox.use: kiwi.community.aio_sandbox:AioSandboxProvider` with `provisioner_url`).

> [!TIP]
> On Linux, if Docker-based commands fail with `permission denied while trying to connect to the Docker daemon socket`, add your user to the `docker` group and re-login. See [CONTRIBUTING.md](CONTRIBUTING.md#linux-docker-daemon-permission-denied) for the full fix.

**Production** (builds images locally, mounts runtime config and data):

```bash
make up     # Build images and start all production services
make down   # Stop and remove containers
```

Access: http://localhost:2026

#### Option 2: Local Development

Prerequisite: complete the "Configuration" steps above first (`make setup`). `make dev` requires a valid `config.yaml` in the project root (overridable via `KIWI_FLOW_CONFIG_PATH`). On Windows, run from Git Bash.

```bash
make check      # Verify Node.js 22+, pnpm, uv, nginx
make install    # Install backend + frontend dependencies
make dev        # Start all services
```

Access: http://localhost:2026

### Startup Modes

Two dimensions: **Dev / Prod** (hot-reload vs pre-built frontend) and **Standard / Gateway** (separate LangGraph server vs agent runtime embedded in the Gateway API).

| | **Local Foreground** | **Local Daemon** | **Docker Dev** | **Docker Prod** |
|---|---|---|---|---|
| **Dev** | `make dev` | `make dev-daemon` | `make docker-start` | — |
| **Dev + Gateway** | `make dev-pro` | `make dev-daemon-pro` | `make docker-start-pro` | — |
| **Prod** | `make start` | `make start-daemon` | — | `make up` |
| **Prod + Gateway** | `make start-pro` | `make start-daemon-pro` | — | `make up-pro` |

| Action | Local | Docker Dev | Docker Prod |
|---|---|---|---|
| **Stop** | `make stop` | `make docker-stop` | `make down` |

> **Gateway mode** eliminates the LangGraph server process — the Gateway API handles agent execution directly via async tasks. Lower resource use, no LangGraph Platform license required. Both modes are functionally equivalent.

## Advanced

### Sandbox Mode

Three execution modes:
- **Local Execution** — sandbox code runs directly on the host machine
- **Docker Execution** — sandbox code runs in isolated Docker containers
- **Docker Execution with Kubernetes** — sandbox code runs in Kubernetes pods via the provisioner service

For Docker development, service startup follows `config.yaml` sandbox mode. See the [Sandbox Configuration Guide](backend/docs/CONFIGURATION.md#sandbox).

### MCP Server

Configurable MCP servers extend Kiwi's capabilities. HTTP/SSE servers support OAuth token flows (`client_credentials`, `refresh_token`) with automatic token refresh. See the [MCP Server Guide](backend/docs/MCP_SERVER.md).

### IM Channels

Kiwi can receive tasks from Telegram, Slack, Feishu/Lark, WeChat, and WeCom. Channels auto-start when configured — no public IP required.

| Channel | Transport | Difficulty |
|---------|-----------|------------|
| Telegram | Bot API (long-polling) | Easy |
| Slack | Socket Mode | Moderate |
| Feishu / Lark | WebSocket | Moderate |
| WeChat | Tencent iLink (long-polling) | Moderate |
| WeCom | WebSocket | Moderate |

Configure in `config.yaml`:

```yaml
channels:
  langgraph_url: http://localhost:2024
  gateway_url: http://localhost:8001

  feishu:
    enabled: true
    app_id: $FEISHU_APP_ID
    app_secret: $FEISHU_APP_SECRET

  slack:
    enabled: true
    bot_token: $SLACK_BOT_TOKEN
    app_token: $SLACK_APP_TOKEN
    allowed_users: []

  telegram:
    enabled: true
    bot_token: $TELEGRAM_BOT_TOKEN
    allowed_users: []

  wecom:
    enabled: true
    bot_id: $WECOM_BOT_ID
    bot_secret: $WECOM_BOT_SECRET

  wechat:
    enabled: false
    bot_token: $WECHAT_BOT_TOKEN
    ilink_bot_id: $WECHAT_ILINK_BOT_ID
    qrcode_login_enabled: true
    state_dir: ./.kiwi-flow/wechat/state
```

When running under Docker Compose, IM channels execute inside the `gateway` container — point `channels.langgraph_url` and `channels.gateway_url` at container service names (`http://langgraph:2024`, `http://gateway:8001`) or set `KIWI_FLOW_CHANNELS_LANGGRAPH_URL` / `KIWI_FLOW_CHANNELS_GATEWAY_URL`.

**Channel commands** (chat-side):

| Command | Description |
|---------|-------------|
| `/new` | Start a new conversation |
| `/status` | Show current thread info |
| `/models` | List available models |
| `/memory` | View memory |
| `/help` | Show help |

Setup details for each platform live in the upstream README — links inside the platform-specific docs apply unchanged.

### Tracing

Both LangSmith and Langfuse are supported. Enable either (or both) in `.env`:

```bash
# LangSmith
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=lsv2_pt_xxxxxxxxxxxxxxxx
LANGSMITH_PROJECT=xxx

# Langfuse
LANGFUSE_TRACING=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

If both providers are enabled, Kiwi attaches both tracing callbacks. If a provider is enabled with missing credentials, Kiwi fails fast at model creation and names the offending provider.

For Docker deployments, tracing is disabled by default. Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in your `.env` to enable.

## Core Features

### Skills & Tools

Skills are structured Markdown capability modules — workflows, best practices, and references to supporting resources. Built-ins ship for research, report generation, slide creation, web pages, and image/video generation; add your own under `skills/custom/` (or install `.skill` archives via the Gateway).

For specialized workflows that should *not* pay per-turn token cost, drop SKILL.md files under `skill-library/` instead. The agent discovers them at runtime via `skill_search` (see "What's different from upstream" above).

```
# Paths inside the sandbox container
/mnt/skills/public           ← always-loaded built-ins
├── research/SKILL.md
├── report-generation/SKILL.md
└── ...

/mnt/skills/custom           ← always-loaded user skills
└── your-custom-skill/SKILL.md

/mnt/skill-library           ← on-demand, discovered via skill_search
└── specialized/SKILL.md
```

#### Claude Code Integration

The `claude-to-kiwi` skill lets you interact with a running Kiwi instance directly from [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Send tasks, check status, manage threads — all from the terminal.

Make sure Kiwi is running (default at `http://localhost:2026`), then use the `claude-to-kiwi` skill in Claude Code.

Optional environment variables for custom endpoints:

```bash
KIWI_URL=http://localhost:2026            # Unified proxy base URL
KIWI_GATEWAY_URL=http://localhost:2026    # Gateway API
KIWI_LANGGRAPH_URL=http://localhost:2026/api/langgraph  # LangGraph API
```

See [`skills/public/claude-to-kiwi/SKILL.md`](skills/public/claude-to-kiwi/SKILL.md) for the full API reference.

### Sub-Agents

The lead agent can spawn sub-agents on the fly — each with its own scoped context, tools, and termination conditions. Sub-agents run in parallel when possible and report structured results back. `MAX_CONCURRENT_SUBAGENTS = 3` enforced via middleware, 15-minute timeout.

### Sandbox & File System

Each task gets its own execution environment: a full filesystem view (skills, workspace, uploads, outputs) plus the ability to read, write, edit files, view images, and (when configured safely) execute shell commands.

`AioSandboxProvider` runs commands inside isolated containers. `LocalSandboxProvider` maps file tools to per-thread directories on the host but disables host `bash` by default — re-enable only for fully trusted local workflows.

```
/mnt/user-data/
├── uploads/      ← user uploads
├── workspace/    ← agent working dir
└── outputs/      ← final deliverables
```

### Context Engineering

- **Isolated sub-agent context**: each sub-agent runs in its own context — no leakage from the main agent or sibling sub-agents.
- **Summarization**: aggressive in-session compression of completed sub-tasks, with intermediate results offloaded to the filesystem.
- **Strict tool-call recovery**: when a provider or middleware interrupts a tool-call loop, Kiwi strips raw tool-call metadata on forced-stop assistant messages and injects placeholder tool results for dangling calls before the next model invocation, keeping strict OpenAI-compatible reasoning models from failing on malformed history.

### Long-Term Memory

Kiwi builds a persistent memory of your profile, preferences, and accumulated knowledge across sessions. Stored locally; under your control. Memory updates skip duplicate facts at apply time so repeated context does not accumulate.

## Embedded Python Client

Kiwi can be used as an embedded Python library without running the full HTTP services. `KiwiClient` provides direct in-process access to all agent and Gateway capabilities, returning the same response schemas as the HTTP Gateway API:

```python
from kiwi.client import KiwiClient

client = KiwiClient()

# Chat
response = client.chat("Analyze this paper for me", thread_id="my-thread")

# Streaming
for event in client.stream("hello"):
    if event.type == "messages-tuple" and event.data.get("type") == "ai":
        print(event.data["content"])

# Configuration & management — returns Gateway-aligned dicts
models = client.list_models()
skills = client.list_skills()
client.update_skill("web-search", enabled=True)
client.upload_files("thread-1", ["./report.pdf"])
```

All dict-returning methods are validated against Gateway Pydantic response models in CI (`TestGatewayConformance`). See `backend/packages/harness/kiwi/client.py` for full API documentation.

## Documentation

- [Contributing Guide](CONTRIBUTING.md) — development environment setup and workflow
- [Configuration Guide](backend/docs/CONFIGURATION.md) — setup and configuration reference
- [Architecture Overview](backend/CLAUDE.md) — technical architecture details
- [Backend Architecture](backend/README.md) — backend architecture and API reference

## Security Notice

Kiwi has high-privilege capabilities including system command execution and resource operations, and is designed by default to be **deployed in a local trusted environment (accessible only via the 127.0.0.1 loopback interface)**. Deploying on LAN networks, public cloud servers, or other multi-endpoint environments without strict security measures may introduce serious risks.

If cross-device or cross-network deployment is required, implement strict security measures: IP allowlists (iptables, hardware ACLs), authentication gateways (e.g. nginx with strong pre-auth), network isolation (place trusted devices in a dedicated VLAN). Stay current with upstream security updates.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, workflow, and guidelines. Regression coverage includes Docker sandbox mode detection and provisioner kubeconfig-path handling tests in `backend/tests/`.

## License

Kiwi inherits the [MIT License](./LICENSE) from the upstream DeerFlow project.

## Acknowledgments

Kiwi stands on the shoulders of giants — most directly the original DeerFlow project and its authors:

- **[Daniel Walnut](https://github.com/hetaoBackend/)**
- **[Henry Li](https://github.com/magiccube/)**

And the open-source frameworks that make this possible:

- **[LangChain](https://github.com/langchain-ai/langchain)** — LLM interactions and chains
- **[LangGraph](https://github.com/langchain-ai/langgraph)** — multi-agent orchestration
- **[Next.js](https://nextjs.org/)** — web app framework
