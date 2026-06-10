# LibreChat + Llama.cpp Stack

## Quick Start

Compose / start all services:
```bash
docker compose up -d
```

Restart and rebuild all services:
```bash
docker compose down && docker compose up -d --build
```

---

## Exposed Ports

| Port | Service | URL | Description |
|------|---------|-----|-------------|
| **3080** | `librechat` | http://localhost:3080 | LibreChat web UI — the main chat front-end. |
| **8096** | `docs-mcp` | http://localhost:8096/sse | Docs MCP server — PDF reading and DOCX read/write (`/mcp`, `/sse`, `/help`). |
| **8097** | `office-mcp` | http://localhost:8097/sse | Office MCP server — file system, SQLite, web fetch, calculator, ChromaDB (`/mcp`, `/sse`, `/help`). |
| **8098** | `code-sandbox` | http://localhost:8098/sse | Code Sandbox MCP server — secure, resource-limited Python execution (`/mcp`, `/sse`, `/help`). |
| **8099** | `llama-server` | http://localhost:8099 | Llama.cpp inference server (CUDA) — serves Gemma-4 12B over the OpenAI-compatible API. |

> **Note:** MongoDB (`27017`) and Meilisearch (`7700`) are **not** exposed to the host; they are only reachable within the Docker network.

---

## MCP Servers

All three MCP servers support **both** transports:

| Transport | Path | Use with |
|-----------|------|----------|
| Streamable HTTP | `/mcp` | llama-ui, Cursor, Claude Desktop, VS Code |
| SSE (legacy) | `/sse` | LibreChat, older MCP clients |

See [`mcp/README.md`](mcp/README.md) for full tool listings and client connection guides.

---

## Model Used

```
https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf/tree/main
```

---

## Setup MCP Server (local / manual)

```bash
cd mcp/office-mcp
python -m venv venv && source venv/bin/activate # Windows: venv\Scripts\activate
pip install "mcp[cli]" requests chromadb playwright beautifulsoup4
playwright install chromium # only if you want the browser tool
mkdir data
```

### How to Run an MCP Server Manually

```bash
cd mcp/office-mcp
source venv/bin/activate
python server.py
```

Available at `http://localhost:8097/sse` (SSE) and `http://localhost:8097/mcp` (Streamable HTTP).
