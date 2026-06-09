"""
code-sandbox MCP server
========================
Provides tools for the LLM to execute Python code safely in an isolated
subprocess sandbox. All execution is time-limited and resource-capped.

Tools exposed:
  - run_python       : execute a Python snippet, returns stdout + stderr
  - run_python_async : fire-and-forget background job; poll with job_status
  - job_status       : check status / output of a background job
  - job_list         : list all tracked background jobs
  - job_kill         : kill a running background job
  - install_package  : pip-install a package into the sandbox venv
  - sandbox_info     : show Python version, installed packages, resource limits
"""

import os
import sys
import json
import uuid
import time
import shlex
import resource
import subprocess
import threading
from pathlib import Path
from typing import Dict, Optional

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SANDBOX_DIR = Path(os.getenv("SANDBOX_DIR", "./sandbox_data")).resolve()
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

# Limits
MAX_CPU_SECONDS: int = int(os.getenv("SANDBOX_CPU_SECS", "30"))
MAX_OUTPUT_BYTES: int = int(os.getenv("SANDBOX_MAX_OUTPUT", str(256 * 1024)))  # 256 KB
MAX_JOBS: int = int(os.getenv("SANDBOX_MAX_JOBS", "20"))

PORT = int(os.getenv("SANDBOX_PORT", "8098"))

# In-memory job registry  {job_id -> Job}
_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()

mcp = FastMCP("code-sandbox", host="0.0.0.0", port=PORT)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _python_exe() -> str:
    """Return the Python interpreter to use inside the sandbox."""
    return sys.executable


def _set_limits():
    """Called in child process (POSIX only) to cap CPU + address space."""
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS))
        # 512 MB address space limit
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    except Exception:
        pass  # non-POSIX or unprivileged – best effort


def _run_code_sync(code: str, timeout: int) -> dict:
    """Execute *code* synchronously; return result dict."""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    # Restrict network in the child by unsetting proxy env vars (best effort)
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)

    try:
        proc = subprocess.run(
            [_python_exe(), "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(SANDBOX_DIR),
            env=env,
            preexec_fn=_set_limits,
        )
        stdout = proc.stdout[:MAX_OUTPUT_BYTES]
        stderr = proc.stderr[:MAX_OUTPUT_BYTES]
        return {
            "status": "done",
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"[sandbox] process killed after {timeout}s CPU timeout",
        }
    except Exception as exc:
        return {
            "status": "error",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"[sandbox] internal error: {exc}",
        }


def _background_worker(job_id: str, code: str, timeout: int):
    """Thread target: run code and write result back to _jobs."""
    result = _run_code_sync(code, timeout)
    result["finished_at"] = time.time()
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(result)


def _prune_old_jobs():
    """Drop oldest jobs when registry exceeds MAX_JOBS."""
    with _jobs_lock:
        if len(_jobs) > MAX_JOBS:
            oldest = sorted(_jobs.keys(), key=lambda k: _jobs[k]["created_at"])
            for jid in oldest[: len(_jobs) - MAX_JOBS]:
                del _jobs[jid]


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def run_python(code: str, timeout: int = 30) -> str:
    """
    Execute a Python code snippet synchronously in an isolated sandbox.

    Args:
        code: Python source code to run.
        timeout: Max wall-clock seconds to allow (default 30, max 120).

    Returns:
        JSON string with keys: status, exit_code, stdout, stderr.
    """
    timeout = min(max(1, timeout), 120)
    result = _run_code_sync(code, timeout)
    return json.dumps(result, indent=2)


@mcp.tool()
def run_python_async(code: str, timeout: int = 60) -> str:
    """
    Submit a Python snippet to run in the background (non-blocking).

    Args:
        code: Python source code to run.
        timeout: Max seconds before the job is killed (default 60, max 300).

    Returns:
        JSON with job_id — use job_status(job_id) to poll for results.
    """
    timeout = min(max(1, timeout), 300)
    _prune_old_jobs()

    job_id = str(uuid.uuid4())[:8]
    job = {
        "job_id": job_id,
        "status": "running",
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "created_at": time.time(),
        "finished_at": None,
        "code_preview": code[:200],
    }

    with _jobs_lock:
        _jobs[job_id] = job

    t = threading.Thread(target=_background_worker, args=(job_id, code, timeout), daemon=True)
    t.start()

    return json.dumps({"job_id": job_id, "status": "running"})


@mcp.tool()
def job_status(job_id: str) -> str:
    """
    Check the status of a background Python job.

    Args:
        job_id: ID returned by run_python_async.

    Returns:
        JSON with status, exit_code, stdout, stderr, elapsed seconds.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        return json.dumps({"error": f"Job '{job_id}' not found"})

    now = time.time()
    elapsed = round(now - job["created_at"], 2)
    finished = job.get("finished_at")
    run_time = round(finished - job["created_at"], 2) if finished else elapsed

    return json.dumps({
        "job_id": job_id,
        "status": job["status"],
        "exit_code": job["exit_code"],
        "stdout": job["stdout"],
        "stderr": job["stderr"],
        "elapsed_seconds": run_time,
    }, indent=2)


@mcp.tool()
def job_list() -> str:
    """
    List all tracked background jobs with their current status.

    Returns:
        JSON array of job summaries.
    """
    with _jobs_lock:
        jobs = list(_jobs.values())

    now = time.time()
    summary = []
    for j in sorted(jobs, key=lambda x: x["created_at"], reverse=True):
        summary.append({
            "job_id": j["job_id"],
            "status": j["status"],
            "exit_code": j["exit_code"],
            "elapsed": round(now - j["created_at"], 1),
            "code_preview": j.get("code_preview", ""),
        })
    return json.dumps(summary, indent=2)


@mcp.tool()
def job_kill(job_id: str) -> str:
    """
    Attempt to mark a running job as cancelled.
    Note: the underlying subprocess may still complete naturally;
    Python threads cannot be forcibly terminated from the outside.

    Args:
        job_id: ID of the job to cancel.

    Returns:
        Confirmation message.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return json.dumps({"error": f"Job '{job_id}' not found"})
        if job["status"] == "running":
            job["status"] = "cancelled"
            job["stderr"] += "\n[sandbox] job marked cancelled by user"
    return json.dumps({"job_id": job_id, "status": "cancelled"})


@mcp.tool()
def install_package(package: str) -> str:
    """
    Install a Python package into the sandbox environment using pip.

    Args:
        package: Package name (e.g. 'numpy', 'pandas==2.2.0').

    Returns:
        pip output or error message.
    """
    # Basic safety check — reject shell metacharacters
    if any(c in package for c in (";", "&", "|", "`", "$", "\n", ">")):
        return json.dumps({"error": "Invalid package name"})

    try:
        result = subprocess.run(
            [_python_exe(), "-m", "pip", "install", "--quiet", package],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return json.dumps({
            "status": "ok" if result.returncode == 0 else "error",
            "stdout": result.stdout[:10_000],
            "stderr": result.stderr[:10_000],
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "pip install timed out after 120 s"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def sandbox_info() -> str:
    """
    Return sandbox environment info: Python version, installed packages,
    resource limits, and working directory.
    """
    try:
        pkgs_out = subprocess.check_output(
            [_python_exe(), "-m", "pip", "list", "--format=columns"],
            text=True, timeout=10,
        )
    except Exception:
        pkgs_out = "(could not retrieve)"

    cpu_lim, _ = resource.getrlimit(resource.RLIMIT_CPU)

    return json.dumps({
        "python_version": sys.version,
        "sandbox_dir": str(SANDBOX_DIR),
        "cpu_limit_seconds": MAX_CPU_SECONDS,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "max_jobs": MAX_JOBS,
        "installed_packages": pkgs_out[:5_000],
    }, indent=2)


# ---------------------------------------------------------------------------
# /help HTML endpoint
# ---------------------------------------------------------------------------

def help_handler(request: Request) -> HTMLResponse:
    raw_tools = list(mcp._tool_manager._tools.values())
    rows = ""
    for t in raw_tools:
        schema = getattr(t, "parameters", None) or {}
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        params = " ".join(
            f'<code class="param{" req" if k in required else ""}">{k}</code>'
            for k in props
        )
        rows += (
            f"<tr>"
            f"<td><b>{t.name}</b></td>"
            f"<td>{t.description or '<em>—</em>'}</td>"
            f"<td>{params or '<em>none</em>'}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Code Sandbox MCP — Tools</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:2rem}}
    h1{{color:#3fb950;margin-bottom:.25rem;font-size:1.6rem}}
    p.sub{{color:#8b949e;margin-bottom:1.5rem;font-size:.9rem}}
    table{{width:100%;border-collapse:collapse;font-size:.9rem}}
    th{{background:#161b22;color:#8b949e;text-transform:uppercase;font-size:.75rem;
        letter-spacing:.05em;padding:.6rem 1rem;text-align:left;border-bottom:1px solid #30363d}}
    td{{padding:.65rem 1rem;border-bottom:1px solid #21262d;vertical-align:top}}
    tr:hover td{{background:#161b22}}
    b{{color:#e6edf3}}
    code.param{{background:#21262d;padding:.15em .4em;border-radius:4px;font-size:.82em;
               color:#79c0ff;margin-right:.25em}}
    code.param.req{{color:#ffa657}}
    em{{color:#6e7681}}
    .badge{{display:inline-block;background:#238636aa;color:#3fb950;border:1px solid #2ea043;
            border-radius:12px;padding:.1rem .6rem;font-size:.75rem;margin-left:.5rem}}
    .note{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem;
           margin-bottom:1.5rem;font-size:.85rem;color:#8b949e;line-height:1.6}}
    .note strong{{color:#c9d1d9}}
  </style>
</head>
<body>
  <h1>Code Sandbox MCP <span class="badge">{len(raw_tools)} tools</span></h1>
  <p class="sub">Python code execution in an isolated subprocess sandbox.</p>
  <div class="note">
    <strong>Limits:</strong>
    CPU cap: <strong>{MAX_CPU_SECONDS}s</strong> &nbsp;·&nbsp;
    Max output: <strong>{MAX_OUTPUT_BYTES // 1024} KB</strong> &nbsp;·&nbsp;
    Max concurrent jobs: <strong>{MAX_JOBS}</strong>
  </div>
  <table>
    <thead><tr><th>Tool</th><th>Description</th><th>Parameters</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    import uvicorn
    from starlette.requests import Request
    from starlette.middleware.cors import CORSMiddleware

    _sse  = mcp.sse_app()              # /sse + /messages/  (LibreChat)
    _http = mcp.streamable_http_app() # /mcp               (llama-ui, Cursor, …)

    class MultiTransport:
        """
        Custom ASGI dispatcher:
          /mcp*  → streamable-HTTP (llama-ui)   – prefix NOT stripped
          /help  → HTML tool listing
          else   → SSE (/sse, /messages/)        (LibreChat)

        Both app lifespans are run concurrently so each transport's session
        manager is properly initialised before requests arrive.
        """

        async def _lifespan(self, scope, receive, send):
            """Fan startup/shutdown events to both apps via asyncio queues."""
            startup = await receive()          # lifespan.startup

            sse_q, http_q = asyncio.Queue(), asyncio.Queue()
            await sse_q.put(startup)
            await http_q.put(startup)

            sse_ready  = asyncio.Event()
            http_ready = asyncio.Event()

            async def _run(app, q, ready_evt):
                async def _recv():        return await q.get()
                async def _send(msg):
                    if "startup" in msg.get("type", ""):
                        ready_evt.set()
                await app(scope, _recv, _send)

            sse_task  = asyncio.create_task(_run(_sse,  sse_q,  sse_ready))
            http_task = asyncio.create_task(_run(_http, http_q, http_ready))

            await asyncio.gather(sse_ready.wait(), http_ready.wait())
            await send({"type": "lifespan.startup.complete"})

            shutdown = await receive()         # lifespan.shutdown
            await sse_q.put(shutdown)
            await http_q.put(shutdown)
            await asyncio.gather(sse_task, http_task, return_exceptions=True)
            await send({"type": "lifespan.shutdown.complete"})

        async def __call__(self, scope, receive, send):
            if scope["type"] == "lifespan":
                await self._lifespan(scope, receive, send)
                return
            path = scope.get("path", "/")
            if path == "/help":
                resp = help_handler(Request(scope, receive))
                await resp(scope, receive, send)
            elif path.startswith("/mcp"):
                await _http(scope, receive, send)
            else:
                await _sse(scope, receive, send)

    # CORS required for browser-based clients (llama-ui at :8099 → :8098)
    # expose_headers lets JS read Mcp-Session-Id from the initialize response
    # so it can include it in subsequent requests (without it → 400 Missing session ID)
    app = CORSMiddleware(
        MultiTransport(),
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
