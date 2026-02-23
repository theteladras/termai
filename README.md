<p align="center">
  <img src="assets/logo.png" alt="termai logo" width="450" />
</p>

# Termai

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
- **Offline operation** — uses a local LLM (GPT4All: Phi-3, Mistral, LLaMA) with automatic fallback
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

### Option 2: Install from source

```bash
pip install -e .
termai --install       # terminal-based wizard
# or
termai --gui           # browser-based wizard
```

## Usage

```
termai "your instruction"          # generate & preview a command
termai -y "your instruction"       # skip confirmation, execute immediately
termai --dry-run "instruction"     # preview only, don't execute
termai --chat                      # interactive chat mode
termai --history                   # show recent command history
termai --history 50                # show last 50 commands
```

### Setup & Configuration

```
termai --gui                       # browser-based setup wizard
termai --settings                  # settings dashboard (models, allow list, config)
termai --install                   # terminal-based setup wizard
termai --setup                     # terminal model selector
termai --list-models               # show available models
termai --model Mistral-7B-...      # use a specific model for this run
termai --device gpu                # run model on GPU
termai --init-config               # create default config file
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

## GUI

termai includes a browser-based GUI with zero dependencies — no Tkinter, no Electron, just Python's built-in HTTP server opening a page in your default browser.

- **Setup wizard** — first-run experience with model selection and download progress
- **Settings dashboard** — four tabs:
  - **Models** — switch active model, download new ones, see which are installed
  - **Allow List** — view/add/remove custom allowed commands, toggle built-in safe commands on/off
  - **History** — browse, filter, and clear your prompt history
  - **Config** — view current settings

The GUI auto-launches when double-clicking the standalone executable. From the terminal:

```bash
termai --gui          # force the setup wizard
termai --settings     # go straight to settings
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

Environment variables override config: `TERMAI_MODEL`, `TERMAI_DEVICE`, `TERMAI_MAX_TOKENS`, `TERMAI_PLUGIN_DIR`.

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
├── generator.py     # Natural language → shell command
├── executor.py      # Command preview, safety checks, execution
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

## License

MIT
