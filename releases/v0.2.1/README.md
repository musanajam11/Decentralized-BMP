# Decentralized-BMP — v0.2.1 Release

Self-hosted, fully configurable replacement for `backend.beammp.com` and `auth.beammp.com`. No hardcoded domains — point every component at any backend URL you control.

## What's New in v0.2.1

- **BeamNG Content Manager alternative** — The web dashboard now shows an info box explaining that users can use the [BeamNG Content Manager](https://github.com/musanajam11/BeamNG-Content-Manager) instead of patching the launcher. Just point the Content Manager's auth/backend URLs at this backend and connect — no client patch required.

## Upgrading from v0.2.0

1. Replace `index.html` in your backend folder with the new version.
2. Rebuild: `docker compose up -d --build`

No changes to `main.py`, launcher, or server binaries.

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
