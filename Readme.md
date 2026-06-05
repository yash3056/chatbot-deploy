to compose/start docker
```
docker compose up -d
```

restart the docker 
```
docker compose down && docker compose up -d
```

## Setup mcp server
```
mkdir office-mcp && cd office-mcp
python -m venv venv && source venv/bin/activate # Windows:.venv\Scripts\activate
pip install "mcp[cli]" requests chromadb playwright beautifulsoup4
playwright install chromium # only if you want browser tool
mkdir data
```

### How to run the mcp server

```
cd /**/*/llama-cpp/office-mcp
source venv/bin/activate

# Option A — simplest, runs in stdio (what LibreChat needs):
python server.py

# Option B — dev inspector with hot reload:
mcp dev server.py
```
