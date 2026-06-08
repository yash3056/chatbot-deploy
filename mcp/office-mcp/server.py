import os, sqlite3, subprocess, math, json
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup
import chromadb

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

# --- config ---
BASE_DIR = Path(os.getenv("MCP_BASE_DIR", "./data")).resolve()
DB_PATH = os.getenv("MCP_SQLITE_PATH", "./data/office.db")
CHROMA_PATH = os.getenv("MCP_CHROMA_PATH", "./data/chroma")

BASE_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("office-tools", host="0.0.0.0", port=8097)

# --- helpers ---
def _safe_path(p: str) -> Path:
    target = (BASE_DIR / p).resolve()
    if not str(target).startswith(str(BASE_DIR)):
        raise ValueError("Access outside BASE_DIR denied")
    return target

# --- 1. Filesystem ---
@mcp.tool()
def fs_list(path: str = ".") -> List[str]:
    """List files in a directory relative to BASE_DIR"""
    p = _safe_path(path)
    return sorted([x.name + ("/" if x.is_dir() else "") for x in p.iterdir()])

@mcp.tool()
def fs_read(path: str) -> str:
    """Read a text file"""
    p = _safe_path(path)
    return p.read_text(encoding="utf-8", errors="ignore")[:200_000]

@mcp.tool()
def fs_write(path: str, content: str) -> str:
    """Write text file (creates dirs)"""
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"

# --- 2. SQLite ---
@mcp.tool()
def sqlite_query(sql: str, params: str = "[]") -> str:
    """Run SELECT/INSERT/UPDATE on local SQLite DB"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(sql, json.loads(params))
        if sql.strip().lower().startswith("select"):
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description or []]
            return json.dumps({"columns": cols, "rows": rows[:500]})
        conn.commit()
        return f"OK, {cur.rowcount} rows affected"
    finally:
        conn.close()

@mcp.tool()
def sqlite_tables() -> List[str]:
    """List tables in DB"""
    conn = sqlite3.connect(DB_PATH)
    try:
        return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    finally:
        conn.close()

# --- 3. Fetch ---
@mcp.tool()
def fetch_url(url: str) -> str:
    """Fetch a URL and return text/markdown (no API key)"""
    r = requests.get(url, timeout=15, headers={"User-Agent": "office-mcp/1.0"})
    r.raise_for_status()
    if "html" in r.headers.get("content-type", ""):
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text("\n", strip=True)[:100_000]
    return r.text[:100_000]

# --- 4. Calculator ---
@mcp.tool()
def calculator(expr: str) -> str:
    """Safe math eval"""
    allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed.update({"abs": abs, "round": round})
    return str(eval(expr, {"__builtins__": {}}, allowed))

# --- 5. Git ---
@mcp.tool()
def git_status(repo: str = ".") -> str:
    """git status for a repo under BASE_DIR"""
    p = _safe_path(repo)
    return subprocess.check_output(["git", "-C", str(p), "status", "--short"], text=True)

@mcp.tool()
def git_log(repo: str = ".", n: int = 10) -> str:
    p = _safe_path(repo)
    return subprocess.check_output(["git", "-C", str(p), "log", f"-{n}", "--oneline"], text=True)

# --- 6. Everything search ---
@mcp.tool()
def everything_search(name: str, path: str = ".") -> List[str]:
    """Simple recursive filename search"""
    p = _safe_path(path)
    matches = []
    for root, _, files in os.walk(p):
        for f in files:
            if name.lower() in f.lower():
                matches.append(str(Path(root, f).relative_to(BASE_DIR)))
                if len(matches) >= 100: return matches
    return matches

# --- 7. Chroma (local vector search) ---
_chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
@mcp.tool()
def chroma_add(collection: str, documents: List[str], ids: List[str]):
    """Add docs to local Chroma collection"""
    col = _chroma_client.get_or_create_collection(collection)
    col.add(documents=documents, ids=ids)
    return f"Added {len(ids)} docs"

@mcp.tool()
def chroma_query(collection: str, query: str, n: int = 5) -> str:
    """Query local Chroma"""
    col = _chroma_client.get_or_create_collection(collection)
    res = col.query(query_texts=[query], n_results=n)
    return json.dumps(res, default=str)

# --- 8. Browser screenshot (optional) ---
@mcp.tool()
def browser_screenshot(url: str) -> str:
    """Take screenshot, returns path"""
    from playwright.sync_api import sync_playwright
    out = BASE_DIR / "screenshot.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, timeout=15000)
        page.screenshot(path=str(out), full_page=True)
        browser.close()
    return str(out.relative_to(BASE_DIR))

# --- /help endpoint — lists all registered MCP tools ---
def help_handler(request: Request) -> HTMLResponse:
    # Access tool registry directly from the internal tool manager (sync, no MCP protocol needed)
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
  <title>Office MCP — Tools</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;padding:2rem}}
    h1{{color:#58a6ff;margin-bottom:.25rem;font-size:1.6rem}}
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
    .badge{{display:inline-block;background:#388bfd22;color:#58a6ff;border:1px solid #1f6feb;
            border-radius:12px;padding:.1rem .6rem;font-size:.75rem;margin-left:.5rem}}
  </style>
</head>
<body>
  <h1>Office MCP Tools <span class="badge">{len(raw_tools)} tools</span></h1>
  <p class="sub">Parameters in <code style="color:#ffa657;background:#21262d;padding:.1em .3em;border-radius:3px">orange</code> are required.</p>
  <table>
    <thead><tr><th>Tool</th><th>Description</th><th>Parameters</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount

    # mcp.sse_app() returns the internal Starlette app used by mcp.run(transport="sse").
    # We wrap it with our own Starlette app that adds /help before the catch-all mount.
    sse_starlette = mcp.sse_app()

    combined = Starlette(routes=[
        Route("/help", endpoint=help_handler),
        Mount("/", app=sse_starlette),
    ])

    uvicorn.run(combined, host="0.0.0.0", port=8097, log_level="info")
