# Docs MCP Server

A dedicated MCP server for reading PDFs and reading/writing Word documents.

## Tools

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `pdf_read` | Extract text (+ tables) from a PDF | `path`, `pages`, `extract_tables`, `combine` |
| `pdf_info` | Metadata, page count, page sizes | `path` |
| `docx_read` | Read `.docx` → clean Markdown | `path`, `include_messages` |
| `docx_write` | Write Markdown → `.docx` | `path`, `content`, `title`, `author`, `page_size` |

---

## Quick start

### Python (direct)
```bash
pip install -r requirements.txt
python server.py
```

### Docker
```bash
docker build -t docs-mcp .
docker run --rm -i -v /your/docs:/docs docs-mcp
```

### Add to docker-compose.yml
```yaml
docs-mcp:
  build: ./docs-mcp
  container_name: docs-mcp
  stdin_open: true
  tty: true
  volumes:
    - /home/yash/office:/office   # mount your documents directory
  restart: unless-stopped
```

---

## MCP client config

```json
{
  "mcpServers": {
    "docs": {
      "command": "python",
      "args": ["/absolute/path/to/docs-mcp/server.py"]
    }
  }
}
```

Or with Docker (mounts your docs folder):
```json
{
  "mcpServers": {
    "docs": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-v", "/home/yash/office:/office", "docs-mcp"]
    }
  }
}
```

---

## Usage examples

### pdf_read — all pages
```json
{ "path": "/office/report.pdf" }
```

### pdf_read — page range + tables
```json
{
  "path": "/office/report.pdf",
  "pages": "1-3,7",
  "extract_tables": true
}
```

### pdf_info
```json
{ "path": "/office/report.pdf" }
```
Returns:
```json
{
  "page_count": 12,
  "encrypted": false,
  "metadata": { "title": "Q3 Report", "author": "Yash", ... },
  "unique_page_sizes": [{ "width_in": 8.5, "height_in": 11.0 }]
}
```

### docx_read
```json
{ "path": "/office/notes.docx" }
```
Returns clean Markdown with headings, bold, italic, lists, and tables preserved.

### docx_write
```json
{
  "path": "/office/output.docx",
  "title": "Meeting Notes",
  "author": "Yash",
  "page_size": "A4",
  "content": "# Meeting Notes\n\n## Agenda\n\n- Item 1\n- Item 2\n\n## Summary\n\nThis was a **productive** meeting."
}
```

---

## Markdown supported by `docx_write`

| Syntax | Result |
|--------|--------|
| `# H1` … `###### H6` | Headings 1–6 |
| `**bold**` | Bold |
| `*italic*` | Italic |
| `***bold italic***` | Bold + Italic |
| `` `code` `` | Inline monospace |
| `[text](url)` | Hyperlink |
| `- item` / `* item` | Bullet list |
| `1. item` | Numbered list |
| `\`\`\`…\`\`\`` | Code block (Courier New 9pt) |
| `> quote` | Block quote with indent |
| `---` | Horizontal rule |
| Pipe tables | Word tables with bold header row |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `mcp` | MCP protocol |
| `pdfplumber` | PDF text + table extraction |
| `pypdf` | PDF metadata |
| `mammoth` | DOCX → Markdown conversion |
| `python-docx` | DOCX creation |
