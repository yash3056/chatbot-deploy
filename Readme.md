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
| **3080** | `librechat` | http://localhost:3080 | LibreChat web UI — the main chat front-end that users interact with. |
| **8097** | `office-mcp` | http://localhost:8097/sse | Office MCP tool server — provides an SSE endpoint for document/office-related tools (file reading, ChromaDB search, SQLite). |
| **8098** | `code-sandbox` | http://localhost:8098/sse | Code Sandbox MCP server — provides a secure, resource-limited Python execution environment via an SSE endpoint. |
| **8099** | `llama-server` | http://localhost:8099 | Llama.cpp inference server (CUDA) — serves the Gemma-4 12B model over the OpenAI-compatible HTTP API. |

> **Note:** MongoDB (`27017`) and Meilisearch (`7700`) are **not** exposed to the host; they are only reachable within the Docker network.

---

## Model Used

```
https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf/tree/main
```

---

## Setup MCP Server (local / manual)

```bash
mkdir office-mcp && cd office-mcp
python -m venv venv && source venv/bin/activate # Windows: .venv\Scripts\activate
pip install "mcp[cli]" requests chromadb playwright beautifulsoup4
playwright install chromium # only if you want the browser tool
mkdir data
```

### How to Run the MCP Server Manually

```bash
cd /**/*/llama-cpp/office-mcp
source venv/bin/activate

# Option A — simplest, runs in stdio (what LibreChat needs):
python server.py

# Option B — dev inspector with hot reload:
mcp dev server.py
```
