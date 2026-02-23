"""Browser-based GUI for termai — wizard + settings dashboard.

Uses Python's built-in http.server + webbrowser — zero external
dependencies, works on every OS regardless of what's installed.

- First run (or ``--gui``): shows the installation wizard.
- Already set up (or ``--settings``): shows the settings dashboard
  with tabs for model management and the command allow list.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from termai.config import CONFIG_DIR, CONFIG_FILE, get_config
from termai.models import CATALOG, MODEL_DIR
from termai.allowlist import (
    get_permanent_list, add_to_permanent, remove_from_permanent,
    get_safe_commands, disable_safe_command, enable_safe_command,
)

MODEL_BASE_URL = "https://gpt4all.io/models/gguf/"

INSTALL_DIRS_UNIX = [
    Path("/usr/local/bin"),
    Path.home() / ".local" / "bin",
    Path.home() / "bin",
]

_download_state: dict = {
    "active": False, "cancelled": False, "pct": 0,
    "downloaded_mb": 0, "total_mb": 0, "speed": "", "eta": "",
    "done": False, "error": "", "logs": [],
}


def _log(msg: str, level: str = "ok") -> None:
    _download_state["logs"].append({"msg": msg, "level": level})


def _is_installed() -> bool:
    """Check if termai is meaningfully set up."""
    has_binary = shutil.which("termai") is not None or getattr(sys, "frozen", False)
    has_config = CONFIG_FILE.exists()
    return has_binary and has_config


def _get_current_model() -> str:
    cfg = get_config()
    return cfg.model


def _models_state() -> list[dict]:
    current = _get_current_model()
    return [
        {
            "name": m.name, "filename": m.filename,
            "size_gb": m.size_gb, "params": m.params,
            "min_ram": m.min_ram, "quality": m.quality,
            "description": m.description,
            "installed": (MODEL_DIR / m.filename).exists(),
            "active": m.filename == current,
        }
        for m in CATALOG
    ]


# -- Shared CSS ---------------------------------------------------------------

_CSS = """
:root {
  --bg: #181825; --bg-card: #1e1e2e; --bg-hover: #313244;
  --bg-input: #11111b; --fg: #cdd6f4; --fg-dim: #585b70;
  --fg-sub: #a6adc8; --accent: #89b4fa; --accent-dim: #45475a;
  --green: #a6e3a1; --red: #f38ba8; --yellow: #f9e2af; --mauve: #cba6f7;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--fg); min-height: 100vh;
  display: flex; justify-content: center; align-items: flex-start;
  padding: 40px 20px;
}
.wizard, .dashboard { width: 100%; max-width: 640px; }
.step, .tab-content { display: none; animation: fadeIn 0.3s ease; }
.step.active, .tab-content.active { display: block; }
@keyframes fadeIn { from { opacity:0; transform: translateY(10px); } to { opacity:1; transform: translateY(0); } }

h1 { font-size: 28px; font-weight: 700; margin-bottom: 6px; }
h2 { font-size: 20px; font-weight: 600; margin-bottom: 12px; }
.subtitle { color: var(--fg-sub); font-size: 14px; margin-bottom: 28px; }

.card {
  background: var(--bg-card); border: 1px solid var(--accent-dim);
  border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
}
.features { margin: 24px 0; }
.feature { display: flex; align-items: center; gap: 12px; padding: 8px 0; font-size: 15px; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

.model-card {
  background: var(--bg-card); border: 1px solid var(--accent-dim);
  border-radius: 10px; padding: 14px 18px; margin-bottom: 8px;
  cursor: pointer; transition: border-color 0.2s, background 0.2s;
}
.model-card:hover { background: var(--bg-hover); }
.model-card.selected { border-color: var(--accent); background: var(--bg-hover); }
.model-card .top { display: flex; align-items: center; justify-content: space-between; }
.model-card .name { font-size: 15px; font-weight: 600; }
.model-card .meta { color: var(--fg-dim); font-size: 12px; margin-top: 4px; }
.badge { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.badge-Basic { background: var(--yellow); color: var(--bg-input); }
.badge-Good { background: var(--green); color: var(--bg-input); }
.badge-Better { background: var(--accent); color: var(--bg-input); }
.badge-Best { background: var(--mauve); color: var(--bg-input); }
.installed-tag { color: var(--green); font-size: 12px; margin-left: 8px; }
.active-tag { color: var(--mauve); font-size: 12px; margin-left: 8px; font-weight: 600; }

.btn-row { display: flex; justify-content: space-between; margin-top: 32px; }
.btn {
  padding: 12px 28px; border-radius: 8px; border: none;
  font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s;
}
.btn-primary { background: var(--accent); color: var(--bg-input); }
.btn-primary:hover { background: var(--mauve); }
.btn-primary:disabled { background: var(--accent-dim); color: var(--fg-dim); cursor: not-allowed; }
.btn-secondary { background: var(--bg-hover); color: var(--fg-sub); }
.btn-secondary:hover { background: var(--accent-dim); }
.btn-danger { background: var(--red); color: var(--bg-input); }
.btn-danger:hover { opacity: 0.85; }
.btn-sm { padding: 6px 14px; font-size: 12px; }

.progress-wrap { margin: 24px 0 16px; }
.progress-bar { width: 100%; height: 12px; background: var(--bg-input); border-radius: 6px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--mauve)); border-radius: 6px; transition: width 0.3s ease; width: 0%; }
.progress-stats { display: flex; justify-content: space-between; color: var(--fg-dim); font-size: 12px; margin-top: 6px; }
.log-box {
  background: var(--bg-input); border-radius: 8px; padding: 14px 16px; margin-top: 16px; max-height: 200px;
  overflow-y: auto; font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; line-height: 1.8;
}
.log-ok { color: var(--green); } .log-err { color: var(--red); } .log-dim { color: var(--fg-dim); }

.check-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; font-size: 15px; }
.check-item .icon { font-size: 18px; }
.check-ok { color: var(--green); } .check-warn { color: var(--yellow); }

.code-examples { margin-top: 16px; }
.code-row { display: flex; gap: 16px; padding: 5px 0; font-size: 13px; }
.code-cmd { font-family: 'SF Mono', Menlo, Consolas, monospace; color: var(--accent); white-space: nowrap; }
.code-desc { color: var(--fg-dim); }

/* Tabs */
.tab-bar { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 1px solid var(--accent-dim); }
.tab-btn {
  padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer;
  background: none; border: none; color: var(--fg-dim); border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.tab-btn:hover { color: var(--fg); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }

/* Allow list */
.allow-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; background: var(--bg-card); border: 1px solid var(--accent-dim);
  border-radius: 8px; margin-bottom: 6px;
}
.allow-item .cmd { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 13px; color: var(--accent); }
.allow-item .remove-btn {
  background: none; border: none; color: var(--fg-dim); cursor: pointer;
  font-size: 16px; padding: 2px 8px; border-radius: 4px; transition: all 0.2s;
}
.allow-item .remove-btn:hover { color: var(--red); background: var(--bg-hover); }

.add-row { display: flex; gap: 8px; margin-top: 12px; }
.add-input {
  flex: 1; padding: 10px 14px; background: var(--bg-input); border: 1px solid var(--accent-dim);
  border-radius: 8px; color: var(--fg); font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 13px; outline: none;
}
.add-input:focus { border-color: var(--accent); }
.add-input::placeholder { color: var(--fg-dim); }

.safe-list {
  max-height: 280px; overflow-y: auto; padding: 12px 16px;
  background: var(--bg-input); border-radius: 8px; margin-top: 8px;
  display: flex; flex-wrap: wrap; gap: 6px;
}
.safe-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 6px; font-size: 12px;
  font-family: 'SF Mono', Menlo, Consolas, monospace; cursor: pointer;
  transition: all 0.2s; border: 1px solid transparent; user-select: none;
}
.safe-chip.enabled { background: var(--bg-hover); color: var(--green); border-color: var(--accent-dim); }
.safe-chip.disabled { background: var(--bg); color: var(--fg-dim); text-decoration: line-through; opacity: 0.5; }
.safe-chip:hover { border-color: var(--accent); opacity: 1; }

/* History */
.history-item {
  background: var(--bg-card); border: 1px solid var(--accent-dim);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;
}
.history-item .cmd {
  font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 13px;
  color: var(--accent); margin-bottom: 4px;
}
.history-item .instruction { color: var(--fg-sub); font-size: 13px; margin-bottom: 4px; }
.history-item .meta { color: var(--fg-dim); font-size: 11px; display: flex; gap: 16px; }
.history-item .status-ok { color: var(--green); }
.history-item .status-fail { color: var(--red); }
.history-controls { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
.history-controls select {
  padding: 8px 12px; background: var(--bg-input); border: 1px solid var(--accent-dim);
  border-radius: 8px; color: var(--fg); font-size: 13px; outline: none; cursor: pointer;
}
.history-controls select:focus { border-color: var(--accent); }
.history-empty { color: var(--fg-dim); font-size: 14px; padding: 20px 0; text-align: center; }

/* Processes */
.process-item {
  background: var(--bg-card); border: 1px solid var(--accent-dim);
  border-radius: 8px; padding: 14px 16px; margin-bottom: 10px;
}
.process-item .proc-header {
  display: flex; align-items: center; gap: 10px; margin-bottom: 6px; cursor: pointer;
}
.process-item .proc-instruction {
  font-size: 14px; font-weight: 600; color: var(--fg); flex: 1;
}
.process-item .proc-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600;
}
.proc-badge.completed { background: rgba(52,199,89,.15); color: var(--green); }
.proc-badge.partial { background: rgba(255,204,0,.15); color: var(--yellow); }
.proc-badge.failed { background: rgba(255,59,48,.15); color: var(--red); }
.proc-badge.cancelled { background: rgba(150,150,150,.15); color: var(--fg-dim); }
.process-item .proc-meta {
  color: var(--fg-dim); font-size: 11px; display: flex; gap: 14px; margin-bottom: 8px;
}
.process-item .proc-steps { display: none; margin-top: 10px; }
.process-item.expanded .proc-steps { display: block; }
.process-item .proc-step {
  display: flex; align-items: baseline; gap: 8px; padding: 4px 0;
  font-size: 13px; border-top: 1px solid var(--accent-dim);
}
.process-item .proc-step:first-child { border-top: none; }
.proc-step .step-cmd {
  font-family: 'SF Mono', Menlo, Consolas, monospace; color: var(--accent); flex: 1;
}
.proc-step .step-desc { color: var(--fg-dim); font-size: 11px; }
.proc-step .step-dur { color: var(--fg-dim); font-size: 11px; white-space: nowrap; }
.proc-expand { color: var(--fg-dim); font-size: 12px; cursor: pointer; user-select: none; }

.toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  background: var(--green); color: var(--bg-input); padding: 10px 24px;
  border-radius: 8px; font-weight: 600; font-size: 14px;
  opacity: 0; transition: opacity 0.3s; pointer-events: none; z-index: 100;
}
.toast.show { opacity: 1; }
"""


# -- HTML builder: wizard + settings ------------------------------------------

def _build_html(mode: str = "auto") -> str:
    models_json = json.dumps(_models_state())
    allowed_json = json.dumps(sorted(get_permanent_list()))
    safe_json = json.dumps(get_safe_commands())
    current_model = _get_current_model()
    show_settings = "true" if mode == "settings" else ("true" if (mode == "auto" and _is_installed()) else "false")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>termai</title>
<style>{_CSS}</style>
</head>
<body>

<div class="wizard" id="wizard-view">
  <!-- Step 0: Welcome -->
  <div class="step active" id="step-0">
    <h1>termai</h1>
    <div class="subtitle">Local AI-Powered Terminal Assistant</div>
    <div class="card features">
      <div class="feature"><div class="dot" style="background:var(--accent)"></div> Natural language to shell commands</div>
      <div class="feature"><div class="dot" style="background:var(--green)"></div> Preview &amp; confirm before execution</div>
      <div class="feature"><div class="dot" style="background:var(--mauve)"></div> Runs fully offline with a local LLM</div>
      <div class="feature"><div class="dot" style="background:var(--yellow)"></div> Interactive chat mode</div>
    </div>
    <div class="subtitle">This wizard will install termai and set up a local AI model.</div>
    <div class="btn-row" style="justify-content:flex-end">
      <button class="btn btn-primary" onclick="showStep(1)">Get Started</button>
    </div>
  </div>

  <!-- Step 1: Model selection (wizard) -->
  <div class="step" id="step-1">
    <h1>Choose a Model</h1>
    <div class="subtitle">Downloaded once and stored locally. No internet needed after setup.</div>
    <div id="model-list"></div>
    <div class="btn-row">
      <button class="btn btn-secondary" onclick="showStep(0)">Back</button>
      <button class="btn btn-primary" onclick="startInstall()">Continue</button>
    </div>
  </div>

  <!-- Step 2: Installing -->
  <div class="step" id="step-2">
    <h1 id="install-title">Setting up...</h1>
    <div class="subtitle" id="install-status">Preparing...</div>
    <div class="progress-wrap">
      <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
      <div class="progress-stats">
        <span id="progress-pct"></span>
        <span id="progress-speed"></span>
      </div>
    </div>
    <div class="log-box" id="log-box"></div>
  </div>

  <!-- Step 3: Done -->
  <div class="step" id="step-3">
    <h1>You're all set!</h1>
    <div class="subtitle">termai is ready to use.</div>
    <div id="finish-checks" style="margin:20px 0"></div>
    <div class="card">
      <div style="font-weight:600;margin-bottom:10px">Quick start</div>
      <div class="code-examples">
        <div class="code-row"><span class="code-cmd">termai "list files"</span><span class="code-desc">generate a command</span></div>
        <div class="code-row"><span class="code-cmd">termai -y "free disk space"</span><span class="code-desc">run immediately</span></div>
        <div class="code-row"><span class="code-cmd">termai --chat</span><span class="code-desc">interactive mode</span></div>
        <div class="code-row"><span class="code-cmd">tai "show git log"</span><span class="code-desc">short alias</span></div>
      </div>
    </div>
    <div class="btn-row">
      <button class="btn btn-secondary" onclick="openSettings()">Settings</button>
      <button class="btn btn-primary" onclick="fetch('/api/shutdown');window.close();">Close</button>
    </div>
  </div>
</div>

<!-- ====================== SETTINGS DASHBOARD ====================== -->
<div class="dashboard" id="settings-view" style="display:none">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <h1>termai settings</h1>
    <button class="btn btn-secondary btn-sm" onclick="fetch('/api/shutdown');window.close();">Close</button>
  </div>
  <div class="subtitle">Manage your AI model, allow list, prompt history, and configuration.</div>

  <div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('models', this)">Models</button>
    <button class="tab-btn" onclick="switchTab('remote', this)">Remote AI</button>
    <button class="tab-btn" onclick="switchTab('allowlist', this)">Allow List</button>
    <button class="tab-btn" onclick="switchTab('history', this)">History</button>
    <button class="tab-btn" onclick="switchTab('processes', this)">Processes</button>
    <button class="tab-btn" onclick="switchTab('config', this)">Config</button>
  </div>

  <!-- Tab: Models -->
  <div class="tab-content active" id="tab-models">
    <h2>AI Models</h2>
    <div class="subtitle">Switch your active model or download a new one.</div>
    <div id="settings-model-list"></div>
  </div>

  <!-- Tab: Remote AI -->
  <div class="tab-content" id="tab-remote">
    <h2>Remote AI</h2>
    <div class="subtitle">Connect to OpenAI or Claude for complex tasks. Local AI handles simple ones, remote handles the rest.</div>

    <div class="card" style="margin-bottom:16px">
      <div style="font-weight:600;margin-bottom:12px">Provider</div>
      <div style="display:flex;gap:8px;margin-bottom:16px">
        <button class="btn btn-secondary btn-sm" id="rp-none" onclick="setRemoteProvider('')">None (local only)</button>
        <button class="btn btn-secondary btn-sm" id="rp-openai" onclick="setRemoteProvider('openai')">OpenAI</button>
        <button class="btn btn-secondary btn-sm" id="rp-claude" onclick="setRemoteProvider('claude')">Claude</button>
      </div>

      <div id="remote-openai-cfg" style="display:none">
        <div style="font-weight:600;margin-bottom:8px">OpenAI API Key</div>
        <div class="add-row" style="margin-bottom:12px">
          <input type="password" class="add-input" id="openai-key-input" placeholder="sk-..." />
        </div>
        <div style="font-weight:600;margin-bottom:8px">Model</div>
        <select id="openai-model-select" class="add-input" style="width:auto;margin-bottom:12px">
          <option value="gpt-4o-mini">GPT-4o Mini (fast, affordable)</option>
          <option value="gpt-4o">GPT-4o (most capable)</option>
          <option value="gpt-4.1-mini">GPT-4.1 Mini (latest mini)</option>
          <option value="gpt-4.1">GPT-4.1 (latest flagship)</option>
        </select>
      </div>

      <div id="remote-claude-cfg" style="display:none">
        <div style="font-weight:600;margin-bottom:8px">Claude API Key</div>
        <div class="add-row" style="margin-bottom:12px">
          <input type="password" class="add-input" id="claude-key-input" placeholder="sk-ant-..." />
        </div>
        <div style="font-weight:600;margin-bottom:8px">Model</div>
        <select id="claude-model-select" class="add-input" style="width:auto;margin-bottom:12px">
          <option value="claude-sonnet-4-20250514">Claude Sonnet 4 (balanced)</option>
          <option value="claude-haiku-3-5-20241022">Claude 3.5 Haiku (fast)</option>
          <option value="claude-opus-4-20250514">Claude Opus 4 (most capable)</option>
        </select>
      </div>

      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn btn-primary btn-sm" onclick="saveRemoteConfig()">Save</button>
        <button class="btn btn-secondary btn-sm" onclick="testRemoteConnection()">Test Connection</button>
        <span id="remote-status" style="font-size:13px"></span>
      </div>
    </div>

    <div class="subtitle">How it works: local AI handles simple commands instantly. When a complex task is detected, it's delegated to the remote provider. If the remote provider fails, the local result is used as fallback.</div>
  </div>

  <!-- Tab: Allow List -->
  <div class="tab-content" id="tab-allowlist">
    <h2>Command Allow List</h2>
    <div class="subtitle">Commands on this list run without confirmation prompts.</div>

    <div style="margin-bottom:20px">
      <div style="font-weight:600;margin-bottom:8px">Your allowed commands</div>
      <div id="user-allow-list"></div>
      <div id="allow-empty" class="subtitle" style="display:none;margin-top:8px">No custom commands yet. Commands you approve with "a" (always allow) appear here.</div>
      <div class="add-row">
        <input type="text" class="add-input" id="add-cmd-input" placeholder="e.g. npm install, docker build, pip install" />
        <button class="btn btn-primary btn-sm" onclick="addAllowedCmd()">Add</button>
      </div>
    </div>

    <div>
      <div style="font-weight:600;margin-bottom:4px">Built-in safe commands <span style="color:var(--fg-dim);font-weight:400;font-size:12px">(click to toggle)</span></div>
      <div class="subtitle" style="margin-bottom:8px">Enabled commands auto-execute without prompting. Click to disable/enable.</div>
      <div class="safe-list" id="safe-list"></div>
    </div>
  </div>

  <!-- Tab: History -->
  <div class="tab-content" id="tab-history">
    <h2>Prompt History</h2>
    <div class="subtitle">Commands generated and executed through termai.</div>
    <div class="history-controls">
      <select id="history-limit" onchange="renderHistory()">
        <option value="20">Last 20</option>
        <option value="50">Last 50</option>
        <option value="100">Last 100</option>
        <option value="500">All</option>
      </select>
      <select id="history-filter" onchange="renderHistory()">
        <option value="all">All</option>
        <option value="success">Succeeded</option>
        <option value="failed">Failed</option>
        <option value="with-prompt">With instruction</option>
      </select>
      <div style="flex:1"></div>
      <button class="btn btn-secondary btn-sm" onclick="renderHistory()">Refresh</button>
      <button class="btn btn-secondary btn-sm" style="color:var(--red);border-color:var(--red)" onclick="clearHistory()">Clear All</button>
    </div>
    <div id="history-list"></div>
  </div>

  <!-- Tab: Processes -->
  <div class="tab-content" id="tab-processes">
    <h2>Process History</h2>
    <div class="subtitle">Multi-step orchestrated tasks — prompt, AI, steps, and results.</div>
    <div class="history-controls">
      <select id="proc-limit" onchange="renderProcesses()">
        <option value="20">Last 20</option>
        <option value="50">Last 50</option>
        <option value="100">Last 100</option>
      </select>
      <select id="proc-filter" onchange="renderProcesses()">
        <option value="all">All</option>
        <option value="completed">Completed</option>
        <option value="partial">Partial</option>
        <option value="failed">Failed</option>
      </select>
      <div style="flex:1"></div>
      <button class="btn btn-secondary btn-sm" onclick="renderProcesses()">Refresh</button>
      <button class="btn btn-secondary btn-sm" style="color:var(--red);border-color:var(--red)" onclick="clearProcesses()">Clear All</button>
    </div>
    <div id="proc-list"></div>
  </div>

  <!-- Tab: Config -->
  <div class="tab-content" id="tab-config">
    <h2>Configuration</h2>
    <div class="subtitle">Current settings from ~/.termai/config.toml</div>
    <div class="card" id="config-display" style="font-family:'SF Mono',Menlo,Consolas,monospace;font-size:13px;line-height:2;white-space:pre"></div>
    <div class="subtitle" style="margin-top:12px">Edit this file directly at <span style="color:var(--accent)">~/.termai/config.toml</span></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const MODELS = {models_json};
const CURRENT_MODEL = "{current_model}";
let allowedCmds = {allowed_json};
let safeCommands = {safe_json};
let selectedModel = 0;
let pollTimer = null;
const showSettings = {show_settings};

// Init: show wizard or settings
if (showSettings) openSettings();

function showStep(n) {{
  document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
  document.getElementById('step-' + n).classList.add('active');
}}

function openSettings() {{
  document.getElementById('wizard-view').style.display = 'none';
  document.getElementById('settings-view').style.display = 'block';
  renderSettingsModels();
  renderAllowList();
  renderSafeList();
  renderConfig();
}}

function switchTab(name, btn) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'history') renderHistory();
  if (name === 'processes') renderProcesses();
  if (name === 'remote') loadRemoteConfig();
}}

function toast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}}

// ---- Wizard: model cards ----
(function() {{
  const list = document.getElementById('model-list');
  MODELS.forEach((m, i) => {{
    const card = document.createElement('div');
    card.className = 'model-card' + (i === 0 ? ' selected' : '');
    card.onclick = () => {{
      selectedModel = i;
      document.querySelectorAll('#model-list .model-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
    }};
    const installed = m.installed ? '<span class="installed-tag">✓ installed</span>' : '';
    card.innerHTML = `<div class="top"><span class="name">${{m.name}}${{installed}}</span><span class="badge badge-${{m.quality}}">${{m.quality}}</span></div>
      <div class="meta">${{m.size_gb}} GB · ${{m.params}} params · min ${{m.min_ram}} RAM — ${{m.description}}</div>`;
    list.appendChild(card);
  }});
  const skip = document.createElement('div');
  skip.className = 'model-card';
  skip.onclick = () => {{ selectedModel = -1; document.querySelectorAll('#model-list .model-card').forEach(c => c.classList.remove('selected')); skip.classList.add('selected'); }};
  skip.innerHTML = '<div class="name">Skip — no AI model (rule-based fallback only)</div><div class="meta">No download required</div>';
  list.appendChild(skip);
}})();

// ---- Wizard: install flow ----
function startInstall() {{
  showStep(2);
  fetch('/api/install', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{ model_idx: selectedModel }}) }});
  pollTimer = setInterval(pollProgress, 1000);
}}

function pollProgress() {{
  fetch('/api/progress').then(r => r.json()).then(s => {{
    document.getElementById('progress-fill').style.width = s.pct + '%';
    document.getElementById('progress-pct').textContent = s.total_mb > 0 ? s.downloaded_mb.toFixed(0)+' / '+s.total_mb.toFixed(0)+' MB  ('+s.pct.toFixed(0)+'%)' : '';
    document.getElementById('progress-speed').textContent = s.speed ? s.speed+'   '+s.eta : '';
    if (s.status) document.getElementById('install-status').textContent = s.status;
    if (s.title) document.getElementById('install-title').textContent = s.title;
    const box = document.getElementById('log-box');
    if (s.logs && s.logs.length > box.children.length) {{
      for (let i = box.children.length; i < s.logs.length; i++) {{
        const div = document.createElement('div');
        div.className = 'log-' + s.logs[i].level;
        div.textContent = (s.logs[i].level==='ok'?'✓ ':s.logs[i].level==='err'?'✗ ':'  ') + s.logs[i].msg;
        box.appendChild(div); box.scrollTop = box.scrollHeight;
      }}
    }}
    if (s.done) {{ clearInterval(pollTimer); setTimeout(() => showFinish(s), 500); }}
    if (s.error) {{ clearInterval(pollTimer); document.getElementById('install-title').textContent = 'Installation failed'; document.getElementById('install-status').textContent = s.error; }}
  }}).catch(() => {{}});
}}

function showFinish(s) {{
  const checks = document.getElementById('finish-checks');
  checks.innerHTML = '';
  (s.checks || []).forEach(c => {{
    checks.innerHTML += '<div class="check-item '+(c.ok?'check-ok':'check-warn')+'"><span class="icon">'+(c.ok?'✓':'○')+'</span> '+c.label+'</div>';
  }});
  showStep(3);
}}

// ---- Settings: Models ----
function renderSettingsModels() {{
  fetch('/api/models').then(r => r.json()).then(models => {{
    const list = document.getElementById('settings-model-list');
    list.innerHTML = '';
    models.forEach((m, i) => {{
      const card = document.createElement('div');
      card.className = 'model-card';
      const installed = m.installed ? '<span class="installed-tag">✓ installed</span>' : '';
      const active = m.active ? '<span class="active-tag">● active</span>' : '';
      let actionBtn = '';
      if (m.active) {{
        actionBtn = '<button class="btn btn-secondary btn-sm" disabled>Active</button>';
      }} else if (m.installed) {{
        actionBtn = `<button class="btn btn-primary btn-sm" onclick="switchModel(${{i}})">Switch to this</button>`;
      }} else {{
        actionBtn = `<button class="btn btn-primary btn-sm" onclick="downloadAndSwitch(${{i}})">Download &amp; activate</button>`;
      }}
      card.innerHTML = `<div class="top"><span class="name">${{m.name}}${{installed}}${{active}}</span><span class="badge badge-${{m.quality}}">${{m.quality}}</span></div>
        <div class="meta">${{m.size_gb}} GB · ${{m.params}} params · min ${{m.min_ram}} RAM — ${{m.description}}</div>
        <div style="margin-top:10px;text-align:right">${{actionBtn}}</div>`;
      list.appendChild(card);
    }});
  }});
}}

function switchModel(idx) {{
  fetch('/api/switch-model', {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify({{model_idx: idx}}) }})
    .then(r => r.json()).then(d => {{
      if (d.ok) {{ toast('Switched to ' + d.name); renderSettingsModels(); }}
      else toast('Error: ' + d.error);
    }});
}}

function downloadAndSwitch(idx) {{
  fetch('/api/download-model', {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify({{model_idx: idx}}) }})
    .then(() => {{
      toast('Downloading... this may take a few minutes');
      const poll = setInterval(() => {{
        fetch('/api/progress').then(r => r.json()).then(s => {{
          if (s.done) {{ clearInterval(poll); toast('Download complete!'); renderSettingsModels(); }}
        }});
      }}, 2000);
    }});
}}

// ---- Settings: Allow List ----
function renderAllowList() {{
  fetch('/api/allowlist').then(r => r.json()).then(data => {{
    allowedCmds = data;
    const list = document.getElementById('user-allow-list');
    const empty = document.getElementById('allow-empty');
    list.innerHTML = '';
    if (data.length === 0) {{ empty.style.display = 'block'; return; }}
    empty.style.display = 'none';
    data.forEach(cmd => {{
      const item = document.createElement('div');
      item.className = 'allow-item';
      item.innerHTML = `<span class="cmd">${{cmd}}</span><button class="remove-btn" onclick="removeAllowed('${{cmd.replace(/'/g, "\\\\'")}}')">✕</button>`;
      list.appendChild(item);
    }});
  }});
}}

function addAllowedCmd() {{
  const input = document.getElementById('add-cmd-input');
  const cmd = input.value.trim();
  if (!cmd) return;
  fetch('/api/allowlist/add', {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify({{command: cmd}}) }})
    .then(r => r.json()).then(() => {{ input.value = ''; renderAllowList(); toast('Added: ' + cmd); }});
}}

function removeAllowed(cmd) {{
  fetch('/api/allowlist/remove', {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify({{command: cmd}}) }})
    .then(r => r.json()).then(() => {{ renderAllowList(); toast('Removed: ' + cmd); }});
}}

function renderSafeList() {{
  fetch('/api/safe-commands').then(r => r.json()).then(data => {{
    safeCommands = data;
    const list = document.getElementById('safe-list');
    list.innerHTML = '';
    Object.entries(data).sort((a,b) => a[0].localeCompare(b[0])).forEach(([cmd, enabled]) => {{
      const chip = document.createElement('span');
      chip.className = 'safe-chip ' + (enabled ? 'enabled' : 'disabled');
      chip.textContent = cmd;
      chip.onclick = () => toggleSafe(cmd, enabled);
      list.appendChild(chip);
    }});
  }});
}}

function toggleSafe(cmd, currentlyEnabled) {{
  const endpoint = currentlyEnabled ? '/api/safe-commands/disable' : '/api/safe-commands/enable';
  fetch(endpoint, {{ method: 'POST', headers: {{'Content-Type':'application/json'}}, body: JSON.stringify({{command: cmd}}) }})
    .then(r => r.json()).then(() => {{
      toast((currentlyEnabled ? 'Disabled: ' : 'Enabled: ') + cmd);
      renderSafeList();
    }});
}}

// ---- Settings: Config ----
function renderConfig() {{
  fetch('/api/config').then(r => r.json()).then(cfg => {{
    document.getElementById('config-display').textContent = Object.entries(cfg).map(([k,v]) => k + ' = ' + JSON.stringify(v)).join('\\n');
  }});
}}

// ---- Remote AI ----
let currentRemoteProvider = '';

function loadRemoteConfig() {{
  fetch('/api/remote-config').then(r => r.json()).then(cfg => {{
    currentRemoteProvider = cfg.provider || '';
    updateProviderButtons(currentRemoteProvider);
    if (cfg.openai_api_key) document.getElementById('openai-key-input').value = cfg.openai_api_key;
    if (cfg.claude_api_key) document.getElementById('claude-key-input').value = cfg.claude_api_key;
    if (cfg.remote_model) {{
      const oSel = document.getElementById('openai-model-select');
      const cSel = document.getElementById('claude-model-select');
      if (currentRemoteProvider === 'openai') oSel.value = cfg.remote_model;
      if (currentRemoteProvider === 'claude') cSel.value = cfg.remote_model;
    }}
  }}).catch(() => {{}});
}}

function setRemoteProvider(provider) {{
  currentRemoteProvider = provider;
  updateProviderButtons(provider);
}}

function updateProviderButtons(provider) {{
  ['none', 'openai', 'claude'].forEach(p => {{
    const btn = document.getElementById('rp-' + p);
    const val = p === 'none' ? '' : p;
    btn.className = 'btn btn-sm ' + (val === provider ? 'btn-primary' : 'btn-secondary');
  }});
  document.getElementById('remote-openai-cfg').style.display = provider === 'openai' ? 'block' : 'none';
  document.getElementById('remote-claude-cfg').style.display = provider === 'claude' ? 'block' : 'none';
  document.getElementById('remote-status').textContent = '';
}}

function saveRemoteConfig() {{
  const data = {{
    provider: currentRemoteProvider,
    openai_api_key: document.getElementById('openai-key-input').value.trim(),
    claude_api_key: document.getElementById('claude-key-input').value.trim(),
    remote_model: currentRemoteProvider === 'openai'
      ? document.getElementById('openai-model-select').value
      : currentRemoteProvider === 'claude'
        ? document.getElementById('claude-model-select').value
        : '',
  }};
  fetch('/api/remote-config', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify(data)
  }}).then(r => r.json()).then(res => {{
    if (res.ok) toast('Remote AI settings saved');
    else toast('Error saving: ' + (res.error || 'unknown'));
  }});
}}

function testRemoteConnection() {{
  const status = document.getElementById('remote-status');
  status.textContent = 'Testing...';
  status.style.color = 'var(--fg-dim)';
  fetch('/api/remote-test', {{ method: 'POST' }}).then(r => r.json()).then(res => {{
    status.textContent = res.ok ? '✓ ' + res.message : '✗ ' + res.message;
    status.style.color = res.ok ? 'var(--green)' : 'var(--red)';
  }}).catch(() => {{
    status.textContent = '✗ Request failed';
    status.style.color = 'var(--red)';
  }});
}}

// ---- History ----
let historyCache = null;
async function loadHistory(limit) {{
  const r = await fetch('/api/history?limit=' + limit);
  historyCache = await r.json();
}}
async function renderHistory() {{
  const limit = document.getElementById('history-limit').value;
  const filter = document.getElementById('history-filter').value;
  await loadHistory(limit);
  let items = historyCache || [];
  if (filter === 'success') items = items.filter(e => e.success === true);
  else if (filter === 'failed') items = items.filter(e => e.success === false);
  else if (filter === 'with-prompt') items = items.filter(e => e.instruction);
  const container = document.getElementById('history-list');
  if (!items.length) {{
    container.innerHTML = '<div class="history-empty">No history entries found.</div>';
    return;
  }}
  container.innerHTML = items.slice().reverse().map(e => {{
    const ts = (e.timestamp || '').slice(0, 19).replace('T', ' ');
    const statusCls = e.success === true ? 'status-ok' : (e.success === false ? 'status-fail' : '');
    const statusTxt = e.success === true ? '✓' : (e.success === false ? '✗' : '?');
    return `<div class="history-item">
      <div class="cmd">${{e.command || '?'}}</div>
      ${{e.instruction ? `<div class="instruction">Prompt: ${{e.instruction}}</div>` : ''}}
      <div class="meta">
        <span class="${{statusCls}}">${{statusTxt}}</span>
        <span>${{ts}}</span>
        <span>${{e.cwd || ''}}</span>
      </div>
    </div>`;
  }}).join('');
}}

async function clearHistory() {{
  if (!confirm('Clear all prompt history? This cannot be undone.')) return;
  await fetch('/api/history/clear', {{method:'POST'}});
  toast('History cleared');
  renderHistory();
}}

// ---- Processes ----
let processCache = null;
async function loadProcesses(limit) {{
  const r = await fetch('/api/processes?limit=' + limit);
  processCache = await r.json();
}}
async function renderProcesses() {{
  const limit = document.getElementById('proc-limit').value;
  const filter = document.getElementById('proc-filter').value;
  await loadProcesses(limit);
  let items = processCache || [];
  if (filter !== 'all') items = items.filter(e => e.status === filter);
  const container = document.getElementById('proc-list');
  if (!items.length) {{
    container.innerHTML = '<div class="history-empty">No process history found.</div>';
    return;
  }}
  container.innerHTML = items.slice().reverse().map((p, idx) => {{
    const ts = (p.timestamp || '').slice(0, 19).replace('T', ' ');
    const steps = p.steps || [];
    const succeeded = steps.filter(s => s.status === 'success').length;
    const total = steps.length;
    const dur = p.total_duration_ms != null
      ? (p.total_duration_ms >= 1000 ? (p.total_duration_ms/1000).toFixed(1) + 's' : p.total_duration_ms + 'ms')
      : '';
    const badgeCls = p.status || 'unknown';
    const statusLabel = p.status || '?';
    const ai = p.ai_provider || '?';
    const pid = p.id || '?';

    const stepsHtml = steps.map(s => {{
      const sIcon = s.status === 'success' ? '<span style="color:var(--green)">✓</span>'
        : s.status === 'failed' ? '<span style="color:var(--red)">✗</span>'
        : s.status === 'skipped' ? '<span style="color:var(--yellow)">⊘</span>'
        : '<span style="color:var(--fg-dim)">?</span>';
      const sDur = s.duration_ms != null
        ? (s.duration_ms >= 1000 ? (s.duration_ms/1000).toFixed(1) + 's' : s.duration_ms + 'ms')
        : '';
      return `<div class="proc-step">
        ${{sIcon}}
        <span class="step-cmd">${{s.command || '?'}}</span>
        ${{s.description ? `<span class="step-desc">${{s.description}}</span>` : ''}}
        <span class="step-dur">${{sDur}}</span>
      </div>`;
    }}).join('');

    return `<div class="process-item" id="proc-${{idx}}">
      <div class="proc-header" onclick="document.getElementById('proc-${{idx}}').classList.toggle('expanded')">
        <span class="proc-expand">▸</span>
        <span class="proc-instruction">${{p.instruction || '?'}}</span>
        <span class="proc-badge ${{badgeCls}}">${{statusLabel}}</span>
      </div>
      <div class="proc-meta">
        <span>${{ts}}</span>
        <span>${{ai}}</span>
        <span>${{succeeded}}/${{total}} steps</span>
        <span>${{dur}}</span>
        <span style="opacity:.5">${{pid}}</span>
      </div>
      <div class="proc-steps">${{stepsHtml}}</div>
    </div>`;
  }}).join('');
}}
async function clearProcesses() {{
  if (!confirm('Clear all process history? This cannot be undone.')) return;
  await fetch('/api/processes/clear', {{method:'POST'}});
  toast('Process history cleared');
  renderProcesses();
}}

// ---- Add-input enter key ----
document.addEventListener('keydown', e => {{
  if (e.key === 'Enter' && document.activeElement && document.activeElement.id === 'add-cmd-input') addAllowedCmd();
}});

// Heartbeat (watchdog detects disconnection; no automatic shutdown on refresh)
setInterval(() => fetch('/api/heartbeat').catch(() => {{}}), 2000);
</script>
</body>
</html>"""


# -- HTTP server + API -------------------------------------------------------

class _WizardHandler(BaseHTTPRequestHandler):
    html_page: str = ""
    server_ref: HTTPServer | None = None
    last_heartbeat: float = 0.0

    def do_GET(self) -> None:
        if self.path == "/":
            self._respond(200, "text/html", self.html_page.encode())
        elif self.path == "/api/progress":
            self._respond(200, "application/json", json.dumps(_download_state).encode())
        elif self.path == "/api/heartbeat":
            _WizardHandler.last_heartbeat = time.monotonic()
            self._respond(200, "text/plain", b"ok")
        elif self.path == "/api/models":
            self._respond(200, "application/json", json.dumps(_models_state()).encode())
        elif self.path == "/api/allowlist":
            self._respond(200, "application/json", json.dumps(sorted(get_permanent_list())).encode())
        elif self.path == "/api/config":
            cfg = get_config()
            data = {"model": cfg.model, "device": cfg.device,
                    "max_tokens": cfg.max_tokens, "temperature": cfg.temperature,
                    "remote_provider": cfg.remote_provider,
                    "remote_model": cfg.remote_model,
                    "config_file": str(CONFIG_FILE)}
            self._respond(200, "application/json", json.dumps(data).encode())
        elif self.path == "/api/remote-config":
            cfg = get_config()
            masked_openai = _mask_key(cfg.openai_api_key)
            masked_claude = _mask_key(cfg.claude_api_key)
            data = {
                "provider": cfg.remote_provider,
                "remote_model": cfg.remote_model,
                "openai_api_key": masked_openai,
                "claude_api_key": masked_claude,
                "has_openai_key": bool(cfg.openai_api_key),
                "has_claude_key": bool(cfg.claude_api_key),
            }
            self._respond(200, "application/json", json.dumps(data).encode())
        elif self.path.startswith("/api/history"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["50"])[0])
            from termai.logger import read_history
            entries = read_history(limit)
            self._respond(200, "application/json", json.dumps(entries).encode())
        elif self.path.startswith("/api/processes"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["20"])[0])
            from termai.process_log import read_processes
            entries = read_processes(limit)
            self._respond(200, "application/json", json.dumps(entries).encode())
        elif self.path == "/api/safe-commands":
            self._respond(200, "application/json", json.dumps(get_safe_commands()).encode())
        elif self.path == "/api/shutdown":
            self._respond(200, "text/plain", b"bye")
            threading.Thread(target=self._shutdown, daemon=True).start()
        else:
            self._respond(404, "text/plain", b"not found")

    def do_POST(self) -> None:
        body = self._read_body()

        if self.path == "/api/install":
            model_idx = body.get("model_idx", -1)
            self._respond(200, "application/json", b'{"ok":true}')
            threading.Thread(target=_run_install, args=(model_idx,), daemon=True).start()

        elif self.path == "/api/switch-model":
            idx = body.get("model_idx", -1)
            if 0 <= idx < len(CATALOG):
                m = CATALOG[idx]
                if (MODEL_DIR / m.filename).exists():
                    from termai.models import _save_model_choice
                    _save_model_choice(m.filename)
                    # Reset cached config
                    import termai.config as _cfg
                    _cfg._config = None
                    self._respond(200, "application/json",
                                  json.dumps({"ok": True, "name": m.name}).encode())
                else:
                    self._respond(200, "application/json",
                                  json.dumps({"ok": False, "error": "Model not downloaded"}).encode())
            else:
                self._respond(400, "application/json", b'{"ok":false,"error":"Invalid index"}')

        elif self.path == "/api/download-model":
            idx = body.get("model_idx", -1)
            if 0 <= idx < len(CATALOG):
                self._respond(200, "application/json", b'{"ok":true}')
                threading.Thread(target=_download_and_switch, args=(idx,), daemon=True).start()
            else:
                self._respond(400, "application/json", b'{"ok":false}')

        elif self.path == "/api/allowlist/add":
            cmd = body.get("command", "")
            if cmd:
                add_to_permanent(cmd)
            self._respond(200, "application/json", b'{"ok":true}')

        elif self.path == "/api/allowlist/remove":
            cmd = body.get("command", "")
            if cmd:
                remove_from_permanent(cmd)
            self._respond(200, "application/json", b'{"ok":true}')

        elif self.path == "/api/safe-commands/disable":
            cmd = body.get("command", "")
            if cmd:
                disable_safe_command(cmd)
            self._respond(200, "application/json", b'{"ok":true}')

        elif self.path == "/api/safe-commands/enable":
            cmd = body.get("command", "")
            if cmd:
                enable_safe_command(cmd)
            self._respond(200, "application/json", b'{"ok":true}')

        elif self.path == "/api/remote-config":
            _save_remote_config(body)
            self._respond(200, "application/json", b'{"ok":true}')

        elif self.path == "/api/remote-test":
            ok, msg = _test_remote_connection()
            self._respond(200, "application/json",
                          json.dumps({"ok": ok, "message": msg}).encode())

        elif self.path == "/api/history/clear":
            from termai.logger import LOG_FILE
            try:
                LOG_FILE.write_text("")
            except OSError:
                pass
            self._respond(200, "application/json", b'{"ok":true}')

        elif self.path == "/api/processes/clear":
            from termai.process_log import clear_processes
            clear_processes()
            self._respond(200, "application/json", b'{"ok":true}')

        elif self.path == "/api/shutdown":
            self._respond(200, "text/plain", b"bye")
            threading.Thread(target=self._shutdown, daemon=True).start()

        else:
            self._respond(404, "text/plain", b"not found")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def _respond(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _shutdown(self) -> None:
        time.sleep(2)
        if _download_state.get("active") and not _download_state.get("done") and not _download_state.get("error"):
            return
        if self.server_ref:
            self.server_ref.shutdown()

    def log_message(self, format, *args) -> None:
        pass


# -- Installation / download logic -------------------------------------------

def _run_install(model_idx: int) -> None:
    _download_state.update(
        active=True, cancelled=False, pct=0, downloaded_mb=0,
        total_mb=0, speed="", eta="", done=False, error="",
        logs=[], title="Installing binary...", status="Copying to PATH", checks=[],
    )
    try:
        _do_install_binary()
        if model_idx >= 0:
            model = CATALOG[model_idx]
            if (MODEL_DIR / model.filename).exists():
                _log(f"{model.name} already downloaded", "ok")
            else:
                _download_state["title"] = f"Downloading {model.name}"
                _download_state["status"] = f"{model.size_gb:.1f} GB — this may take a few minutes"
                _download_model(model)
            _save_model_choice(model.filename)
        else:
            _log("Skipped model — using rule-based fallback", "dim")

        _download_state["title"] = "Finishing up..."
        _download_state["status"] = "Writing configuration"
        _do_setup_config()

        checks = [
            {"label": "Binary installed", "ok": shutil.which("termai") is not None or getattr(sys, "frozen", False)},
            {"label": "Configuration", "ok": CONFIG_FILE.exists()},
        ]
        if model_idx >= 0:
            m = CATALOG[model_idx]
            checks.append({"label": f"AI Model ({m.name})", "ok": (MODEL_DIR / m.filename).exists()})
        _download_state["checks"] = checks
        _download_state["done"] = True
    except Exception as e:
        _download_state["error"] = str(e)
        _log(f"Error: {e}", "err")


def _download_and_switch(idx: int) -> None:
    _download_state.update(
        active=True, pct=0, downloaded_mb=0, total_mb=0,
        speed="", eta="", done=False, error="", logs=[],
    )
    try:
        model = CATALOG[idx]
        _download_model(model)
        _save_model_choice(model.filename)
        import termai.config as _cfg
        _cfg._config = None
        _download_state["done"] = True
    except Exception as e:
        _download_state["error"] = str(e)


def _do_install_binary() -> None:
    is_frozen = getattr(sys, "frozen", False)
    if not is_frozen:
        which = shutil.which("termai")
        if which:
            _log(f"termai available at {which}", "ok")
        else:
            _log("termai not on PATH (installed via pip)", "dim")
        return

    current_exe = Path(sys.executable)
    if platform.system() == "Windows":
        install_dir = Path.home() / "AppData" / "Local" / "Programs" / "termai"
        dest = install_dir / "termai.exe"
        tai_dest = install_dir / "tai.exe"
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_exe, dest)
        shutil.copy2(current_exe, tai_dest)
        _log(f"Installed to {dest}", "ok")
        _log("Created tai.exe alias", "ok")
        return

    for d in INSTALL_DIRS_UNIX:
        if d.exists() and os.access(d, os.W_OK):
            dest = d / "termai"
            tai_dest = d / "tai"
            shutil.copy2(current_exe, dest)
            dest.chmod(0o755)
            if tai_dest.exists() or tai_dest.is_symlink():
                tai_dest.unlink()
            tai_dest.symlink_to(dest)
            _log(f"Installed to {dest}", "ok")
            _log("Created tai symlink", "ok")
            return

    dest = INSTALL_DIRS_UNIX[0] / "termai"
    tai_dest = INSTALL_DIRS_UNIX[0] / "tai"
    _log(f"Installing to {INSTALL_DIRS_UNIX[0]} (admin required)", "dim")
    if platform.system() == "Darwin":
        script = (
            f'do shell script "cp {current_exe} {dest} && '
            f'chmod +x {dest} && '
            f'ln -sf {dest} {tai_dest}" with administrator privileges'
        )
        subprocess.run(["osascript", "-e", script], check=True)
    else:
        subprocess.run(["sudo", "cp", str(current_exe), str(dest)], check=True)
        subprocess.run(["sudo", "chmod", "+x", str(dest)], check=True)
        subprocess.run(["sudo", "ln", "-sf", str(dest), str(tai_dest)], check=True)
    _log(f"Installed to {dest}", "ok")
    _log("Created tai symlink", "ok")


def _download_model(model) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    url = MODEL_BASE_URL + model.filename
    dest = MODEL_DIR / model.filename
    tmp = dest.with_suffix(".part")
    _log(f"Downloading from {url}", "dim")

    downloaded = 0
    if tmp.exists():
        downloaded = tmp.stat().st_size
        _log(f"Resuming from {downloaded / 1e6:.1f} MB", "dim")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "termai/0.1"})
            if downloaded > 0:
                req.add_header("Range", f"bytes={downloaded}-")
            resp = urllib.request.urlopen(req, timeout=60)

            if downloaded > 0 and resp.status == 200:
                downloaded = 0
            total_header = resp.headers.get("Content-Length", "0")
            total = int(total_header) + downloaded

            chunk_size = 256 * 1024
            start_time = time.monotonic()
            with open(tmp, "ab" if downloaded > 0 else "wb") as f:
                while True:
                    try:
                        chunk = resp.read(chunk_size)
                    except Exception as read_err:
                        _log(f"Connection interrupted: {read_err}", "dim")
                        break
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    _update_progress(downloaded, total, start_time)

            if total > 0 and downloaded >= total:
                tmp.rename(dest)
                _download_state["pct"] = 100
                _log(f"Model saved to {dest}", "ok")
                return

            if attempt < max_retries - 1:
                _log(f"Download incomplete ({downloaded / 1e6:.0f}/{total / 1e6:.0f} MB), retrying...", "dim")
                time.sleep(2)
                continue
            else:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"Download incomplete after {max_retries} attempts")

        except (urllib.error.URLError, OSError) as e:
            if attempt < max_retries - 1:
                _log(f"Attempt {attempt + 1} failed: {e} — retrying in 3s", "dim")
                time.sleep(3)
            else:
                tmp.unlink(missing_ok=True)
                _log(f"Download failed after {max_retries} attempts: {e}", "err")
                raise


def _update_progress(downloaded: int, total: int, start_time: float) -> None:
    elapsed = max(time.monotonic() - start_time, 0.001)
    speed_bps = downloaded / elapsed
    pct = (downloaded / total * 100) if total > 0 else 0
    if speed_bps > 1e6:
        speed = f"{speed_bps / 1e6:.1f} MB/s"
    elif speed_bps > 1e3:
        speed = f"{speed_bps / 1e3:.0f} KB/s"
    else:
        speed = f"{speed_bps:.0f} B/s"
    if total > 0 and speed_bps > 0:
        remaining = (total - downloaded) / speed_bps
        eta = f"~{remaining / 60:.0f} min left" if remaining > 60 else f"~{remaining:.0f}s left"
    else:
        eta = ""
    _download_state.update(pct=round(pct, 1), downloaded_mb=round(downloaded / 1e6, 1),
                           total_mb=round(total / 1e6, 1), speed=speed, eta=eta)


def _save_model_choice(filename: str) -> None:
    from termai.models import _save_model_choice
    _save_model_choice(filename)
    _log("Saved model choice to config", "ok")


def _do_setup_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        from termai.config import Config
        Config().write_default()
        _log(f"Created config at {CONFIG_FILE}", "ok")
    else:
        _log("Config already exists", "ok")
    plugins_dir = CONFIG_DIR / "plugins"
    plugins_dir.mkdir(exist_ok=True)
    _log("Plugin directory ready", "ok")


# -- Remote AI helpers ---------------------------------------------------------

def _mask_key(key: str) -> str:
    """Mask an API key for display, showing only last 4 chars."""
    if not key or len(key) < 8:
        return ""
    return "•" * (len(key) - 4) + key[-4:]


def _save_remote_config(data: dict) -> None:
    """Write remote AI settings to config.toml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    provider = data.get("provider", "")
    remote_model = data.get("remote_model", "")
    openai_key = data.get("openai_api_key", "")
    claude_key = data.get("claude_api_key", "")

    # Don't overwrite keys with masked values
    cfg = get_config()
    if openai_key and openai_key.startswith("•"):
        openai_key = cfg.openai_api_key
    if claude_key and claude_key.startswith("•"):
        claude_key = cfg.claude_api_key

    if CONFIG_FILE.exists():
        content = CONFIG_FILE.read_text()
    else:
        content = "[termai]\n"

    # Remove existing [remote] section if present
    import re as _re
    content = _re.sub(r"\n?\[remote\][^\[]*", "", content)

    if provider:
        remote_section = f"\n[remote]\nprovider = \"{provider}\"\nmodel = \"{remote_model}\"\n"
        if openai_key:
            remote_section += f'openai_api_key = "{openai_key}"\n'
        if claude_key:
            remote_section += f'claude_api_key = "{claude_key}"\n'
        content = content.rstrip() + "\n" + remote_section

    CONFIG_FILE.write_text(content)

    # Reset cached config so changes take effect
    import termai.config as _cfg
    _cfg._config = None

    from termai.remote import reset_remote_provider
    reset_remote_provider()


def _test_remote_connection() -> tuple[bool, str]:
    """Test the current remote AI configuration."""
    # Reload config first
    import termai.config as _cfg
    _cfg._config = None

    from termai.remote import reset_remote_provider, get_remote_provider
    reset_remote_provider()
    remote = get_remote_provider()

    if not remote:
        return False, "No remote provider configured"
    if not remote.is_available():
        return False, "API key missing"

    return remote.test_connection()


# -- Entry point --------------------------------------------------------------

def _heartbeat_watchdog(server: HTTPServer, handler_cls: type) -> None:
    missed = 0
    while True:
        time.sleep(5)
        if _download_state.get("active") and not _download_state.get("done") and not _download_state.get("error"):
            missed = 0
            continue
        last = handler_cls.last_heartbeat
        if last > 0 and (time.monotonic() - last) > 10:
            missed += 1
        else:
            missed = 0
        if missed >= 6:
            print("[termai] Browser disconnected — shutting down.")
            server.shutdown()
            return


def _open_app_window(url: str) -> None:
    """Open URL in an app-like window (no URL bar, tabs, or bookmarks).

    Tries Chromium-based browsers with --app flag first, then falls back
    to the default browser.
    """
    import subprocess as _sp

    candidates: list[tuple[str, list[str]]] = []

    if platform.system() == "Darwin":
        candidates = [
            ("Google Chrome", [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                f"--app={url}", "--new-window",
            ]),
            ("Chromium", [
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                f"--app={url}", "--new-window",
            ]),
            ("Microsoft Edge", [
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                f"--app={url}", "--new-window",
            ]),
            ("Brave", [
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                f"--app={url}", "--new-window",
            ]),
        ]
    elif platform.system() == "Windows":
        candidates = [
            ("Chrome", ["cmd", "/c", "start", "chrome", f"--app={url}"]),
            ("Edge", ["cmd", "/c", "start", "msedge", f"--app={url}"]),
        ]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            path = shutil.which(name)
            if path:
                candidates.append((name, [path, f"--app={url}", "--new-window"]))

    for name, cmd in candidates:
        try:
            _sp.Popen(cmd, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
            return
        except (FileNotFoundError, OSError):
            continue

    webbrowser.open(url)


def run_gui_wizard(mode: str = "auto") -> None:
    """Launch the browser-based UI.

    mode: "auto" (wizard if first run, settings if installed),
          "wizard" (force wizard), "settings" (force settings).
    """
    page = _build_html(mode=mode)

    handler = type("Handler", (_WizardHandler,), {
        "html_page": page,
        "last_heartbeat": time.monotonic(),
    })
    _PORT = 49152
    for port in range(_PORT, _PORT + 20):
        try:
            server = HTTPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    else:
        server = HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
    handler.server_ref = server
    url = f"http://127.0.0.1:{port}"

    threading.Thread(target=_heartbeat_watchdog, args=(server, handler), daemon=True).start()

    label = "settings" if (mode == "settings" or (mode == "auto" and _is_installed())) else "setup wizard"
    print(f"[termai] Opening {label} at {url}")
    _open_app_window(url)
    server.serve_forever()
    print("[termai] Closed.")
