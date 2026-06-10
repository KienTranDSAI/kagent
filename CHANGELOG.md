# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-10

### Added

- Agentic loop with streaming tool use: file read/write, string-replacement edits, glob, grep, bash, sub-agents, todo tracking
- Providers: Gemini (native) and OpenAI / OpenAI-compatible endpoints
- Permission modes: default (interactive approval), plan (read-only), accept-edits, auto
- Session persistence and `--resume`
- Per-project `CLAUDE.md` context and persistent user memory
- 3-tier context compaction (micro-compaction, tool-result collapse, LLM summary)
- Multimodal input: images, PDFs with page ranges, Jupyter notebooks
- Per-session token and cost tracking
- Interactive setup wizard (`kagent init`)
