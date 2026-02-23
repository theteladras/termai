# termai

A local AI-powered terminal assistant that converts natural language into shell commands — safely.

## Features

- **Safe command generation** — preview every command before it runs, with color-coded safety warnings for destructive operations
- **Context-aware** — knows your OS, shell, cwd, git branch, package manager, and recent commands
- **Interactive chat mode** — multi-turn conversation in your terminal with `/help`, `/history`, `/context`, `/clear`
- **Offline operation** — uses a local LLM (GPT4All: Phi-3, Mistral, LLaMA) with automatic fallback
- **Standalone executable** — single-file binary for macOS, Linux, and Windows (no Python required)
- **Interactive model setup** — pick from curated models on first run
- **Command logging** — full audit trail in `~/.termai/history.jsonl`
- **Plugin system** — extend with custom slash commands and execution hooks
- **Configurable** — TOML config file, CLI flags, and environment variables

## Quick Start

### Option 1: Download the executable (recommended)

Download the latest binary from [Releases](../../releases) for your platform — no Python needed.

```bash
# macOS / Linux
chmod +x termai
./termai --install     # full wizard: installs binary, picks a model, configures
```

The installation wizard will:
1. Copy `termai` to `/usr/local/bin` (with sudo if needed)
2. Create the `tai` shortcut alias
3. Let you pick and download an AI model
4. Set up the config file

After that, just use `termai` or `tai` from anywhere.

### Option 2: Install from source

```bash
pip install -e .
termai --install       # run the wizard
```

## Usage

```
termai --install                   # full installation wizard
termai "your instruction"          # generate & preview a command
termai -y "your instruction"       # skip confirmation, execute immediately
termai --dry-run "instruction"     # preview only
termai --chat                      # interactive mode
termai --history                   # show recent history
termai --history 50                # show last 50 commands
termai --setup                     # pick and download an AI model
termai --list-models               # show available models
termai --model Mistral-7B-...      # use a specific model
termai --device gpu                # run model on GPU
termai --init-config               # create ~/.termai/config.toml
```

`tai` works as a short alias for `termai`:

```bash
tai -y "show disk usage"
tai --chat
```

## Model Setup

On first run, termai uses a rule-based fallback that works instantly with no downloads. For full AI-powered generation, run the interactive model selector:

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

Models are downloaded once and stored in `~/.cache/gpt4all/`.

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
Execute this command? [y/N] y

ai> /help
ai> /history
ai> /context
ai> exit
```

## Configuration

Create a config file with `termai --init-config`, or manually at `~/.termai/config.toml`:

```toml
[termai]
model = "Phi-3-mini-4k-instruct.Q4_0.gguf"
device = "cpu"
max_tokens = 256
temperature = 0.2
```

Environment variables override config: `TERMAI_MODEL`, `TERMAI_DEVICE`, `TERMAI_MAX_TOKENS`, `TERMAI_PLUGIN_DIR`.

## Building Standalone Executables

```bash
pip install -e ".[dev]"

# Standard build (~15-30 MB)
python build.py

# Fat build with bundled model (~2+ GB, fully offline)
python build.py --bundle-model

# Output: dist/termai (or dist/termai.exe on Windows)
```

Builds are also automated via GitHub Actions — push a `v*` tag to create a release with binaries for all platforms.

### Testing the executable locally

If you have termai installed via pip and want to switch to the standalone executable:

```bash
# 1. Uninstall the pip version
pip uninstall termai -y

# 2. Build the executable
python build.py --clean

# 3. Test it
./dist/termai --version
./dist/termai --setup
./dist/termai -y "list files"

# 4. (Optional) Copy to PATH for global access
sudo cp dist/termai /usr/local/bin/termai
sudo cp dist/termai /usr/local/bin/tai
```

To go back to the development version:

```bash
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
        # return modified command or None
        return None
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
├── installer.py     # Full installation wizard
├── generator.py     # Natural language → shell command
├── executor.py      # Command preview, safety checks, execution
├── safety.py        # Destructive command detection & warnings
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
