<p align="center">
  <img src="assets/logo.png" alt="termai logo" width="450" />
</p>

# Termai

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A local AI-powered terminal assistant that converts natural language into shell commands — safely.

## Motivation

We spend too much time looking up commands we've forgotten, piecing together flags from man pages, and copy-pasting from Stack Overflow. Meanwhile, cloud-based AI assistants require sending your terminal context to a remote server — your working directory, environment variables, running processes — all shipped off to someone else's infrastructure.

**termai** exists because:

- **Your terminal is yours.** Everything runs locally. No API keys, no cloud, no telemetry. Your commands, your context, your machine.
- **Commands should be safe by default.** Every generated command is previewed before execution. Destructive operations are flagged with clear warnings. You stay in control.
- **Setup shouldn't be a project.** Download one file, double-click or run it, pick a model, done. No Python, no pip, no dependency hell.
- **AI should earn your trust.** The smart allow-list system lets harmless commands run instantly while requiring confirmation for anything risky. Over time, you teach it what you're comfortable with.

## Features

- **Safe command generation** — preview every command before it runs, with color-coded safety warnings for destructive operations
- **Smart auto-execution** — harmless commands (`ls`, `pwd`, `git status`, etc.) run without prompting; risky ones always ask
- **Allow list** — approve commands once, per-session, or permanently; manage via GUI or terminal
- **Context-aware** — knows your OS, shell, cwd, git branch, package manager, and recent commands
- **Interactive chat mode** — multi-turn conversation in your terminal with `/help`, `/history`, `/context`, `/clear`
- **AI orchestrator** — complex multi-step requests are decomposed into a dependency-aware execution plan with parallel waves
- **Hybrid AI** — local LLM handles simple tasks instantly; complex tasks are delegated to OpenAI or Claude when configured
- **Parallel execution** — independent commands run simultaneously for faster results
- **Process history** — full lifecycle tracking per task (prompt, AI provider, steps, timing, status) in GUI and terminal
- **Offline-first** — works fully offline with a local LLM (GPT4All: Phi-3, Mistral, LLaMA); remote AI is always optional
- **Standalone executable** — single-file binary for macOS, Linux, and Windows (no Python required)
- **Browser-based GUI** — setup wizard and settings dashboard that opens in your browser, zero dependencies
- **Command logging** — full audit trail in `~/.termai/history.jsonl`
- **Plugin system** — extend with custom slash commands and execution hooks
- **Configurable** — TOML config file, CLI flags, environment variables, and GUI settings

## Quick Start

### Option 1: Download the executable (recommended)

Download the latest binary from [Releases](../../releases) for your platform — no Python needed.

```bash
# macOS / Linux
chmod +x termai
./termai              # opens the GUI setup wizard in your browser
```

Double-clicking the executable also opens the wizard. It will:
1. Install `termai` and `tai` to your PATH
2. Let you pick and download an AI model
3. Set up the config file

After that, just use `termai` or `tai` from anywhere.

### Option 2: Build from source

```bash
pip install -e ".[dev]"
python build.py --clean
```

The executable is output to `dist/termai` (or `dist/termai.exe` on Windows). From there:

```bash
./dist/termai              # opens the GUI setup wizard in your browser
./dist/termai --install    # terminal-based wizard (no browser)
```

## Usage

```
termai "your instruction"          # generate & preview a command
termai -y "your instruction"       # skip confirmation, execute immediately
termai --dry-run "instruction"     # preview only, don't execute
termai --chat                      # interactive chat mode
termai --history                   # show recent command history
termai --history 50                # show last 50 commands
termai --processes                 # show multi-step process history
termai --processes 10              # show last 10 processes
```

### Setup & Configuration

```
termai --settings                  # settings dashboard (models, allow list, config)
termai --install                   # terminal-based setup wizard
termai --setup                     # terminal model selector
termai --list-models               # show available models
termai --model Mistral-7B-...      # use a specific model for this run
termai --device gpu                # run model on GPU
termai --init-config               # create default config file
termai --uninstall                 # remove binaries, config, and models
termai --remote                    # force remote AI for this run
termai --local                     # force local-only AI for this run
termai --provider openai           # override remote provider for this run
```

`tai` works as a short alias for `termai`:

```bash
tai -y "show disk usage"
tai --chat
tai --settings
```

## Smart Command Execution

termai uses a three-tier trust system to decide when to ask for confirmation:

| Tier | Behavior | Example |
|---|---|---|
| **Built-in safe** | Auto-executes immediately | `ls`, `pwd`, `git status`, `df -h` |
| **User allow list** | Auto-executes (you approved it) | `npm install`, `docker build` |
| **Everything else** | Asks before running | `rm`, `chmod`, `pip install` |

When prompted, you get four options:

```
  y execute        a always allow   s session allow   n cancel

  Run? [y/a/s/N]
```

- **y** — run once, ask again next time
- **a** — run and add to your permanent allow list
- **s** — run and allow for this terminal session
- **n** — cancel

Critical commands (`rm -rf /`, `mkfs`, `dd`) always require typing "execute" regardless of allow lists.

Manage allow lists and built-in safe commands via the settings dashboard:

```bash
termai --settings     # opens in your browser
```

## AI Orchestrator

When an instruction requires multiple steps, termai automatically detects this and uses the AI to create a structured execution plan:

```
tai "create a python project called api-service, set up a venv, install flask and pytest, init git"
```

The orchestrator will:

1. **Decompose** the request into atomic shell commands
2. **Identify dependencies** between steps (which must wait for others)
3. **Group independent steps** into parallel execution waves
4. **Execute** wave by wave with real-time feedback

```
  ╭─ Execution Plan ─────────────────────────────
  │  "create a python project, set up venv, install flask and pytest, init git"
  │  5 steps • 3 waves • remote/OpenAIProvider
  ├────────────────────────────────────────────────
  │  Wave 1
  │    1. mkdir api-service
  │  Wave 2 (parallel)
  │    2. cd api-service && python3 -m venv venv
  │    3. cd api-service && git init
  │  Wave 3 (parallel)
  │    4. cd api-service && venv/bin/pip install flask
  │    5. cd api-service && venv/bin/pip install pytest
  ╰────────────────────────────────────────────────

  Execute plan? [y/N] y

  ▸ Wave 1/3
    ✓ 1. mkdir api-service (50ms)

  ▸ Wave 2/3 (parallel)
    ✓ 2. python3 -m venv venv (3.2s)
    ✓ 3. git init (80ms)

  ▸ Wave 3/3 (parallel)
    ✓ 4. pip install flask (5.1s)
    ✓ 5. pip install pytest (4.8s)

  ════════════════════════════════════════════════
  Plan completed: 5/5 steps succeeded (13.3s)
  ════════════════════════════════════════════════
```

Every process is logged with full details. View past processes via:

```bash
termai --processes       # terminal view
termai --settings        # GUI Processes tab
```

In chat mode, use `/processes` to view recent process history.

## GUI

termai includes a browser-based GUI with zero dependencies — no Tkinter, no Electron, just Python's built-in HTTP server opening a page in your default browser.

- **Setup wizard** — first-run experience with model selection and download progress
- **Settings dashboard** — six tabs:
  - **Models** — switch active model, download new ones, see which are installed
  - **Remote AI** — configure OpenAI/Claude API keys, select remote model, test connection
  - **Allow List** — view/add/remove custom allowed commands, toggle built-in safe commands on/off
  - **History** — browse, filter, and clear your prompt history
  - **Processes** — view multi-step orchestrated tasks with step details, timing, and AI info
  - **Config** — view current settings

The GUI auto-launches when running the standalone executable with no arguments (or double-clicking it). From the terminal:

```bash
termai                # opens the setup wizard (default when no args)
termai --settings     # go straight to the settings dashboard
```

## Remote AI (Optional)

termai works fully offline by default. Optionally, connect OpenAI or Claude for complex tasks — the local model handles simple commands instantly, and only delegates when needed.

### Setup

Configure via the settings dashboard or manually in `~/.termai/config.toml`:

```toml
[remote]
provider = "openai"          # "openai" or "claude"
model = "gpt-4o-mini"        # see model options below
openai_api_key = "sk-..."
```

Or set environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export TERMAI_REMOTE_PROVIDER="openai"
# or
export ANTHROPIC_API_KEY="sk-ant-..."
export TERMAI_REMOTE_PROVIDER="claude"
```

### How Delegation Works

1. Local model generates a command first (instant, free, private)
2. A complexity classifier evaluates the instruction
3. Simple tasks (list files, check status) use the local result
4. Complex tasks (multi-step scripts, Kubernetes, Terraform) are delegated to the remote provider
5. If the remote provider fails, the local result is used as fallback with a warning

### Available Remote Models

| Provider | Model | Description |
|---|---|---|
| OpenAI | `gpt-4o-mini` | Fast and affordable (default) |
| OpenAI | `gpt-4o` | Most capable |
| OpenAI | `gpt-4.1-mini` | Latest mini model |
| OpenAI | `gpt-4.1` | Latest flagship |
| Claude | `claude-sonnet-4-20250514` | Balanced speed and quality (default) |
| Claude | `claude-haiku-3-5-20241022` | Fast and affordable |
| Claude | `claude-opus-4-20250514` | Most capable |

### CLI Overrides

```bash
termai --remote "complex task"       # force remote AI for this instruction
termai --local "simple task"         # force local-only, ignore remote config
termai --provider claude "task"      # use Claude instead of configured provider
```

Install the optional dependencies to use remote AI:

```bash
pip install -e ".[remote]"           # installs openai + anthropic SDKs
```

## Model Setup

On first run, termai uses a rule-based fallback that works instantly with no downloads. For full AI-powered generation, pick a model during setup or run:

```
$ termai --setup

  Available models:

  #    Name                     Size       Params   RAM      Quality
  ──── ──────────────────────── ────────── ──────── ──────── ────────
  1    Phi-3 Mini               2.2 GB     3.8B     8 GB     Good
  2    Orca Mini 3B             2.0 GB     3B       8 GB     Basic
  3    Mistral 7B Instruct      4.1 GB     7B       8 GB     Better
  4    LLaMA 3 8B Instruct      4.7 GB     8B       16 GB    Best

  Select a model [1-4, 0 to skip]:
```

Models are downloaded once and stored in `~/.cache/gpt4all/`. Switch models anytime via `termai --settings`.

## Interactive Chat

```
$ termai --chat
══════════════════════════════════════════════════
  termai — interactive chat mode
══════════════════════════════════════════════════

ai> find all log files older than 7 days
  ┌─ Command Preview ─────────────────────
  │  find . -name "*.log" -mtime +7
  └───────────────────────────────────────
  (auto-approved)

  Running…

ai> /help
ai> /history
ai> /context
ai> exit
```

Safe commands auto-execute in chat mode too — no confirmation needed for `ls`, `git status`, etc.

## Configuration

Config file at `~/.termai/config.toml` (create with `termai --init-config`):

```toml
[termai]
model = "Phi-3-mini-4k-instruct.Q4_0.gguf"
device = "cpu"
max_tokens = 256
temperature = 0.2
```

Environment variables override config: `TERMAI_MODEL`, `TERMAI_DEVICE`, `TERMAI_MAX_TOKENS`, `TERMAI_PLUGIN_DIR`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TERMAI_REMOTE_PROVIDER`.

Additional data files in `~/.termai/`:

| File | Purpose |
|---|---|
| `config.toml` | Main configuration |
| `allowed.json` | Permanently allowed commands |
| `disabled_builtins.json` | Built-in safe commands you've disabled |
| `history.jsonl` | Command execution audit log |
| `plugins/` | Custom plugin directory |

## Building Standalone Executables

```bash
pip install -e ".[dev]"

# Standard build (~15 MB, includes gpt4all runtime)
python build.py

# Clean rebuild
python build.py --clean

# Fat build with bundled model (~2+ GB, fully offline)
python build.py --bundle-model

# Output: dist/termai (or dist/termai.exe on Windows)
```

The executable bundles the gpt4all native libraries so AI works out of the box — no Python or pip needed on the target machine.

Builds are also automated via GitHub Actions — push a `v*` tag to create a release with binaries for all platforms.

### Testing the executable locally

```bash
# 1. Uninstall the pip version (if installed)
pip uninstall termai -y

# 2. Build
python build.py --clean

# 3. Test
./dist/termai --version
./dist/termai                      # GUI wizard opens in browser
./dist/termai -y "list files"      # CLI still works with args

# 4. Go back to dev version
pip install -e .
```

## Plugins

Place Python files in `~/.termai/plugins/`. Each must define a `register(registry)` function:

```python
def register(registry):
    @registry.slash_command("/mycommand")
    def my_handler(args, ctx):
        print("Hello from my plugin!")

    @registry.pre_execute
    def before_run(command, ctx):
        return None  # return modified command or None
```

See `examples/plugin_example.py` for a full example.

## Project Structure

```
termai/
├── __init__.py      # Package metadata
├── __main__.py      # python -m termai support
├── cli.py           # Argument parsing and entry point
├── config.py        # TOML config and env var management
├── context.py       # Session context (OS, shell, cwd, git, env)
├── model.py         # Local LLM wrapper (GPT4All)
├── models.py        # Model catalog and interactive selector
├── installer.py     # Terminal-based installation wizard
├── gui.py           # Browser-based GUI (wizard + settings dashboard)
├── uninstaller.py   # Uninstall wizard
├── remote.py        # Remote AI providers (OpenAI, Claude)
├── classifier.py    # Complexity classifier for local vs remote delegation
├── generator.py     # Natural language → shell command (local + remote)
├── orchestrator.py  # Multi-step task decomposition, wave execution, plan logging
├── process_log.py   # Process-level history (prompt → plan → step results)
├── executor.py      # Command preview, safety checks, parallel execution
├── safety.py        # Destructive command detection & warnings
├── allowlist.py     # Three-tier command allow list management
├── chat.py          # Interactive chat REPL
├── logger.py        # Command history logging (JSONL)
└── plugins.py       # Plugin system (slash commands, hooks)
build.py             # PyInstaller build script
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repository and clone your fork
2. **Create a branch** for your feature or fix: `git checkout -b my-feature`
3. **Install dev dependencies**: `pip install -e ".[dev]"`
4. **Make your changes** — keep commits focused and descriptive
5. **Run the linter and tests** before submitting:
   ```bash
   ruff check termai/
   pytest
   ```
6. **Open a pull request** against `main` with a clear description of what you changed and why

### Guidelines

- Follow the existing code style (enforced by [Ruff](https://docs.astral.sh/ruff/))
- Keep PRs small and focused — one feature or fix per PR
- Add tests for new functionality when possible
- Update the README if you're adding user-facing features or changing CLI flags
- Don't commit secrets, API keys, or model files
- Be respectful and constructive in discussions

### Ideas for Contributions

- New fallback command mappings in `generator.py`
- Additional safety patterns in `safety.py`
- Plugins — share useful ones in `examples/`
- Support for new local model backends
- Improved context gathering (Docker, Kubernetes, cloud CLIs)
- Translations or documentation improvements

If you're unsure about an idea, open an issue first to discuss it.

## Roadmap

Planned features and improvements:

- **Web search integration** — optional web fetching to look up documentation, correct install commands, and current best practices before generating commands. Useful when the AI lacks knowledge about newer tools or needs to verify version-specific instructions. Will be privacy-respecting (only activates when explicitly triggered or when remote AI is already configured).
- File reading and analysis support
- Natural language cron job scheduling
- Command explanation mode (`tai --explain "awk '{print $2}'"`)
- Team-shared allow lists and config profiles

## License

MIT
