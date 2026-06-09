# Ngrok Setup — Exposing llama-ui Securely

## Goal

Expose llama-ui (port `8099`) to the internet via ngrok with:

| Client | Access |
|--------|--------|
| **Browser** | Requires username + password (HTTP Basic Auth prompt) |
| **curl / API clients** | No credentials needed — passes straight through |

This is achieved by putting an **nginx reverse proxy** between ngrok and the llama-server.  
nginx inspects the `User-Agent` header: `Mozilla/*` → enforce auth, everything else → allow.

```
Browser / curl
      │
      ▼
  ngrok (HTTPS tunnel)
      │
      ▼
  nginx :8100  ← User-Agent check here
      │
      ▼
  llama-server :8099
```

---

## Prerequisites

```bash
# Install nginx
sudo apt install -y nginx apache2-utils

# Install ngrok  (skip if already installed)
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install -y ngrok

# Authenticate ngrok with your token (one-time)
ngrok config add-authtoken <YOUR_NGROK_TOKEN>
```

---

## Step 1 — Create a Password File

```bash
# Replace 'youruser' and enter a password when prompted
sudo htpasswd -c /etc/nginx/.llama_htpasswd youruser
```

To add more users later (no `-c` flag):
```bash
sudo htpasswd /etc/nginx/.llama_htpasswd anotheruser
```

---

## Step 2 — Create the nginx Config

Create `/etc/nginx/sites-available/llama-proxy`:

```nginx
# Map User-Agent to auth requirement:
#   Browsers send "Mozilla/..." → require Basic Auth
#   curl, API clients, etc.    → no auth ("off")
map $http_user_agent $llama_auth {
    ~*Mozilla   "llama-ui";   # string shown in browser login dialog
    default     "off";        # disables auth for non-browser clients
}

server {
    listen 8100;              # nginx listens here; ngrok tunnels this port

    location / {
        auth_basic              $llama_auth;
        auth_basic_user_file    /etc/nginx/.llama_htpasswd;

        proxy_pass              http://127.0.0.1:8099;
        proxy_http_version      1.1;

        # Required for llama-ui WebSocket and streaming
        proxy_set_header        Upgrade           $http_upgrade;
        proxy_set_header        Connection        "upgrade";
        proxy_set_header        Host              $host;
        proxy_set_header        X-Real-IP         $remote_addr;
        proxy_set_header        X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header        X-Forwarded-Proto $scheme;

        proxy_read_timeout      300s;   # allow long-running inference streams
        proxy_send_timeout      300s;
    }
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/llama-proxy /etc/nginx/sites-enabled/
sudo nginx -t          # verify config
sudo systemctl reload nginx
```

---

## Step 3 — Start ngrok

```bash
ngrok http 8100
```

ngrok will print a public HTTPS URL like:
```
https://abc123.ngrok-free.app  →  http://localhost:8100
```

### Optional: persistent domain (ngrok paid plan)

```bash
ngrok http --domain=your-subdomain.ngrok.app 8100
```

### Optional: ngrok config file (`~/.config/ngrok/ngrok.yml`)

```yaml
version: "3"
authtoken: <YOUR_NGROK_TOKEN>
tunnels:
  llama-ui:
    proto: http
    addr: 8100
    # inspect: false   # uncomment to disable ngrok request inspector
```

Then start with:
```bash
ngrok start llama-ui
```

---

## Usage

### Browser

Open the ngrok URL in your browser:
```
https://abc123.ngrok-free.app
```
→ Browser shows a **login dialog** (HTTP Basic Auth).  
→ Enter the username and password you created in Step 1.

---

### curl / API (no password needed)

curl's default `User-Agent` is `curl/x.x.x` — nginx sees it is not a browser and skips auth.

```bash
# List available models
curl https://abc123.ngrok-free.app/v1/models

# Chat completion
curl https://abc123.ngrok-free.app/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-12b-it-Q4_K_M.gguf",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'
```

> [!NOTE]
> If you use a custom `User-Agent` that contains `Mozilla`, nginx will require auth.
> To force no-auth with a custom agent: `curl -A "my-script/1.0" https://...`

---

## How to Stop

```bash
# Stop ngrok: Ctrl+C in the ngrok terminal, or:
pkill ngrok

# Stop nginx proxy (does not affect nginx serving other sites):
sudo nginx -s reload   # after removing the symlink
# or fully stop:
sudo systemctl stop nginx
```

---

## Security Notes

> [!WARNING]
> HTTP Basic Auth is only secure over HTTPS. ngrok provides HTTPS automatically — never expose port `8100` directly on the internet without ngrok or another TLS layer.

> [!IMPORTANT]
> The User-Agent check is a **convenience gate**, not a security boundary. Anyone can spoof a non-Mozilla User-Agent to bypass the password. If you need strong security, use **ngrok's OAuth** integration or **IP allowlist** instead.

> [!TIP]
> To restrict access to specific IPs only (ngrok paid), add to `ngrok.yml`:
> ```yaml
> ip_restrictions:
>   allow_cidrs:
>     - "203.0.113.0/24"   # office IP range
> ```
