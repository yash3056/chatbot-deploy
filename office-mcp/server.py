import os, sqlite3, subprocess, math, json
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup

# pip install chromadb
import chromadb

from mcp.server.fastmcp import FastMCP

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

if __name__ == "__main__":
    # SSE transport: exposes an HTTP endpoint so LibreChat (in another container)
    # can connect via http://office-mcp:8097/sse over the Docker bridge network.
    mcp.run(transport="sse")