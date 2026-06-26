<div align="center">
	<img src="icon.png" alt="Vion Logo" width="120" height="120" />
	<h1>Vion: The Unrestricted AI Discord Agent</h1>
	<p><em>An advanced AI agent designed with robust modularity and sandbox execution capabilities, capable of doing *ANYTHING* within Discord.</em></p>
</div>

---

## Table of Contents
 1. [Getting Started](#getting-started)
 2. [Configuration](#configuration)
 3. [Project Architecture](#project-architecture)

---

## Getting Started
The application is designed to run robustly with built-in fail-safes. There are two primary methods for starting the bot depending on your environment (Production vs. Development).

### Production Environment (Recommended)
Execute the provided bash script. This acts as a lightweight process manager that automatically installs dependencies, manages background crashes, limits loop crashing, and provides system security.

```bash
./exec.sh
```

*(Use the --help flag to know all the options)*

### Development Environment
For testing or debugging, you can bypass the bash script and directly initialize the bot using Python.

```bash
python bot.py
```

---

## Configuration
The bot's identity, behavior, limits, and AI parameters are entirely driven by the config.ial file located in the project root. This ensures code logic remains abstracted from AI instructions and deployment configurations.
Make sure you copy .env.template into .env to input your API secrets (Discord, Gemini, AssemblyAI) before running the program for the first time.

---

## Project Architecture
The repository is highly modular, ensuring clear separation between core logic, UI generation, and runtime execution.

```
.
├── core/          # Core Application Logic
│   ├── cog/       # Discord commands and event extensions
│   ├── lib/       # Low-Level Utilities (Code Sandbox, File I/O, LLM Engine)
│   └── wrp/       # High-Level Wrappers (Profile, Memory, Blacklist)
├── meta/          # Configuration Setup & Path Mapping
├── data/          # Dynamic User and Server runtime memory & configs
├── logs/          # System runtime logs and rotating archives
├── bootstrap.py   # Initialization script (Logging, early setup)
├── bot.py         # Main application entry point
├── configure.ial  # Primary bot configuration and behavior settings
└── exec.sh        # Process manager script (Keeps bot alive)
```
