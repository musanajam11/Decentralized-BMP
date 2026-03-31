# Decentralized-BMP — v0.2.0 Release

Self-hosted, fully configurable replacement for `backend.beammp.com` and `auth.beammp.com`. No hardcoded domains — point every component at any backend URL you control.

## What's New in v0.2.0

- **Configurable backend URL** — The launcher, game server, and web dashboard can all point at any backend. Switch between your own backend, another community backend, or the official one by changing a single URL.
  - **Launcher**: Set `BackendUrl` in `Launcher.cfg`
  - **Server**: Set `BackendUrl` in `ServerConfig.toml` (or env var `BEAMMP_BACKEND_URL`)
  - **Web UI**: Click the backend indicator in the navbar to switch
- **Backend switcher in dashboard** — Navbar shows the current backend with version. Click it to save and switch between multiple backends.

## Switching Backends

To point your entire stack at a different backend:

1. **Launcher** — Edit `Launcher.cfg`:
   ```json
   {
       "Port": 4444,
       "Build": "Default",
       "BackendUrl": "https://your-backend.example.com"
   }
   ```

2. **Game Server** — Edit `ServerConfig.toml`:
   ```toml
   [General]
   BackendUrl = "https://your-backend.example.com"
   ```
   Or set the environment variable:
   ```
   BEAMMP_BACKEND_URL=https://your-backend.example.com
   ```

3. **Web Dashboard** — Click the backend indicator in the top navbar and enter the new URL.

## Upgrading from v0.1.1

1. Replace `main.py` and `index.html` in your backend folder.
2. Rebuild: `docker compose up -d --build`
3. Update `Launcher.cfg` to include the `BackendUrl` field.
4. Update `ServerConfig.toml` to include the `BackendUrl` field.
5. Recompile the launcher and server binaries (source changes required).

## Quick Start

```bash
cd backend
cp .env.example .env
# Edit .env — set a strong ADMIN_KEY and your domain
docker compose up -d --build
```

Default login: `admin` / `changeme` — change this immediately.

## Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI backend server |
| `index.html` | Web UI (served by FastAPI) |
| `Dockerfile` | Container build |
| `docker-compose.yml` | Container orchestration |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |
| `builds/` | Place `BeamMP-Launcher.exe` and `BeamMP.zip` here |

## Configuration Points

| Component | Config File | Key | Env Var | Default |
|-----------|------------|-----|---------|---------|
| Launcher | `Launcher.cfg` | `BackendUrl` | — | `https://backend.yourdomain.xyz` |
| Server | `ServerConfig.toml` | `BackendUrl` | `BEAMMP_BACKEND_URL` | `https://backend.yourdomain.xyz` |
| Backend | `.env` | `ALLOWED_ORIGINS` | `ALLOWED_ORIGINS` | `https://backend.yourdomain.xyz` |
| Web UI | Browser localStorage | — | — | Current origin |

## Data Storage

| Data | Storage | Location |
|------|---------|----------|
| Users & keys | SQLite | `/data/beammp.db` |
| Active servers | JSON | `/data/servers.json` (transient) |
| Mods | Files | `/data/mods/{server_id}/` |
| Launcher/mod builds | Files | `/data/builds/` |
