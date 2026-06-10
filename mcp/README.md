# MCP Servers

Three plug-and-play MCP servers that any AI client can connect to.  
All servers expose **two transports** so they work with any client:

| Transport | Path | Use with |
|-----------|------|----------|
| Streamable HTTP | `/mcp` | llama-ui, Cursor, Claude Desktop, VS Code |
| SSE (legacy) | `/sse` | LibreChat, older MCP clients |

---

## Servers

### 1. `office-mcp` — Port `8097`

General-purpose office tools for the LLM.

| Tool | Description |
|------|-------------|
| `fs_list` | List files in a directory |
| `fs_read` | Read a text file |
| `fs_write` | Write a text file |
| `sqlite_query` | Run SELECT / INSERT / UPDATE on a local SQLite DB |
| `sqlite_tables` | List tables in the DB |
| `fetch_url` | Fetch a URL and return plain text / markdown |
| `calculator` | Safe math expression evaluator |
| `git_status` | `git status` for a repo |
| `git_log` | `git log` for a repo |
| `everything_search` | Recursive filename search |
| `chroma_add` | Add documents to a local ChromaDB collection |
| `chroma_query` | Semantic search over a ChromaDB collection |
| `browser_screenshot` | Take a full-page screenshot (requires Playwright) |

**Endpoints:**
- Streamable HTTP → `http://localhost:8097/mcp`
- SSE            → `http://localhost:8097/sse`
- Help page      → `http://localhost:8097/help`

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_BASE_DIR` | `./data` | Root directory all file tools are sandboxed to |
| `MCP_SQLITE_PATH` | `./data/office.db` | SQLite database path |
| `MCP_CHROMA_PATH` | `./data/chroma` | ChromaDB persistence path |

---

### 2. `code-sandbox` — Port `8098`

Secure, resource-capped Python code execution.

| Tool | Description |
|------|-------------|
| `run_python` | Execute Python synchronously, returns stdout + stderr |
| `run_python_async` | Fire-and-forget background job |
| `job_status` | Poll status / output of a background job |
| `job_list` | List all tracked jobs |
| `job_kill` | Cancel a running job |
| `install_package` | `pip install` a package into the sandbox |
| `sandbox_info` | Python version, installed packages, resource limits |

**Endpoints:**
- Streamable HTTP → `http://localhost:8098/mcp`
- SSE            → `http://localhost:8098/sse`
- Help page      → `http://localhost:8098/help`

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_DIR` | `./sandbox_data` | Working directory for executed code |
| `SANDBOX_CPU_SECS` | `30` | Max CPU seconds per execution |
| `SANDBOX_MAX_OUTPUT` | `262144` | Max output bytes (256 KB) |
| `SANDBOX_MAX_JOBS` | `20` | Max concurrent background jobs |
| `SANDBOX_PORT` | `8098` | Port to listen on |

---

### 3. `docs-mcp` — Port `8096`

PDF reading and DOCX read/write for the LLM.

| Tool | Description |
|------|-------------|
| `pdf_read` | Extract text from a PDF (full doc or page range, with optional table extraction) |
| `pdf_info` | Return metadata + structure info (title, author, page count, sizes, encryption) |
| `docx_read` | Read a `.docx` file and return clean Markdown |
| `docx_write` | Create or overwrite a `.docx` file from Markdown content |

**Endpoints:**
- Streamable HTTP → `http://localhost:8096/mcp`
- SSE            → `http://localhost:8096/sse`
- Help page      → `http://localhost:8096/help`

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCS_MCP_PORT` | `8096` | Port to listen on |

---

## Quick Start

### Option A — Run all servers (standalone, no LibreChat needed)

```bash
cd mcp/
docker compose up -d --build
```

### Option B — Run as part of the full LibreChat stack

```bash
# from the repo root
docker compose up -d --build
```

---

## Connecting Your Client

### llama-ui (llama.cpp built-in web UI)

In **MCP Servers** settings, add:
```
http://localhost:8097/mcp   ← office-mcp
http://localhost:8098/mcp   ← code-sandbox
http://localhost:8096/mcp   ← docs-mcp
```

### LibreChat (`librechat.yaml`)

```yaml
mcpServers:
  office-tools:
    type: sse
    url: "http://office-mcp:8097/sse"   # use Docker service name if in same compose
  code-sandbox:
    type: sse
    url: "http://code-sandbox:8098/sse"
  docs-mcp:
    type: sse
    url: "http://docs-mcp:8096/sse"
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "office-mcp": {
      "url": "http://localhost:8097/mcp"
    },
    "code-sandbox": {
      "url": "http://localhost:8098/mcp"
    },
    "docs-mcp": {
      "url": "http://localhost:8096/mcp"
    }
  }
}
```

### Cursor / VS Code (MCP extension)

```json
{
  "mcpServers": {
    "office-mcp":   { "url": "http://localhost:8097/mcp" },
    "code-sandbox": { "url": "http://localhost:8098/mcp" },
    "docs-mcp":     { "url": "http://localhost:8096/mcp" }
  }
}
```

---

## Data Persistence

| Volume | Contents |
|--------|----------|
| `office_mcp_data` | SQLite DB, ChromaDB index, files written by the LLM |
| `code_sandbox_data` | Files written during Python code execution |
| `docs_data` | Files written by `docx_write` |

To reset all data: `docker compose down -v`
