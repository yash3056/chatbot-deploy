# llama-stack systemd Service — Admin Guide

## Why this exists

The llama.cpp container in our Docker Compose stack uses GPU passthrough (`--gpus all` / nvidia runtime). The NVIDIA container runtime binds GPU devices to a container at **creation time**, not at **start time**.

Docker's own `restart: unless-stopped` policy only *restarts* existing containers after a host reboot — it does not recreate them. After a server reboot, the NVIDIA driver re-initializes and GPU devices can re-enumerate, which leaves a merely-restarted container with stale GPU bindings. Symptom: the container shows as "running," logs show no errors, but the model is effectively not usable on GPU.

**The fix:** stop relying on Docker's restart policy for the llama.cpp service and instead let a systemd unit run `docker compose up -d` on every boot. `up -d` recreates any container whose config has changed or that isn't already correctly running, which re-triggers proper GPU device injection every time.

This systemd unit manages the **entire Compose stack** (all 5 linked containers) as a single unit — start, stop, and boot-time bring-up all go through systemd now, not through each container's individual restart policy.

---

## 1. Required change to docker-compose.yml

Before installing the service, open your `docker-compose.yml` and change the restart policy on the llama.cpp service (and ideally all services in the stack, for consistency) from:

```yaml
services:
  llama-cpp:
    restart: unless-stopped
```

to:

```yaml
services:
  llama-cpp:
    restart: "no"
```

**Why:** if you leave `restart: unless-stopped` in place, Docker will still try to auto-restart the container on its own after a crash or reboot — fighting with systemd, which is now responsible for bringing the stack up correctly. Setting it to `"no"` hands full control to the systemd unit. systemd's `Requires=`/`After=` ordering guarantees Docker and the NVIDIA driver are ready *before* `docker compose up -d` runs, which is the whole point of this change.

If any of the other 4 containers depend on llama.cpp being up (via `depends_on`), leave their `restart` policy as `unless-stopped` — they're not affected by the GPU rebind issue, and Docker restarting them internally is fine. Only the GPU-bound service needs `restart: "no"`.

---

## 2. Installing the service

### 2.1 Create the unit file

```bash
sudo nano /etc/systemd/system/llama-stack.service
```

Paste the following, **replacing `/path/to/your/compose/dir` with the actual absolute path** to the directory containing your `docker-compose.yml`:

```ini
# /etc/systemd/system/llama-stack.service
[Unit]
Description=Llama.cpp Docker Stack
Requires=docker.service nvidia-persistenced.service
After=docker.service nvidia-persistenced.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/path/to/your/compose/dir
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
```

**What each part means:**

| Directive | Purpose |
|---|---|
| `Requires=docker.service nvidia-persistenced.service` | Won't even attempt to start until both Docker and the NVIDIA persistence daemon are running. If either fails, this unit fails too. |
| `After=...network-online.target` | Ordering only (not a hard dependency) — waits for network to be up, useful if any container pulls from a registry or depends on network-mounted volumes. |
| `Type=oneshot` + `RemainAfterExit=yes` | Tells systemd this is a "run once and stay considered active" service, not a long-running process (correct for `docker compose up -d`, which exits after launching containers in the background). |
| `WorkingDirectory` | Must point to the folder containing `docker-compose.yml`, or `docker compose` won't find it. |
| `ExecStart` / `ExecStop` | What runs on `systemctl start` / `systemctl stop`. |
| `WantedBy=multi-user.target` | Ensures this runs automatically on every normal boot. |

> **Note:** confirm the path to Docker's compose binary matches your system — `/usr/bin/docker compose` (Compose v2 plugin) is standard on modern installs. Check with `which docker` and `docker compose version`. If you're on an older Compose v1 (`docker-compose`, hyphenated), adjust `ExecStart`/`ExecStop` accordingly.

### 2.2 Confirm nvidia-persistenced exists as a systemd service

This unit depends on it, so it must exist and be enabled:

```bash
systemctl status nvidia-persistenced
```

If it's not found or not enabled:

```bash
sudo systemctl enable --now nvidia-persistenced
```

If your system genuinely doesn't ship this service (rare, but possible depending on driver install method), remove `nvidia-persistenced.service` from both `Requires=` and `After=` in the unit file — but do so only as a last resort, since it's what guarantees the GPU driver is ready before Docker starts containers.

### 2.3 Reload systemd and enable the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable llama-stack.service
```

`daemon-reload` makes systemd pick up the new/changed unit file — **always run this after editing any `.service` file**, or your changes won't take effect. `enable` makes it start automatically on boot (via `WantedBy=multi-user.target`); it does not start it immediately.

### 2.4 Start it now (first run)

```bash
sudo systemctl start llama-stack.service
```

---

## 3. Day-to-day operations

| Task | Command |
|---|---|
| Start the whole stack | `sudo systemctl start llama-stack.service` |
| Stop the whole stack | `sudo systemctl stop llama-stack.service` |
| Restart the whole stack | `sudo systemctl restart llama-stack.service` |
| Check current status | `systemctl status llama-stack.service` |
| Check if it's enabled on boot | `systemctl is-enabled llama-stack.service` |
| Disable auto-start on boot | `sudo systemctl disable llama-stack.service` |
| View recent systemd-level logs | `journalctl -u llama-stack.service -n 50 --no-pager` |
| Follow logs live | `journalctl -u llama-stack.service -f` |
| Check actual container status | `docker compose -f /path/to/your/compose/dir/docker-compose.yml ps` |
| Check llama.cpp container logs | `docker compose -f /path/to/your/compose/dir/docker-compose.yml logs -f llama-cpp` |

**Important distinction:** `systemctl status` tells you whether the *systemd unit* ran successfully (i.e., whether `docker compose up -d` was executed without error). It does **not** tell you whether the containers inside are healthy or whether the model is actually usable on GPU — for that, check `docker compose ps` and the llama.cpp container's own logs, and ideally hit its `/health` endpoint.

---

## 4. Editing the service

1. Edit the file:
   ```bash
   sudo nano /etc/systemd/system/llama-stack.service
   ```
2. **Always reload after editing:**
   ```bash
   sudo systemctl daemon-reload
   ```
3. Restart to apply:
   ```bash
   sudo systemctl restart llama-stack.service
   ```

Common edits you might make later:
- Adding a healthcheck-based `ExecStartPost` to verify the model is actually loaded before considering startup "done"
- Changing `WorkingDirectory` if the compose project moves
- Adding more dependencies to `After=`/`Requires=` if the stack grows

---

## 5. Rolling back (if needed)

To fully remove this setup and go back to relying on Docker's own restart policy:

```bash
sudo systemctl stop llama-stack.service
sudo systemctl disable llama-stack.service
sudo rm /etc/systemd/system/llama-stack.service
sudo systemctl daemon-reload
```

Then revert `restart: "no"` back to `restart: unless-stopped` in `docker-compose.yml` and run `docker compose up -d` once manually. Note: this reintroduces the original GPU rebind bug on reboot — only do this if you have another fix in place.

---

## 6. Troubleshooting

**Service fails to start / `systemctl status` shows `failed`:**
- Run `journalctl -u llama-stack.service -n 50 --no-pager` to see the actual error.
- Common cause: wrong `WorkingDirectory` path, or `docker compose` command not found at that path (check `which docker`).

**Service starts fine but llama.cpp still isn't responding correctly:**
- This means the systemd/Docker recreation part worked, but something else is wrong (model load error, GPU still not bound). Check `docker compose logs llama-cpp` directly — this is a container-level issue, not a systemd-level one.

**`nvidia-persistenced.service` not found:**
- Confirms your driver install didn't set it up as a systemd unit. Install/enable it, or as a fallback remove it from `Requires=`/`After=` (see 2.2).

**Containers come up before GPU is fully ready even with this fix:**
- Add `nvidia-smi` polling into a pre-start check, or a short `ExecStartPre=/bin/sleep 5` as a stopgap — not elegant, but works if driver init is occasionally slow on your hardware.
