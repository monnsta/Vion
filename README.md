<div align="center">
	<img src="doc/assets/icon.png" alt="Vion Logo" width="120" height="120" />
	<h1>Vion</h1>
	<p><strong>An autonomous AI Discord entity that understands intent, executes sandboxed code, and reasons naturally.</strong></p>
	<a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg" alt="Python Version"></a>
	<a href="https://github.com/Rapptz/discord.py"><img src="https://img.shields.io/badge/discord.py-2.x-blueviolet.svg" alt="discord.py"></a>
	<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License"></a>
</div>

---

## Overview

**Vion** is an intelligent, multi-modal AI agent built to live directly inside your Discord server. Unlike conventional bots that rely on rigid prefixed commands or static slash triggers, Vion listens, reasons, and executes actions directly in Python within a secure sandbox environment.

Vion adapts to community dynamics over time using a persistence-layer memory architecture, autonomous "Free Will" activity loops, voice recording/synthesis features, and permission-aware administrative authority.

---

## Quickstart & Installation

### 1. Prerequisites

- Python 3.11 or higher
- `ffmpeg` (automatically managed on Termux; install via system package manager on Linux/macOS/Windows for voice features)

### 2. Installation Options

#### Option A: Direct Install via Pip (Recommended)

You can install Vion directly from GitHub into your environment:

```bash
pip install git+https://github.com/monnsta/Vion.git
```

This registers the global CLI command `vion` and defaults the operational workspace to `~/vion`.

#### Option B: Clone & Local Setup

If you prefer running from source or developing locally:

```bash
git clone https://github.com/monnsta/Vion.git
cd Vion
```

### 3. Environment Configuration

Create a `.env` file in your Vion root directory (`~/vion` for git-installed usage, or the repository root if running from source) with your API credentials:

```yaml
discord: "YOUR_DISCORD_BOT_TOKEN"
assemblyai: "YOUR_ASSEMBLYAI_KEY"
hmac: "YOUR_HMAC_SECRET"
gemini:
  - "PRIMARY_GEMINI_API_KEY"
  - "FALLBACK_GEMINI_API_KEY"
```

### 4. Running Vion

Vion automatically detects your platform, handles missing runtime dependencies, and sets up required storage directories on launch.

If installed via pip:

```bash
vion
```

If running from a cloned source tree:

```bash
python -m vion
```

---

## Key Features

### Intent-Driven Execution
- **No Command Syntax Required:** Ask Vion tasks in natural language, and it dynamically drafts and runs asynchronous Python code targeting Discord APIs.
- **Sandboxed Runtime:** Code execution is governed inside an isolated execution container with strict module whitelist constraints (`discord.py`, `asyncio`, `yt_dlp`, `httpx`, `matplotlib`, etc.).
- **Self-Calling & Recursive Processing:** Can re-evaluate complex multi-step workflows, analyze uploaded media files, or query full server/user JSON state snapshots on demand.

### Persistent Dual-Tier Memory System
- **Short-Term Memory (STM):** Tracks real-time active channel context, recent mentions, and conversation turns.
- **Long-Term Memory (LTM):** Persists auto-summarized and proactive observations across three scope levels:
  - **Global Scope:** Cross-server intelligence and core persona evolution.
  - **Guild Scope:** Server-specific events, ongoing drama, rules, and admin context.
  - **User Scope:** Personal user preferences, relationships, and history across servers.
- **Context Linker:** Temporarily links external guild or user contexts into active prompt streams.

### Advanced Voice Utilities
- **Voice Channel Interaction:** Join, leave, move, mute, and deafen server members.
- **Speech-to-Text & Transcription:** Record multi-user audio streams in voice channels and transcribe spoken dialogue.
- **Text-to-Speech Synthesis:** Generate high-fidelity audio streams using Gemini voices (e.g., `CHARON`, `AOEDE`, `ZEPHYR`, `PUCK`).
- **Media Playback:** Play audio sources or stream directly from YouTube URLs into active voice sessions.

### Autonomous "Free Will" Consciousness
- **Active Engagement:** Evaluates chat velocity and interjects naturally in active discussions without direct pings.
- **Inactivity Revitalization:** Detects stalled channels and initiates conversational topics.
- **Unsettling Memory & Typing Awareness:** Detects abandoned user typing states and responds proactively to delayed edits, deletes, or reaction events.
- **Offline Backfill:** Scans missed mentions, replies, and notifications upon startup to ensure continuity.

### Server-Specific Custom Cogs & Persistent Storage
- **Dynamic Extension Generation:** Generates, loads, unloads, and syncs custom server cogs (`GuildCog`) isolated strictly to individual server IDs.
- **Per-Guild JSON Storage:** Supports persistent data storage (`cog_data`) for custom warn systems, mini-games, and custom workflows.

### Built-in Security & Interactive UI
- **Permission Hierarchy:** Checks user permissions before executing privileged actions (e.g., bans, purges, role assignments).
- **Interactive Component Layouts:** Rich interactive cards, paged audit logs, form inputs, and confirmation dialogs built on top of `discord.ui`.
- **Entity Blacklisting:** Temporary or permanent moderation blacklisting for abusing users or servers.

---

## Technical Stack

- **Core Framework:** Python 3.11+, `discord.py`, `discord-ext-voice-recv`
- **LLM Engine:** Google Gemini API (`google-genai`)
- **Audio & Media:** PyNaCl, yt-dlp, AssemblyAI / Speech-to-Text integrations
- **Data & Formatting:** PyYAML, orjson, httpx, matplotlib, rich, pytz

---

## Philosophy

Traditional Discord bots process static strings against defined prefix commands. **Vion** shifts the paradigm from *command execution* to *intent synthesis*:

1. **Observe:** Receives Discord events (messages, voice updates, edits, deletes).
2. **Contextualize:** Injects short-term state, long-term memory, and server configurations into the system prompt.
3. **Execute:** Generates Python code targeting the `discord.py` API within a secure sandbox.
4. **Evolve:** Proactively updates memory logs and internal state to maintain long-term context across interactions.

---

## License

This project is licensed under the [MIT License](LICENSE).
