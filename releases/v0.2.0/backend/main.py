# Decentralized-BMP Backend
# Copyright (C) 2024 Decentralized-BMP contributors.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
BeamMP Custom Backend Server
Replaces backend.beammp.com and auth.beammp.com for self-hosted play.
"""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

import bcrypt
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "https://backend.yourdomain.xyz").split(",")

app = FastAPI(title="BeamMP Custom Backend", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)

# --- Configuration ---
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_FILE = DATA_DIR / "beammp.db"
SERVERS_FILE = DATA_DIR / "servers.json"
LAUNCHER_DIR = DATA_DIR / "builds"
MOD_DIR = DATA_DIR / "builds"
MOD_STORAGE_DIR = DATA_DIR / "mods"

# Legacy JSON paths (used only for one-time migration)
_LEGACY_USERS_FILE = DATA_DIR / "users.json"
_LEGACY_KEYS_FILE = DATA_DIR / "keys.json"

# The launcher version you're distributing (match your launcher binary)
LAUNCHER_VERSION = os.environ.get("LAUNCHER_VERSION", "2.7.0")

# Backend version
BACKEND_VERSION = "0.2.0"

# --- ADMIN_KEY validation ---
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
if not ADMIN_KEY or ADMIN_KEY in ("changeme-admin-key", "changeme-set-a-real-key-here"):
    import sys
    print("[FATAL] ADMIN_KEY environment variable is not set or is still the default value!")
    print("[FATAL] Set a strong, unique ADMIN_KEY in your .env or environment before starting.")
    sys.exit(1)

# --- Global State ---
STARTUP_TIME = time.time()
ADMIN_SESSIONS: dict[str, dict] = {}  # token -> {"username": str, "role": str, "created": float}

# --- Metrics ---
METRICS_HISTORY: list[dict] = []  # [{"ts": epoch, "players": N, "servers": N, "requests": N, "heartbeats": N}]
METRICS_MAX_POINTS = 60  # 1 hour at 1-min intervals
METRICS_COUNTERS = {"requests": 0, "heartbeats": 0}
METRICS_LAST_SAMPLE = time.time()


def sample_metrics():
    """Take a metrics snapshot if >= 60s since last sample."""
    global METRICS_LAST_SAMPLE
    now = time.time()
    if now - METRICS_LAST_SAMPLE < 60:
        return
    servers = get_servers()
    active = [s for s in servers if now - s.get("last_heartbeat", 0) < 60]
    METRICS_HISTORY.append({
        "ts": int(now),
        "players": sum(s.get("players", 0) for s in active),
        "servers": len(active),
        "requests": METRICS_COUNTERS["requests"],
        "heartbeats": METRICS_COUNTERS["heartbeats"],
    })
    METRICS_COUNTERS["requests"] = 0
    METRICS_COUNTERS["heartbeats"] = 0
    if len(METRICS_HISTORY) > METRICS_MAX_POINTS:
        METRICS_HISTORY[:] = METRICS_HISTORY[-METRICS_MAX_POINTS:]
    METRICS_LAST_SAMPLE = now
    # Cleanup stale rate-limiting entries to prevent memory leaks
    for key in list(ENDPOINT_REQUESTS.keys()):
        ENDPOINT_REQUESTS[key] = [t for t in ENDPOINT_REQUESTS[key] if now - t < 300]
        if not ENDPOINT_REQUESTS[key]:
            del ENDPOINT_REQUESTS[key]
    for key in list(HEARTBEAT_TIMESTAMPS.keys()):
        if now - HEARTBEAT_TIMESTAMPS[key] > 120:
            del HEARTBEAT_TIMESTAMPS[key]
    for key in list(LOGIN_ATTEMPTS.keys()):
        LOGIN_ATTEMPTS[key] = [t for t in LOGIN_ATTEMPTS[key] if now - t < LOGIN_WINDOW_SECONDS]
        if not LOGIN_ATTEMPTS[key]:
            del LOGIN_ATTEMPTS[key]

# --- Rate Limiting ---
LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)  # ip -> [timestamps]
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 900  # 15 minutes


def is_rate_limited(ip: str) -> bool:
    """Check if an IP has exceeded login attempt limits."""
    now = time.time()
    # Prune old attempts
    LOGIN_ATTEMPTS[ip] = [t for t in LOGIN_ATTEMPTS[ip] if now - t < LOGIN_WINDOW_SECONDS]
    return len(LOGIN_ATTEMPTS[ip]) >= MAX_LOGIN_ATTEMPTS


def record_login_attempt(ip: str):
    """Record a failed login attempt for rate limiting."""
    LOGIN_ATTEMPTS[ip].append(time.time())


# --- General Rate Limiting (all public endpoints) ---
ENDPOINT_REQUESTS: dict[str, list[float]] = defaultdict(list)  # "ip:endpoint" -> [timestamps]
HEARTBEAT_TIMESTAMPS: dict[str, float] = {}  # auth_key -> last heartbeat time
HEARTBEAT_MIN_INTERVAL = 5  # seconds between heartbeats per server
MAX_BODY_SIZE = 1 * 1024 * 1024  # 1MB for non-upload requests


def is_endpoint_rate_limited(ip: str, endpoint: str, max_requests: int = 30, window: int = 60) -> bool:
    """General rate limiter for any endpoint by IP."""
    now = time.time()
    key = f"{ip}:{endpoint}"
    ENDPOINT_REQUESTS[key] = [t for t in ENDPOINT_REQUESTS[key] if now - t < window]
    if len(ENDPOINT_REQUESTS[key]) >= max_requests:
        return True
    ENDPOINT_REQUESTS[key].append(now)
    return False


def get_client_ip(request: Request) -> str:
    """Extract real client IP from proxy headers."""
    return (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.headers.get("x-real-ip", "")
        or (request.client.host if request.client else "0.0.0.0")
    )


# --- Input Validation ---
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")


def validate_username(username: str) -> bool:
    """Username must be 3-32 chars: alphanumeric, hyphens, underscores."""
    return bool(USERNAME_RE.match(username))


def validate_password(password: str) -> bool:
    """Password must be at least 8 characters."""
    return len(password) >= 8


# --- Helpers ---
def sha256_file(path: Path) -> str:
    """Get SHA256 hash of a file."""
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_server_id(auth_key: str) -> str:
    """Generate a public server ID from the auth key."""
    return hashlib.sha256(auth_key.encode()).hexdigest()[:16]


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_servers() -> list:
    return load_json(SERVERS_FILE, [])


def save_servers(servers: list):
    save_json(SERVERS_FILE, servers)


# =========================================================================
# DATABASE LAYER (SQLite)
# =========================================================================

def get_db():
    """Get a database connection with WAL mode for concurrent reads."""
    conn = sqlite3.connect(str(DB_FILE), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'USER',
            private_key TEXT,
            public_key TEXT
        );
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            server_name TEXT NOT NULL DEFAULT 'My Server',
            owner TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS registration_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            used_by TEXT,
            used_at TEXT
        );
    """)
    conn.commit()
    conn.close()
    # Migrate: add used columns to registration_keys if missing
    conn = get_db()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(registration_keys)").fetchall()]
    if "used" not in cols:
        conn.execute("ALTER TABLE registration_keys ADD COLUMN used INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE registration_keys ADD COLUMN used_by TEXT")
        conn.execute("ALTER TABLE registration_keys ADD COLUMN used_at TEXT")
        conn.commit()
    conn.close()


def migrate_json_to_db():
    """One-time migration of legacy JSON files into SQLite."""
    migrated = False
    # Migrate users
    if _LEGACY_USERS_FILE.exists():
        users = load_json(_LEGACY_USERS_FILE, {})
        if users:
            conn = get_db()
            for uname, udata in users.items():
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO users (username, password_hash, role, private_key, public_key) VALUES (?, ?, ?, ?, ?)",
                        (uname, udata.get("password_hash", ""), udata.get("role", "USER"),
                         udata.get("private_key"), udata.get("public_key")),
                    )
                except Exception as e:
                    print(f"[MIGRATE] Failed to migrate user '{uname}': {e}")
            conn.commit()
            conn.close()
            _LEGACY_USERS_FILE.rename(_LEGACY_USERS_FILE.with_suffix(".json.bak"))
            print(f"[MIGRATE] Migrated {len(users)} users from JSON to SQLite")
            migrated = True
    # Migrate keys
    if _LEGACY_KEYS_FILE.exists():
        keys = load_json(_LEGACY_KEYS_FILE, [])
        if keys:
            conn = get_db()
            for k in keys:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO keys (key, server_name, owner, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                        (k.get("key", ""), k.get("server_name", "My Server"),
                         k.get("owner", ""), k.get("created_by", ""), k.get("created_at", "")),
                    )
                except Exception as e:
                    print(f"[MIGRATE] Failed to migrate key: {e}")
            conn.commit()
            conn.close()
            _LEGACY_KEYS_FILE.rename(_LEGACY_KEYS_FILE.with_suffix(".json.bak"))
            print(f"[MIGRATE] Migrated {len(keys)} keys from JSON to SQLite")
            migrated = True
    if migrated:
        print("[MIGRATE] Legacy JSON files renamed to .json.bak — safe to delete after verifying")


# --- User DB helpers ---

def db_get_user(username: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def db_get_user_by_private_key(pk: str) -> tuple | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE private_key = ?", (pk,)).fetchone()
    conn.close()
    if not row:
        return None
    return (row["username"], dict(row))


def db_get_user_by_public_key(pk: str) -> tuple | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE public_key = ?", (pk,)).fetchone()
    conn.close()
    if not row:
        return None
    return (row["username"], dict(row))


def db_create_user(username: str, password_hash: str, role: str, private_key: str = None, public_key: str = None) -> bool:
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, private_key, public_key) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, role, private_key, public_key),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def db_update_user(username: str, **fields) -> bool:
    if not fields:
        return False
    allowed = {"password_hash", "role", "private_key", "public_key"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [username]
    conn = get_db()
    cur = conn.execute(f"UPDATE users SET {set_clause} WHERE username = ?", values)
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


# --- Registration Key DB helpers ---

def db_create_registration_key(key: str, created_by: str) -> bool:
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO registration_keys (key, created_by, created_at) VALUES (?, ?, ?)",
            (key, created_by, time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def db_get_registration_key(key: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM registration_keys WHERE key = ? AND used = 0", (key,)).fetchone()
    conn.close()
    return dict(row) if row else None


def db_mark_registration_key_used(key: str, used_by: str) -> bool:
    conn = get_db()
    cur = conn.execute(
        "UPDATE registration_keys SET used = 1, used_by = ?, used_at = ? WHERE key = ? AND used = 0",
        (used_by, time.strftime("%Y-%m-%d %H:%M:%S"), key),
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def db_delete_registration_key(key: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM registration_keys WHERE key = ?", (key,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def db_list_registration_keys() -> list:
    conn = get_db()
    rows = conn.execute("SELECT key, created_by, created_at, used, used_by, used_at FROM registration_keys ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_delete_user(username: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def db_list_users() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT id, username, role FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_count_users() -> int:
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


def db_user_exists(username: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row is not None


# --- Key DB helpers ---

def db_get_all_keys() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT key, server_name, owner, created_by, created_at FROM keys").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_get_keys_by_owner(owner: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT key, server_name, owner, created_by, created_at FROM keys WHERE owner = ?", (owner,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_key_is_valid(auth_key: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT 1 FROM keys WHERE key = ?", (auth_key,)).fetchone()
    conn.close()
    return row is not None


def db_get_key_owner(auth_key: str) -> str:
    conn = get_db()
    row = conn.execute("SELECT owner FROM keys WHERE key = ?", (auth_key,)).fetchone()
    conn.close()
    return row["owner"] if row else ""


def db_create_key(key: str, server_name: str, owner: str, created_by: str, created_at: str) -> bool:
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO keys (key, server_name, owner, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (key, server_name, owner, created_by, created_at),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def db_delete_key(key: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM keys WHERE key = ?", (key,))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def db_update_key_name(key: str, new_name: str) -> bool:
    conn = get_db()
    cur = conn.execute("UPDATE keys SET server_name = ? WHERE key = ?", (new_name, key))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def db_get_key_info(key: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT key, server_name, owner, created_by, created_at FROM keys WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


# --- Password helpers ---

def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, user: dict) -> bool:
    """Verify password against stored hash. Auto-upgrades legacy SHA256 hashes to bcrypt."""
    stored_hash = user.get("password_hash", "")

    # Check if this is a legacy SHA256 hash (64 hex chars)
    if len(stored_hash) == 64 and all(c in '0123456789abcdef' for c in stored_hash):
        # Legacy SHA256 verification (no salt in DB schema, but check anyway)
        expected = hashlib.sha256(password.encode()).hexdigest()
        if secrets.compare_digest(expected, stored_hash):
            # Auto-upgrade to bcrypt and persist
            new_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            user["password_hash"] = new_hash
            db_update_user(user["username"], password_hash=new_hash)
            return True
        return False
    else:
        # bcrypt verification
        return bcrypt.checkpw(password.encode(), stored_hash.encode())


def verify_admin_session(request: Request) -> dict | None:
    """Check for valid admin session cookie. Returns session dict or None."""
    token = request.cookies.get("session_token")
    if not token or token not in ADMIN_SESSIONS:
        return None
    session = ADMIN_SESSIONS[token]
    if time.time() - session["created"] > 86400:  # 24h expiry
        del ADMIN_SESSIONS[token]
        return None
    if session.get("role") != "ADM":
        return None
    return session


def verify_any_session(request: Request) -> dict | None:
    """Check for any valid session cookie. Returns {"username": str, "role": str} or None."""
    token = request.cookies.get("session_token")
    if not token or token not in ADMIN_SESSIONS:
        return None
    session = ADMIN_SESSIONS[token]
    if time.time() - session["created"] > 86400:
        del ADMIN_SESSIONS[token]
        return None
    return {"username": session["username"], "role": session.get("role", "USER")}


# --- Request counting middleware ---
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    METRICS_COUNTERS["requests"] += 1
    sample_metrics()
    response = await call_next(request)
    return response


@app.middleware("http")
async def body_size_middleware(request: Request, call_next):
    """Reject non-upload requests with bodies larger than MAX_BODY_SIZE."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_SIZE:
                    return JSONResponse({"error": "Request body too large"}, status_code=413)
            except ValueError:
                pass
    response = await call_next(request)
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


# --- Startup: ensure data dirs and default admin user ---
@app.on_event("startup")
def startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCHER_DIR.mkdir(parents=True, exist_ok=True)
    MOD_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database and migrate legacy JSON if present
    init_db()
    migrate_json_to_db()

    # Create default admin user if no users exist
    if db_count_users() == 0:
        initial_password = secrets.token_urlsafe(16)
        db_create_user("admin", hash_password(initial_password), "ADM",
                       secrets.token_hex(32), secrets.token_hex(16))
        print(f"[SETUP] ======================================")
        print(f"[SETUP] Created default admin user")
        print(f"[SETUP] Username: admin")
        print(f"[SETUP] Password: {initial_password}")
        print(f"[SETUP] SAVE THIS PASSWORD — it will not be shown again!")
        print(f"[SETUP] ======================================")

    if not SERVERS_FILE.exists():
        save_servers([])


# =========================================================================
# BACKEND ENDPOINTS (replaces backend.beammp.com)
# =========================================================================

@app.get("/sha/launcher")
def sha_launcher(request: Request, branch: str = "default", pk: str = ""):
    """Return SHA256 hash of the launcher binary."""
    if is_endpoint_rate_limited(get_client_ip(request), "sha", max_requests=60):
        return PlainTextResponse("Rate limited", status_code=429)
    launcher_path = LAUNCHER_DIR / "BeamMP-Launcher.exe"
    h = sha256_file(launcher_path)
    if not h:
        # Return hash of the currently running version so no update is triggered
        return PlainTextResponse("no_update")
    return PlainTextResponse(h)


@app.get("/version/launcher")
def version_launcher(request: Request, branch: str = "default", pk: str = ""):
    """Return the current launcher version string."""
    if is_endpoint_rate_limited(get_client_ip(request), "sha", max_requests=60):
        return PlainTextResponse("Rate limited", status_code=429)
    return PlainTextResponse(LAUNCHER_VERSION)


@app.get("/builds/launcher")
def download_launcher(request: Request, download: bool = True, pk: str = "", branch: str = "default"):
    """Download the launcher binary."""
    if is_endpoint_rate_limited(get_client_ip(request), "downloads", max_requests=5):
        return PlainTextResponse("Rate limited", status_code=429)
    launcher_path = LAUNCHER_DIR / "BeamMP-Launcher.exe"
    if not launcher_path.exists():
        return PlainTextResponse("Build not available", status_code=404)
    return FileResponse(launcher_path, filename="BeamMP-Launcher.exe")


@app.get("/sha/mod")
def sha_mod(request: Request, branch: str = "default", pk: str = ""):
    """Return SHA256 hash of the mod zip."""
    if is_endpoint_rate_limited(get_client_ip(request), "sha", max_requests=60):
        return PlainTextResponse("Rate limited", status_code=429)
    mod_path = MOD_DIR / "BeamMP.zip"
    h = sha256_file(mod_path)
    if not h:
        return PlainTextResponse("no_update")
    return PlainTextResponse(h)


@app.get("/builds/client")
def download_mod(request: Request, download: bool = True, pk: str = "", branch: str = "default"):
    """Download the mod zip."""
    if is_endpoint_rate_limited(get_client_ip(request), "downloads", max_requests=5):
        return PlainTextResponse("Rate limited", status_code=429)
    mod_path = MOD_DIR / "BeamMP.zip"
    if not mod_path.exists():
        return PlainTextResponse("Mod not available", status_code=404)
    return FileResponse(mod_path, filename="BeamMP.zip")


@app.get("/servers-info")
def servers_info(request: Request):
    """Return the server list. Cleans up stale servers (no heartbeat in 60s)."""
    if is_endpoint_rate_limited(get_client_ip(request), "servers-info"):
        return JSONResponse({"error": "Too many requests"}, status_code=429)
    servers = get_servers()
    now = time.time()
    # Remove servers that haven't sent a heartbeat in 60 seconds
    active = [s for s in servers if now - s.get("last_heartbeat", 0) < 60]
    if len(active) != len(servers):
        save_servers(active)
    is_admin = verify_admin_session(request) is not None
    # Strip internal fields before returning
    hidden = {"last_heartbeat", "auth_key"}
    public = []
    for s in active:
        entry = {k: v for k, v in s.items() if k not in hidden}
        entry["server_id"] = get_server_id(s.get("auth_key", ""))
        # List mods available for download on the backend
        sid = entry["server_id"]
        mod_dir = MOD_STORAGE_DIR / sid
        if mod_dir.exists():
            entry["downloadable_mods"] = [f.name for f in mod_dir.iterdir() if f.is_file() and f.suffix == ".zip"]
        else:
            entry["downloadable_mods"] = []
        public.append(entry)
    return JSONResponse(public)


# =========================================================================
# AUTH ENDPOINTS (replaces auth.beammp.com)
# =========================================================================

@app.post("/userlogin")
async def userlogin(request: Request):
    """
    Handle login. Accepts:
      - {"username": "x", "password": "y"}  (manual login)
      - {"pk": "private_key"}               (auto-login with saved key)
      - "LO"                                (logout — handled client-side)
    """
    body = await request.body()
    body_str = body.decode("utf-8", errors="replace")
    print(f"[USERLOGIN] Received body: {body_str[:200]}")

    try:
        data = json.loads(body_str)
    except json.JSONDecodeError:
        print("[USERLOGIN] JSON decode failed")
        return JSONResponse({"success": False, "message": "Invalid request"})

    # Auto-login by private key
    if "pk" in data:
        pk = data["pk"]
        result = db_get_user_by_private_key(pk)
        if result:
            uname, udata = result
            return JSONResponse({
                "success": True,
                "message": "Auto-login successful",
                "username": uname,
                "role": udata.get("role", "USER"),
                "id": udata.get("id", 0),
                "private_key": udata.get("private_key", ""),
                "public_key": udata.get("public_key", ""),
            })
        return JSONResponse({"success": False, "message": "Invalid key"})

    # Manual login
    username = data.get("username", "")
    password = data.get("password", "")

    if not username or not password:
        return JSONResponse({"success": False, "message": "Username and password required"})

    client_ip = get_client_ip(request)
    if is_rate_limited(client_ip):
        return JSONResponse({"success": False, "message": "Too many login attempts. Try again later."})

    user = db_get_user(username)
    if not user:
        record_login_attempt(client_ip)
        return JSONResponse({"success": False, "message": "Invalid credentials"})

    if not verify_password(password, user):
        record_login_attempt(client_ip)
        print(f"[USERLOGIN] Password mismatch for '{username}'")
        return JSONResponse({"success": False, "message": "Invalid credentials"})

    print(f"[USERLOGIN] Login successful for '{username}'")

    # Generate keys if not present
    if not user.get("private_key"):
        pk = secrets.token_hex(32)
        pub = secrets.token_hex(16)
        db_update_user(username, private_key=pk, public_key=pub)
        user["private_key"] = pk
        user["public_key"] = pub

    return JSONResponse({
        "success": True,
        "message": "Login successful",
        "username": username,
        "role": user.get("role", "USER"),
        "id": user.get("id", 0),
        "private_key": user["private_key"],
        "public_key": user["public_key"],
    })


# =========================================================================
# SERVER REGISTRATION (for BeamMP-Server instances to register themselves)
# =========================================================================

@app.post("/servers/heartbeat")
async def server_heartbeat_legacy(request: Request):
    """Legacy endpoint — redirects to /heartbeat."""
    return await heartbeat(request)


# =========================================================================
# USER MANAGEMENT (admin endpoints for adding users)
# =========================================================================

@app.post("/admin/users")
async def create_user(request: Request):
    """
    Create a new user. Body: {"admin_key": "...", "username": "...", "password": "...", "role": "USER"}
    admin_key must match ADMIN_KEY env var.
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid JSON"}, status_code=400)

    if not secrets.compare_digest(data.get("admin_key", ""), ADMIN_KEY):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=403)

    username = data.get("username", "")
    password = data.get("password", "")
    role = data.get("role", "USER")

    if not username or not password:
        return JSONResponse({"success": False, "message": "username and password required"})

    if not validate_username(username):
        return JSONResponse({"success": False, "message": "Username must be 3-32 alphanumeric characters, hyphens, or underscores"}, status_code=400)
    if not validate_password(password):
        return JSONResponse({"success": False, "message": "Password must be at least 8 characters"}, status_code=400)
    if role not in ("USER", "ADM"):
        return JSONResponse({"success": False, "message": "Role must be USER or ADM"}, status_code=400)

    if db_user_exists(username):
        return JSONResponse({"success": False, "message": "User already exists"})

    if not db_create_user(username, hash_password(password), role,
                          secrets.token_hex(32), secrets.token_hex(16)):
        return JSONResponse({"success": False, "message": "Failed to create user"}, status_code=500)

    return JSONResponse({"success": True, "message": f"User '{username}' created"})


# =========================================================================
# SERVER KEY MANAGEMENT (replaces beammp.com/keymaster)
# =========================================================================

@app.post("/admin/keys")
async def create_server_key(request: Request):
    """
    Generate a server auth key. Body: {"admin_key": "...", "server_name": "..."}
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid JSON"}, status_code=400)

    if not secrets.compare_digest(data.get("admin_key", ""), ADMIN_KEY):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=403)

    key = secrets.token_hex(32)
    return JSONResponse({
        "success": True,
        "auth_key": key,
        "server_name": data.get("server_name", "My Server"),
        "message": "Use this auth_key in your BeamMP-Server config",
    })


# =========================================================================
# SERVER-FACING ENDPOINTS (called by BeamMP-Server directly)
# =========================================================================

# The version your server binary is — return same version so no update nag
SERVER_VERSION = os.environ.get("SERVER_VERSION", "3.9.1")


@app.get("/v/s")
def server_version_check(request: Request):
    """Return the 'latest' server version string. Used by CheckForUpdates()."""
    if is_endpoint_rate_limited(get_client_ip(request), "sha", max_requests=60):
        return PlainTextResponse("Rate limited", status_code=429)
    return PlainTextResponse(SERVER_VERSION)


@app.post("/heartbeat")
async def heartbeat(request: Request):
    """
    BeamMP-Server heartbeat (POST /heartbeat with api-v:2 header).
    Body JSON keys: uuid, players, maxplayers, port, map, private, version,
                    clientversion, name, tags, guests, modlist, modstotalsize,
                    modstotal, playerslist, desc
    Must reply: {"status": "2000"/"200", "code": "...", "msg": "..."}
    """
    METRICS_COUNTERS["heartbeats"] += 1
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "code": "400", "msg": "Invalid JSON"}, status_code=400)

    auth_key = data.get("uuid", "")
    if not auth_key:
        return JSONResponse({"status": "error", "code": "401", "msg": "Missing auth key"})

    # Validate auth key against registered keys
    if not db_key_is_valid(auth_key):
        return JSONResponse({"status": "error", "code": "403", "msg": "Invalid or unregistered auth key"})

    # Look up owner from key registration
    key_owner = db_get_key_owner(auth_key)

    # Rate limit heartbeats per auth key (max 1 per 5 seconds)
    now = time.time()
    if auth_key in HEARTBEAT_TIMESTAMPS:
        if now - HEARTBEAT_TIMESTAMPS[auth_key] < HEARTBEAT_MIN_INTERVAL:
            return JSONResponse({"status": "error", "code": "429", "msg": "Heartbeat too frequent"}, status_code=429)
    HEARTBEAT_TIMESTAMPS[auth_key] = now

    servers = get_servers()

    existing = None
    first_seen = False
    for s in servers:
        if s.get("auth_key") == auth_key:
            existing = s
            break

    real_ip = get_client_ip(request)

    server_entry = {
        "auth_key": auth_key,
        "ip": real_ip,
        "port": int(data.get("port", 30814)),
        "sname": data.get("name", "Unnamed Server"),
        "players": int(data.get("players", 0)),
        "maxplayers": int(data.get("maxplayers", 10)),
        "map": data.get("map", "/levels/gridmap_v2/info.json"),
        "private": data.get("private", "false"),
        "version": data.get("version", ""),
        "cversion": data.get("clientversion", data.get("cversion", data.get("version", "2.0"))),
        "sdesc": data.get("desc", ""),
        "owner": key_owner,
        "location": data.get("location", "--"),
        "official": data.get("official", False),
        "playerslist": data.get("playerslist", ""),
        "pps": data.get("pps", ""),
        "tags": data.get("tags", ""),
        "modlist": data.get("modlist", ""),
        "modstotalsize": int(data.get("modstotalsize", 0)),
        "modstotal": int(data.get("modstotal", 0)),
        "last_heartbeat": now,
    }

    if existing:
        existing.update(server_entry)
        status_code = "200"
        msg = "Session resumed"
    else:
        servers.append(server_entry)
        status_code = "2000"
        msg = "Authenticated"

    save_servers(servers)

    return JSONResponse({
        "status": status_code,
        "code": "jwt_placeholder",
        "msg": msg,
    })


@app.post("/pkToUser")
async def pk_to_user(request: Request):
    """
    Authenticate a player joining a server.
    Body: {"key": "<player_public_key>", "auth_key": "<server_auth_key>", "client_ip": "<ip>"}
    Response: {"username": "...", "roles": "USER", "guest": false, "identifiers": ["beammp:<id>"]}
    """
    if is_endpoint_rate_limited(get_client_ip(request), "pkToUser", max_requests=30):
        return JSONResponse({"error": "Too many requests"}, status_code=429)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    player_key = data.get("key", "")
    if not player_key:
        return JSONResponse({"error": "Missing player key"}, status_code=400)

    # Look up the user by their public_key
    result = db_get_user_by_public_key(player_key)
    if result:
        username, user_data = result
        return JSONResponse({
            "username": username,
            "roles": user_data.get("role", "USER"),
            "guest": False,
            "identifiers": [f"beammp:{user_data.get('id', 0)}"],
        })

    # Key not found — allow as guest if you want, or reject
    # For now, allow as guest with a derived name
    guest_id = hashlib.sha256(player_key.encode()).hexdigest()[:8]
    return JSONResponse({
        "username": f"Guest-{guest_id}",
        "roles": "USER",
        "guest": True,
        "identifiers": [f"guest:{guest_id}"],
    })


# =========================================================================
# WEB UI API ENDPOINTS
# =========================================================================

@app.get("/api/status")
def api_status(request: Request):
    """Public status endpoint for the dashboard."""
    if is_endpoint_rate_limited(get_client_ip(request), "api-status"):
        return JSONResponse({"error": "Too many requests"}, status_code=429)
    servers = get_servers()
    now = time.time()
    active = [s for s in servers if now - s.get("last_heartbeat", 0) < 60]
    total_players = sum(s.get("players", 0) for s in active)
    return JSONResponse({
        "status": "online",
        "uptime_seconds": int(now - STARTUP_TIME),
        "active_servers": len(active),
        "total_players": total_players,
        "launcher_version": LAUNCHER_VERSION,
        "server_version": SERVER_VERSION,
        "backend_version": BACKEND_VERSION,
        "registered_users": db_count_users(),
    })


@app.get("/api/metrics")
def api_metrics(request: Request):
    """Return metrics time-series for dashboard graphs. Requires login."""
    if not verify_any_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    return JSONResponse({"success": True, "points": METRICS_HISTORY})


@app.post("/api/admin/login")
async def admin_web_login(request: Request):
    """Web UI login. Sets a session cookie. Works for all users; admin features gated separately."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid JSON"}, status_code=400)

    username = data.get("username", "")
    password = data.get("password", "")
    if not username or not password:
        return JSONResponse({"success": False, "message": "Username and password required"}, status_code=400)

    client_ip = get_client_ip(request)
    if is_rate_limited(client_ip):
        return JSONResponse({"success": False, "message": "Too many login attempts. Try again later."}, status_code=429)

    user = db_get_user(username)
    if not user:
        record_login_attempt(client_ip)
        return JSONResponse({"success": False, "message": "Invalid credentials"}, status_code=401)

    if not verify_password(password, user):
        record_login_attempt(client_ip)
        return JSONResponse({"success": False, "message": "Invalid credentials"}, status_code=401)

    role = user.get("role", "USER")
    token = secrets.token_hex(32)
    ADMIN_SESSIONS[token] = {"username": username, "role": role, "created": time.time()}
    response = JSONResponse({"success": True, "username": username, "role": role})
    response.set_cookie("session_token", token, httponly=True, samesite="strict", secure=True, max_age=86400)
    return response


@app.post("/api/admin/logout")
def admin_web_logout(request: Request):
    """Clear admin session."""
    token = request.cookies.get("session_token")
    if token and token in ADMIN_SESSIONS:
        del ADMIN_SESSIONS[token]
    response = JSONResponse({"success": True})
    response.delete_cookie("session_token")
    return response


@app.post("/api/register")
async def register_user(request: Request):
    """Register a new user with a single-use registration key."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid JSON"}, status_code=400)

    reg_key = data.get("registration_key", "").strip()
    username = data.get("username", "").strip()

    if not reg_key:
        return JSONResponse({"success": False, "message": "Registration key required"}, status_code=400)
    if not username:
        return JSONResponse({"success": False, "message": "Username required"}, status_code=400)
    if not validate_username(username):
        return JSONResponse({"success": False, "message": "Username must be 3-32 chars: letters, numbers, hyphens, underscores"}, status_code=400)

    client_ip = get_client_ip(request)
    if is_rate_limited(client_ip):
        return JSONResponse({"success": False, "message": "Too many attempts. Try again later."}, status_code=429)

    key_entry = db_get_registration_key(reg_key)
    if not key_entry:
        record_login_attempt(client_ip)
        return JSONResponse({"success": False, "message": "Invalid registration key"}, status_code=401)

    if db_get_user(username):
        return JSONResponse({"success": False, "message": "Username already taken"}, status_code=409)

    password = secrets.token_urlsafe(12)
    pw_hash = hash_password(password)
    pk = secrets.token_hex(32)
    pub = secrets.token_hex(16)

    if not db_create_user(username, pw_hash, "USER", private_key=pk, public_key=pub):
        return JSONResponse({"success": False, "message": "Failed to create account"}, status_code=500)

    db_mark_registration_key_used(reg_key, username)
    print(f"[REGISTER] New user '{username}' registered using key from '{key_entry['created_by']}'")

    return JSONResponse({"success": True, "message": "Account created", "username": username, "password": password})


@app.get("/api/admin/registration-keys")
def list_registration_keys(request: Request):
    """List all registration keys (admin only)."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    return JSONResponse({"success": True, "keys": db_list_registration_keys()})


@app.post("/api/admin/registration-keys")
async def create_registration_key(request: Request):
    """Generate a single-use registration key (admin only)."""
    session = verify_admin_session(request)
    if not session:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    key = secrets.token_urlsafe(24)
    db_create_registration_key(key, session["username"])
    return JSONResponse({"success": True, "key": key})


@app.delete("/api/admin/registration-keys/{key}")
def delete_registration_key(key: str, request: Request):
    """Delete a registration key (admin only, unused keys only)."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    conn = get_db()
    row = conn.execute("SELECT used FROM registration_keys WHERE key = ?", (key,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"success": False, "message": "Key not found"}, status_code=404)
    if row["used"]:
        conn.close()
        return JSONResponse({"success": False, "message": "Cannot delete a used key"}, status_code=400)
    if db_delete_registration_key(key):
        return JSONResponse({"success": True, "message": "Registration key deleted"})
    return JSONResponse({"success": False, "message": "Key not found"}, status_code=404)


@app.get("/api/admin/session")
def admin_session_check(request: Request):
    """Check if current session is valid."""
    session = verify_any_session(request)
    if session:
        return JSONResponse({"authenticated": True, "username": session["username"], "role": session["role"]})
    return JSONResponse({"authenticated": False}, status_code=401)


@app.get("/api/admin/users")
def list_users_api(request: Request):
    """List all users (admin only)."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    return JSONResponse({"success": True, "users": db_list_users()})


@app.post("/api/admin/users")
async def create_user_api(request: Request):
    """Create a user via web UI session auth."""
    admin = verify_admin_session(request)
    if not admin:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid JSON"}, status_code=400)

    username = data.get("username", "")
    password = data.get("password", "")
    role = data.get("role", "USER")
    if not username or not password:
        return JSONResponse({"success": False, "message": "Username and password required"}, status_code=400)

    if not validate_username(username):
        return JSONResponse({"success": False, "message": "Username must be 3-32 alphanumeric characters, hyphens, or underscores"}, status_code=400)
    if not validate_password(password):
        return JSONResponse({"success": False, "message": "Password must be at least 8 characters"}, status_code=400)
    if role not in ("USER", "ADM"):
        return JSONResponse({"success": False, "message": "Role must be USER or ADM"}, status_code=400)

    if db_user_exists(username):
        return JSONResponse({"success": False, "message": "User already exists"}, status_code=409)

    if not db_create_user(username, hash_password(password), role,
                          secrets.token_hex(32), secrets.token_hex(16)):
        return JSONResponse({"success": False, "message": "Failed to create user"}, status_code=500)
    return JSONResponse({"success": True, "message": f"User '{username}' created"})


@app.delete("/api/admin/users/{username}")
def delete_user_api(username: str, request: Request):
    """Delete a user (admin only, cannot delete self)."""
    admin = verify_admin_session(request)
    if not admin:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    if username == admin["username"]:
        return JSONResponse({"success": False, "message": "Cannot delete yourself"}, status_code=400)
    if not db_user_exists(username):
        return JSONResponse({"success": False, "message": "User not found"}, status_code=404)
    db_delete_user(username)
    # Invalidate any active sessions for the deleted user
    tokens_to_remove = [t for t, s in ADMIN_SESSIONS.items() if s["username"] == username]
    for t in tokens_to_remove:
        del ADMIN_SESSIONS[t]
    return JSONResponse({"success": True, "message": f"User '{username}' deleted"})


@app.patch("/api/admin/users/{username}")
async def update_user_api(username: str, request: Request):
    """Update a user's password and/or role. Admins can edit anyone; users can only change their own password."""
    session = verify_any_session(request)
    if not session:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    is_admin = session["role"] == "ADM"
    is_self = session["username"] == username

    if not is_admin and not is_self:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=403)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "Invalid JSON"}, status_code=400)

    user = db_get_user(username)
    if not user:
        return JSONResponse({"success": False, "message": "User not found"}, status_code=404)

    updates = {}
    changed = []

    new_password = data.get("password", "")
    if new_password:
        if not validate_password(new_password):
            return JSONResponse({"success": False, "message": "Password must be at least 8 characters"}, status_code=400)
        updates["password_hash"] = hash_password(new_password)
        changed.append("password")

    new_role = data.get("role", "")
    if new_role and new_role in ("USER", "ADM") and is_admin:
        if is_self and new_role != "ADM":
            return JSONResponse({"success": False, "message": "Cannot remove your own admin role"}, status_code=400)
        old_role = user.get("role", "USER")
        updates["role"] = new_role
        changed.append("role")
        # Invalidate all sessions for this user if role changed
        if old_role != new_role:
            tokens_to_remove = [t for t, s in ADMIN_SESSIONS.items() if s["username"] == username]
            for t in tokens_to_remove:
                del ADMIN_SESSIONS[t]

    if not changed:
        return JSONResponse({"success": False, "message": "Nothing to update"}, status_code=400)

    db_update_user(username, **updates)
    return JSONResponse({"success": True, "message": f"Updated {', '.join(changed)} for '{username}'"})


@app.get("/api/admin/keys")
def list_keys_api(request: Request):
    """List all generated server keys (admin only)."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    return JSONResponse({"success": True, "keys": db_get_all_keys()})


@app.post("/api/admin/keys")
async def create_key_api(request: Request):
    """Generate and persist a server auth key via web UI session auth."""
    admin = verify_admin_session(request)
    if not admin:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        data = {}

    key = secrets.token_hex(32)
    server_name = data.get("server_name", "My Server")
    owner = data.get("owner", admin["username"])

    # Validate owner exists
    if not db_user_exists(owner):
        return JSONResponse({"success": False, "message": f"User '{owner}' not found"}, status_code=404)

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not db_create_key(key, server_name, owner, admin, created_at):
        return JSONResponse({"success": False, "message": "Failed to create key"}, status_code=500)
    return JSONResponse({"success": True, "auth_key": key, "server_name": server_name, "owner": owner})


@app.delete("/api/admin/keys/{key}")
def delete_key_api(key: str, request: Request):
    """Delete a server auth key (admin only)."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    if not db_delete_key(key):
        return JSONResponse({"success": False, "message": "Key not found"}, status_code=404)
    return JSONResponse({"success": True, "message": "Key deleted"})


@app.get("/api/my/keys")
def my_keys_api(request: Request):
    """Return keys owned by the currently logged-in user."""
    session = verify_any_session(request)
    if not session:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    return JSONResponse({"success": True, "keys": db_get_keys_by_owner(session["username"])})


@app.patch("/api/my/keys/{key}")
async def rename_my_key(key: str, request: Request):
    """Rename the server_name on a key the user owns."""
    session = verify_any_session(request)
    if not session:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    info = db_get_key_info(key)
    if not info:
        return JSONResponse({"success": False, "message": "Key not found"}, status_code=404)
    if info["owner"] != session["username"] and session.get("role") != "ADM":
        return JSONResponse({"success": False, "message": "Not your key"}, status_code=403)
    data = await request.json()
    new_name = str(data.get("server_name", "")).strip()
    if not new_name or len(new_name) > 100:
        return JSONResponse({"success": False, "message": "Server name must be 1-100 characters"}, status_code=400)
    db_update_key_name(key, new_name)
    return JSONResponse({"success": True, "message": "Server name updated"})


# =========================================================================
# MOD FILE MANAGEMENT
# =========================================================================


@app.post("/api/servers/{server_id}/upload-mod")
async def upload_mod(server_id: str, request: Request):
    """Upload a mod file for a server. Admin only. Streams to disk for large files."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    servers = get_servers()
    valid = any(get_server_id(s.get("auth_key", "")) == server_id for s in servers)
    if not valid:
        return JSONResponse({"success": False, "message": "Server not found"}, status_code=404)

    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload_file = form.get("file")
        if not upload_file:
            return JSONResponse({"success": False, "message": "No file uploaded"}, status_code=400)
        filename = Path(upload_file.filename).name
        if not filename.lower().endswith(".zip"):
            return JSONResponse({"success": False, "message": "Only .zip files allowed"}, status_code=400)
        if not re.match(r'^[a-zA-Z0-9_\-. ]+\.zip$', filename):
            return JSONResponse({"success": False, "message": "Invalid filename"}, status_code=400)
        mod_dir = MOD_STORAGE_DIR / server_id
        mod_dir.mkdir(parents=True, exist_ok=True)
        file_path = mod_dir / filename
        try:
            with open(file_path, "wb") as f:
                total = 0
                while chunk := await upload_file.read(1024 * 1024):
                    total += len(chunk)
                    if total > 1024 * 1024 * 1024:
                        f.close()
                        file_path.unlink(missing_ok=True)
                        return JSONResponse({"success": False, "message": "File too large (max 1GB)"}, status_code=400)
                    f.write(chunk)
        except Exception as e:
            file_path.unlink(missing_ok=True)
            return JSONResponse({"success": False, "message": f"Upload failed: {str(e)}"}, status_code=500)
    else:
        return JSONResponse({"success": False, "message": "Use multipart/form-data"}, status_code=400)

    return JSONResponse({"success": True, "message": f"Mod '{filename}' uploaded ({total // (1024*1024)}MB)", "filename": filename})


@app.get("/api/servers/{server_id}/mods/{filename}")
def download_server_mod(server_id: str, filename: str, request: Request):
    """Download a mod file. Requires login."""
    if not verify_any_session(request):
        return JSONResponse({"success": False, "message": "Login required"}, status_code=401)
    safe_filename = Path(filename).name
    if safe_filename != filename:
        return JSONResponse({"success": False, "message": "Invalid filename"}, status_code=400)
    file_path = MOD_STORAGE_DIR / server_id / safe_filename
    try:
        file_path.resolve().relative_to(MOD_STORAGE_DIR.resolve())
    except ValueError:
        return JSONResponse({"success": False, "message": "Invalid path"}, status_code=400)
    if not file_path.exists():
        return JSONResponse({"success": False, "message": "Mod not found"}, status_code=404)
    return FileResponse(file_path, filename=safe_filename)


@app.delete("/api/servers/{server_id}/mods/{filename}")
def delete_server_mod(server_id: str, filename: str, request: Request):
    """Delete a mod file. Admin only."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    safe_filename = Path(filename).name
    if safe_filename != filename:
        return JSONResponse({"success": False, "message": "Invalid filename"}, status_code=400)
    file_path = MOD_STORAGE_DIR / server_id / safe_filename
    try:
        file_path.resolve().relative_to(MOD_STORAGE_DIR.resolve())
    except ValueError:
        return JSONResponse({"success": False, "message": "Invalid path"}, status_code=400)
    if not file_path.exists():
        return JSONResponse({"success": False, "message": "Mod not found"}, status_code=404)
    file_path.unlink()
    return JSONResponse({"success": True, "message": f"Mod '{safe_filename}' deleted"})


# =========================================================================
# BUILD DISTRIBUTION (launcher, mod, server binaries)
# =========================================================================

# Allowed build types and their expected filenames
BUILD_TYPES = {
    "launcher": "BeamMP-Launcher.exe",
    "mod": "BeamMP.zip",
    "server-windows": "BeamMP-Server.exe",
    "server-linux": "BeamMP-Server",
}
BUILDS_DIR = DATA_DIR / "builds"
BUILDS_META_FILE = BUILDS_DIR / "meta.json"

def load_builds_meta() -> dict:
    if BUILDS_META_FILE.exists():
        try:
            return json.loads(BUILDS_META_FILE.read_text())
        except Exception:
            pass
    return {}

def save_builds_meta(meta: dict):
    BUILDS_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUILDS_META_FILE.write_text(json.dumps(meta))


@app.get("/api/builds")
def list_builds(request: Request):
    """List available build files with metadata. Requires login."""
    if not verify_any_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    builds = []
    for build_type, filename in BUILD_TYPES.items():
        path = BUILDS_DIR / filename
        if path.exists():
            stat = path.stat()
            meta = load_builds_meta()
            original_name = meta.get(build_type, filename)
            builds.append({
                "type": build_type,
                "filename": original_name,
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
                "sha256": sha256_file(path),
            })
    return JSONResponse({"success": True, "builds": builds})


@app.get("/api/builds/download/{build_type}")
def download_build(build_type: str, request: Request):
    """Download a build file. Requires login."""
    if not verify_any_session(request):
        return JSONResponse({"success": False, "message": "Login required"}, status_code=401)
    if build_type not in BUILD_TYPES:
        return JSONResponse({"success": False, "message": "Invalid build type"}, status_code=400)
    if is_endpoint_rate_limited(get_client_ip(request), "downloads", max_requests=5):
        return JSONResponse({"success": False, "message": "Rate limited"}, status_code=429)
    filename = BUILD_TYPES[build_type]
    path = BUILDS_DIR / filename
    if not path.exists():
        return JSONResponse({"success": False, "message": "Build not available"}, status_code=404)
    meta = load_builds_meta()
    original_name = meta.get(build_type, filename)
    return FileResponse(path, filename=original_name)


@app.post("/api/builds/upload")
async def upload_build(request: Request):
    """Upload a build file. Admin only. Multipart form: file + type field."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return JSONResponse({"success": False, "message": "Use multipart/form-data"}, status_code=400)
    form = await request.form()
    build_type = form.get("type", "")
    if build_type not in BUILD_TYPES:
        return JSONResponse({"success": False, "message": f"Invalid type. Must be one of: {', '.join(BUILD_TYPES.keys())}"}, status_code=400)
    upload_file = form.get("file")
    if not upload_file:
        return JSONResponse({"success": False, "message": "No file uploaded"}, status_code=400)
    original_filename = Path(upload_file.filename).name if upload_file.filename else BUILD_TYPES[build_type]
    expected_filename = BUILD_TYPES[build_type]
    BUILDS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = BUILDS_DIR / expected_filename
    try:
        with open(file_path, "wb") as f:
            total = 0
            while chunk := await upload_file.read(1024 * 1024):
                total += len(chunk)
                if total > 1024 * 1024 * 1024:
                    f.close()
                    file_path.unlink(missing_ok=True)
                    return JSONResponse({"success": False, "message": "File too large (max 1GB)"}, status_code=400)
                f.write(chunk)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        return JSONResponse({"success": False, "message": f"Upload failed: {str(e)}"}, status_code=500)
    meta = load_builds_meta()
    meta[build_type] = original_filename
    save_builds_meta(meta)
    return JSONResponse({"success": True, "message": f"Build '{original_filename}' uploaded ({total // (1024*1024)}MB)", "filename": original_filename})


@app.delete("/api/builds/{build_type}")
def delete_build(build_type: str, request: Request):
    """Delete a build file. Admin only."""
    if not verify_admin_session(request):
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)
    if build_type not in BUILD_TYPES:
        return JSONResponse({"success": False, "message": "Invalid build type"}, status_code=400)
    filename = BUILD_TYPES[build_type]
    path = BUILDS_DIR / filename
    if not path.exists():
        return JSONResponse({"success": False, "message": "Build not found"}, status_code=404)
    path.unlink()
    return JSONResponse({"success": True, "message": f"Build '{filename}' deleted"})


# =========================================================================
# ROOT — Serve Web UI
# =========================================================================

@app.get("/")
def root():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return JSONResponse({"status": "ok", "service": "BeamMP Custom Backend", "version": "1.0.0"})
