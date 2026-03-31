# Backend — BeamMP Self-Hosted API

A self-hosted FastAPI backend that replaces `backend.beammp.com` and `auth.beammp.com`. Handles player authentication, server registration, mod distribution, and provides a web dashboard for administration.

## Deployment

### Docker (Recommended)

```bash
cp .env.example .env
# Edit .env — set ADMIN_KEY and ALLOWED_ORIGINS
docker compose up -d --build
```

The container exposes port **8420** (mapped to internal port 8000). Place a reverse proxy with TLS in front of it.

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ADMIN_KEY` | **Yes** | `changeme-admin-key` | Secret key for programmatic admin API access |
| `ALLOWED_ORIGINS` | No | `https://backend.yourdomain.xyz` | Comma-separated list of allowed CORS origins |
| `LAUNCHER_VERSION` | No | `2.7.0` | Version string returned to launchers for update checks |
| `SERVER_VERSION` | No | `3.9.1` | Version string returned to game servers |
| `DATA_DIR` | No | `/data` | Directory for SQLite database, mods, and builds |

### .env Example

```env
ADMIN_KEY=your-strong-random-key-here
ALLOWED_ORIGINS=https://backend.yourdomain.xyz
LAUNCHER_VERSION=2.7.0
SERVER_VERSION=3.9.1
```

### Docker Compose Customization

The default `docker-compose.yml` mounts `/mnt/user/appdata/beammp_backend` as the data volume. Change this to a path on your host:

```yaml
volumes:
  - /path/to/your/data:/data
```

## First Login

1. Navigate to `https://your-backend-domain/`
2. Log in with `admin` / `changeme`
3. **Change the admin password immediately** via the Users panel

## Build Distribution

Place your compiled binaries in the `/data/builds/` directory (or upload via the web dashboard):

| File | Purpose |
|---|---|
| `BeamMP-Launcher.exe` | Launcher binary served at `/builds/launcher` |
| `BeamMP.zip` | Game mod archive served at `/builds/client` |

## API Endpoints

### Game Client / Launcher

| Endpoint | Method | Description |
|---|---|---|
| `/userlogin` | POST | Player login (username + password or private key) |
| `/pkToUser` | POST | Authenticate player during server join |
| `/servers-info` | GET | List of active servers |
| `/heartbeat` | POST | Server heartbeat / registration |
| `/builds/launcher` | GET | Download launcher binary |
| `/builds/client` | GET | Download game mod |
| `/sha/launcher` | GET | SHA256 hash of launcher binary |
| `/sha/mod` | GET | SHA256 hash of game mod |
| `/version/launcher` | GET | Current launcher version string |
| `/v/s` | GET | Current server version string |

### Web Dashboard API

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/status` | GET | — | Public server status |
| `/api/metrics` | GET | Session | Metrics history |
| `/api/admin/login` | POST | — | Login (returns session cookie) |
| `/api/admin/logout` | POST | Session | Clear session |
| `/api/register` | POST | — | Register with a registration key |
| `/api/admin/users` | GET/POST | Admin | List / create users |
| `/api/admin/users/{username}` | DELETE/PATCH | Admin | Delete / update user |
| `/api/admin/keys` | GET/POST | Admin | List / create server auth keys |
| `/api/admin/keys/{key}` | DELETE | Admin | Delete server auth key |
| `/api/my/keys` | GET | Session | List own server keys |
| `/api/my/keys/{key}` | PATCH | Session | Rename a key |
| `/api/admin/registration-keys` | GET/POST | Admin | Manage registration keys |
| `/api/admin/registration-keys/{key}` | DELETE | Admin | Delete registration key |

### Admin API (Key-Based)

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/admin/users` | POST | `ADMIN_KEY` header | Create user programmatically |
| `/admin/keys` | POST | `ADMIN_KEY` header | Generate server auth key |

## Database

SQLite stored at `DATA_DIR/beammp.db` with WAL mode. Tables:

- **users** — id, username, password_hash, role, private_key, public_key
- **keys** — id, key, server_name, owner, created_by, created_at
- **registration_keys** — id, key, created_by, created_at, used, used_by, used_at

Legacy JSON files (`users.json`, `keys.json`) are auto-migrated on first run.

## Reverse Proxy Example (Caddy)

```
backend.yourdomain.xyz {
    reverse_proxy localhost:8420
}
```

## Reverse Proxy Example (nginx)

```nginx
server {
    listen 443 ssl;
    server_name backend.yourdomain.xyz;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8420;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
