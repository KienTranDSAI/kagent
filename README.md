# kagent

[![CI](https://github.com/KienTranDSAI/kagent/actions/workflows/ci.yml/badge.svg)](https://github.com/KienTranDSAI/kagent/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/kagent-ai)](https://pypi.org/project/kagent-ai/)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A terminal-based AI coding agent that works with multiple LLM providers — Gemini, OpenAI, and any OpenAI-compatible endpoint. Point it at a codebase, describe what you want, and it reads files, edits code, and runs commands to get there.

<!-- TODO: demo GIF — record with `vhs` or `asciinema` -->

## Features

- **Agentic loop** — the model reads files, edits code, runs shell commands, and iterates until the task is done
- **Provider-agnostic** — Gemini (native) or any OpenAI-compatible API (OpenAI, vLLM, sglang, Ollama, Qwen, ...)
- **Solid tool set** — file read/write, string-replacement edits, glob, grep, bash, sub-agents, todo tracking
- **Permission modes** — interactive approval by default; plan (read-only), accept-edits, and full-auto modes
- **Streaming output** — responses render live in a rich terminal UI
- **Sessions** — every conversation is saved and can be resumed
- **Project memory** — per-project `CLAUDE.md` context plus persistent user-level memory
- **Context compaction** — 3-tier strategy (micro-compaction → tool-result collapse → LLM summary) to stay within context limits
- **Multimodal** — reads images, PDFs (with page ranges), and Jupyter notebooks
- **Cost tracking** — token usage and cost per session
- **Setup wizard** — `kagent init` configures provider, model, and API key interactively

## Installation

```bash
uv tool install kagent-ai
# or
pipx install kagent-ai
```

From source:

```bash
git clone https://github.com/KienTranDSAI/kagent.git
cd kagent
uv tool install --editable .
```

## Quick start

```bash
kagent init   # one-time setup: pick provider, model, API key
kagent        # start the agent in your project directory
```

## Configuration

`kagent init` writes `~/.kagent/.env` (permissions 0600). You can also create it by hand:

```env
LLM_PROVIDER=gemini            # gemini | openai
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=...

# OpenAI or any OpenAI-compatible endpoint (vLLM, sglang, Ollama, ...)
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-4o
# OPENAI_API_KEY=...
# OPENAI_BASE_URL=https://...  # only for compatible endpoints
```

Environment precedence (highest first):

1. Real shell environment variables
2. `./.env` in the current directory
3. `~/.kagent/.env`

## Usage

```bash
kagent                    # default — asks before file writes and shell commands
kagent --plan             # plan mode: read-only exploration
kagent --accept-edits     # auto-approve edits, still ask for shell commands
kagent --auto             # approve everything (use with care)
kagent --resume <id>      # resume a saved session
```

### Slash commands

| Command | Description |
|---------|-------------|
| `/help` | List available commands |
| `/mode <name>` | Switch permission mode |
| `/plan` | Enter plan mode |
| `/todo` | Show the todo list |
| `/git` | Git helpers (diff, commit, review) |
| `/memory` | Edit project memory |

### File locations

| Path | Purpose |
|------|---------|
| `~/.kagent/.env` | API keys, provider/model defaults |
| `~/.kagent/sessions/` | Saved conversations (JSON per session) |
| `~/.kagent/memory/` | Persistent memory injected into the system prompt |
| `<project>/CLAUDE.md` | Per-project context, committed with the repo |

## How it works

kagent runs a single agentic loop: your prompt goes to the LLM, the response streams back, tool calls are dispatched through a registry with JSON-Schema validation, results are appended to the conversation, and the loop repeats until the model finishes. A permission checker gates every side effect (file writes, shell commands) according to the active mode, and a context manager compacts older history in three tiers so long sessions don't blow the context window. Edits use exact string replacement rather than line numbers, which makes them robust against stale line offsets.

The architecture is inspired by Claude Code.

## Development

```bash
git clone https://github.com/KienTranDSAI/kagent.git
cd kagent
uv venv && uv pip install -e '.[dev]'

pytest            # run tests
ruff check .      # lint
```

## Roadmap

- Native Anthropic (Claude) provider — today Claude models are reachable via Anthropic's OpenAI-compatible endpoint (`LLM_PROVIDER=openai`, `OPENAI_BASE_URL=https://api.anthropic.com/v1/`)
- MCP (Model Context Protocol) tool support

## License

[MIT](LICENSE)
