"""Browser-based GUI installation wizard for termai.

Uses Python's built-in http.server + webbrowser — zero external
dependencies, works on every OS regardless of what's installed.
The wizard runs as a local web page served from a tiny HTTP server.
"""

from __future__ import annotations

import html
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from termai.config import CONFIG_DIR, CONFIG_FILE
from termai.models import CATALOG, MODEL_DIR

MODEL_BASE_URL = "https://gpt4all.io/models/gguf/"

INSTALL_DIRS_UNIX = [
    Path("/usr/local/bin"),
    Path.home() / ".local" / "bin",
    Path.home() / "bin",
]

_download_state: dict = {
    "active": False,
    "cancelled": False,
    "pct": 0,
    "downloaded_mb": 0,
    "total_mb": 0,
    "speed": "",
    "eta": "",
    "done": False,
    "error": "",
    "logs": [],
}


def _log(msg: str, level: str = "ok") -> None:
    _download_state["logs"].append({"msg": msg, "level": level})


# -- HTML/CSS/JS (single-page app) -------------------------------------------

def _build_html() -> str:
    models_json = json.dumps([
        {
            "name": m.name,
            "filename": m.filename,
            "size_gb": m.size_gb,
            "params": m.params,
            "min_ram": m.min_ram,
            "quality": m.quality,
            "description": m.description,
            "installed": (MODEL_DIR / m.filename).exists(),
        }
        for m in CATALOG
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>termai — Setup</title>
<style>
:root {{
  --bg: #181825; --bg-card: #1e1e2e; --bg-hover: #313244;
  --bg-input: #11111b; --fg: #cdd6f4; --fg-dim: #585b70;
  --fg-sub: #a6adc8; --accent: #89b4fa; --accent-dim: #45475a;
  --green: #a6e3a1; --red: #f38ba8; --yellow: #f9e2af; --mauve: #cba6f7;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--fg); min-height: 100vh;
  display: flex; justify-content: center; align-items: flex-start;
  padding: 40px 20px;
}}
.wizard {{ width: 100%; max-width: 600px; }}
.step {{ display: none; animation: fadeIn 0.3s ease; }}
.step.active {{ display: block; }}
@keyframes fadeIn {{ from {{ opacity:0; transform: translateY(10px); }} to {{ opacity:1; transform: translateY(0); }} }}

h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 6px; }}
.subtitle {{ color: var(--fg-sub); font-size: 14px; margin-bottom: 28px; }}

.card {{
  background: var(--bg-card); border: 1px solid var(--accent-dim);
  border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
}}

.features {{ margin: 24px 0; }}
.feature {{
  display: flex; align-items: center; gap: 12px;
  padding: 8px 0; font-size: 15px;
}}
.dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}

.model-card {{
  background: var(--bg-card); border: 1px solid var(--accent-dim);
  border-radius: 10px; padding: 14px 18px; margin-bottom: 8px;
  cursor: pointer; transition: border-color 0.2s, background 0.2s;
}}
.model-card:hover {{ background: var(--bg-hover); }}
.model-card.selected {{ border-color: var(--accent); background: var(--bg-hover); }}
.model-card .top {{ display: flex; align-items: center; justify-content: space-between; }}
.model-card .name {{ font-size: 15px; font-weight: 600; }}
.model-card .meta {{ color: var(--fg-dim); font-size: 12px; margin-top: 4px; }}
.badge {{
  font-size: 10px; font-weight: 700; padding: 2px 8px;
  border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px;
}}
.badge-Basic {{ background: var(--yellow); color: var(--bg-input); }}
.badge-Good {{ background: var(--green); color: var(--bg-input); }}
.badge-Better {{ background: var(--accent); color: var(--bg-input); }}
.badge-Best {{ background: var(--mauve); color: var(--bg-input); }}
.installed-tag {{ color: var(--green); font-size: 12px; margin-left: 8px; }}

.btn-row {{ display: flex; justify-content: space-between; margin-top: 32px; }}
.btn {{
  padding: 12px 28px; border-radius: 8px; border: none;
  font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s;
}}
.btn-primary {{
  background: var(--accent); color: var(--bg-input);
}}
.btn-primary:hover {{ background: var(--mauve); }}
.btn-secondary {{
  background: var(--bg-hover); color: var(--fg-sub);
}}
.btn-secondary:hover {{ background: var(--accent-dim); }}

/* Progress */
.progress-wrap {{ margin: 24px 0 16px; }}
.progress-bar {{
  width: 100%; height: 12px; background: var(--bg-input);
  border-radius: 6px; overflow: hidden;
}}
.progress-fill {{
  height: 100%; background: linear-gradient(90deg, var(--accent), var(--mauve));
  border-radius: 6px; transition: width 0.3s ease; width: 0%;
}}
.progress-stats {{
  display: flex; justify-content: space-between;
  color: var(--fg-dim); font-size: 12px; margin-top: 6px;
}}
.log-box {{
  background: var(--bg-input); border-radius: 8px;
  padding: 14px 16px; margin-top: 16px; max-height: 200px;
  overflow-y: auto; font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12px; line-height: 1.8;
}}
.log-ok {{ color: var(--green); }}
.log-err {{ color: var(--red); }}
.log-dim {{ color: var(--fg-dim); }}

/* Finish */
.check-item {{
  display: flex; align-items: center; gap: 10px;
  padding: 6px 0; font-size: 15px;
}}
.check-item .icon {{ font-size: 18px; }}
.check-ok {{ color: var(--green); }}
.check-warn {{ color: var(--yellow); }}

.code-examples {{ margin-top: 16px; }}
.code-row {{
  display: flex; gap: 16px; padding: 5px 0; font-size: 13px;
}}
.code-cmd {{
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  color: var(--accent); white-space: nowrap;
}}
.code-desc {{ color: var(--fg-dim); }}
</style>
</head>
<body>
<div class="wizard">

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

  <!-- Step 1: Model selection -->
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
    <div class="btn-row" style="justify-content:flex-end">
      <button class="btn btn-primary" onclick="fetch('/api/shutdown');window.close();">Close</button>
    </div>
  </div>
</div>

<script>
const MODELS = {models_json};
let selectedModel = 0;
let pollTimer = null;

function showStep(n) {{
  document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
  document.getElementById('step-' + n).classList.add('active');
}}

// Build model cards
(function() {{
  const list = document.getElementById('model-list');
  MODELS.forEach((m, i) => {{
    const card = document.createElement('div');
    card.className = 'model-card' + (i === 0 ? ' selected' : '');
    card.onclick = () => {{
      selectedModel = i;
      document.querySelectorAll('.model-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
    }};
    const installed = m.installed ? '<span class="installed-tag">✓ installed</span>' : '';
    card.innerHTML = `
      <div class="top">
        <span class="name">${{m.name}}${{installed}}</span>
        <span class="badge badge-${{m.quality}}">${{m.quality}}</span>
      </div>
      <div class="meta">${{m.size_gb}} GB · ${{m.params}} params · min ${{m.min_ram}} RAM — ${{m.description}}</div>
    `;
    list.appendChild(card);
  }});
  // Skip option
  const skip = document.createElement('div');
  skip.className = 'model-card';
  skip.onclick = () => {{
    selectedModel = -1;
    document.querySelectorAll('.model-card').forEach(c => c.classList.remove('selected'));
    skip.classList.add('selected');
  }};
  skip.innerHTML = '<div class="name">Skip — no AI model (rule-based fallback only)</div><div class="meta">No download required</div>';
  list.appendChild(skip);
}})();

function startInstall() {{
  showStep(2);
  fetch('/api/install', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ model_idx: selectedModel }})
  }});
  pollTimer = setInterval(pollProgress, 400);
}}

function pollProgress() {{
  fetch('/api/progress').then(r => r.json()).then(s => {{
    document.getElementById('progress-fill').style.width = s.pct + '%';
    document.getElementById('progress-pct').textContent =
      s.total_mb > 0 ? s.downloaded_mb.toFixed(0) + ' / ' + s.total_mb.toFixed(0) + ' MB  (' + s.pct.toFixed(0) + '%)' : '';
    document.getElementById('progress-speed').textContent =
      s.speed ? s.speed + '   ' + s.eta : '';
    if (s.status) document.getElementById('install-status').textContent = s.status;
    if (s.title) document.getElementById('install-title').textContent = s.title;

    const box = document.getElementById('log-box');
    if (s.logs && s.logs.length > box.children.length) {{
      for (let i = box.children.length; i < s.logs.length; i++) {{
        const div = document.createElement('div');
        div.className = 'log-' + s.logs[i].level;
        const prefix = s.logs[i].level === 'ok' ? '✓ ' : s.logs[i].level === 'err' ? '✗ ' : '  ';
        div.textContent = prefix + s.logs[i].msg;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
      }}
    }}

    if (s.done) {{
      clearInterval(pollTimer);
      setTimeout(() => showFinish(s), 500);
    }}
    if (s.error) {{
      clearInterval(pollTimer);
      document.getElementById('install-title').textContent = 'Installation failed';
      document.getElementById('install-status').textContent = s.error;
    }}
  }});
}}

function showFinish(s) {{
  const checks = document.getElementById('finish-checks');
  checks.innerHTML = '';
  (s.checks || []).forEach(c => {{
    const cls = c.ok ? 'check-ok' : 'check-warn';
    const icon = c.ok ? '✓' : '○';
    checks.innerHTML += '<div class="check-item ' + cls + '"><span class="icon">' + icon + '</span> ' + c.label + '</div>';
  }});
  showStep(3);
}}

// Heartbeat — tells the server the browser tab is still open
setInterval(() => fetch('/api/heartbeat').catch(() => {{}}), 2000);

// Shut down the server cleanly when the tab/window closes
window.addEventListener('beforeunload', () => {{
  navigator.sendBeacon('/api/shutdown');
}});
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
        elif self.path == "/api/shutdown":
            self._respond(200, "text/plain", b"bye")
            threading.Thread(target=self._shutdown, daemon=True).start()
        else:
            self._respond(404, "text/plain", b"not found")

    def do_POST(self) -> None:
        if self.path == "/api/install":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            model_idx = body.get("model_idx", -1)
            self._respond(200, "application/json", b'{"ok":true}')
            threading.Thread(target=_run_install, args=(model_idx,), daemon=True).start()
        elif self.path == "/api/shutdown":
            self._respond(200, "text/plain", b"bye")
            threading.Thread(target=self._shutdown, daemon=True).start()
        else:
            self._respond(404, "text/plain", b"not found")

    def _respond(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _shutdown(self) -> None:
        time.sleep(0.3)
        if self.server_ref:
            self.server_ref.shutdown()

    def log_message(self, format, *args) -> None:
        pass  # silence request logs


# -- Installation logic -------------------------------------------------------

def _run_install(model_idx: int) -> None:
    _download_state.update(
        active=True, cancelled=False, pct=0, downloaded_mb=0,
        total_mb=0, speed="", eta="", done=False, error="",
        logs=[], title="Installing binary...", status="Copying to PATH",
        checks=[],
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

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "termai/0.1"})
        resp = urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        _log(f"Download failed: {e}", "err")
        raise

    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 256 * 1024
    start_time = time.monotonic()

    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                _update_progress(downloaded, total, start_time)

        tmp.rename(dest)
        _download_state["pct"] = 100
        _log(f"Model saved to {dest}", "ok")

    except Exception:
        tmp.unlink(missing_ok=True)
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

    _download_state.update(
        pct=round(pct, 1),
        downloaded_mb=round(downloaded / 1e6, 1),
        total_mb=round(total / 1e6, 1),
        speed=speed,
        eta=eta,
    )


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


# -- Entry point --------------------------------------------------------------

def _heartbeat_watchdog(server: HTTPServer, handler_cls: type) -> None:
    """Shut down the server if no heartbeat is received for 8 seconds."""
    while True:
        time.sleep(3)
        last = handler_cls.last_heartbeat
        if last > 0 and (time.monotonic() - last) > 8:
            print("[termai] Browser disconnected — shutting down.")
            server.shutdown()
            return


def run_gui_wizard() -> None:
    """Launch the browser-based wizard on a random local port."""
    page = _build_html()

    handler = type("Handler", (_WizardHandler,), {
        "html_page": page,
        "last_heartbeat": time.monotonic(),
    })
    server = HTTPServer(("127.0.0.1", 0), handler)
    handler.server_ref = server
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"

    threading.Thread(target=_heartbeat_watchdog, args=(server, handler), daemon=True).start()

    print(f"[termai] Opening setup wizard at {url}")
    webbrowser.open(url)
    server.serve_forever()
    print("[termai] Wizard closed.")
