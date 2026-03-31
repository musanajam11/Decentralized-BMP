# AGPL-3.0 Compliance Guide

This document outlines the obligations imposed by the GNU Affero General Public
License v3.0 and how this project meets them.

## What is AGPL-3.0?

The AGPL-3.0 is a strong copyleft free software license. It is identical to
GPL-3.0 with one additional requirement: **Section 13 (Remote Network
Interaction)** requires that users who interact with the software over a
network must be offered access to the corresponding source code.

Full text: https://www.gnu.org/licenses/agpl-3.0.html

---

## Obligations Checklist

### 1. Source Code Availability (Sections 4–6, 13)

| Requirement | Status |
|---|---|
| Complete source code for all modified AGPL components must be available | The full source is included in this repository |
| Source must include build scripts and instructions | `CMakeLists.txt`, `vcpkg.json`, and build configs are included |
| Network users must be able to obtain the source (Section 13) | Source must be offered to anyone who connects to the server or uses the launcher |

**How to comply**: If you distribute binaries or run the server publicly, you
must provide a way for users to obtain the complete corresponding source code.
Options include:
- Hosting the source in a public repository
- Including a written offer for source code valid for 3 years
- Bundling source alongside binaries

### 2. License Preservation (Section 7)

| Requirement | Status |
|---|---|
| Original LICENSE files retained | ✅ `BeamMP-Server/LICENSE` and `BeamMP-Launcher/LICENSE` preserved |
| Copyright notices preserved | ✅ Original copyright headers in source files untouched |
| AGPL-3.0 applies to the modified work | ✅ Modifications are distributed under the same license |

### 3. Modification Notices (Section 5)

| Requirement | Status |
|---|---|
| Modified files must carry prominent notices stating they were changed | ✅ Each modified file contains a MODIFIED notice in its header |
| Each modified file should state the date of change | ✅ Modification date range (2024-2026) noted in file headers; exact dates tracked via git history |
| The modified work must be licensed under AGPL-3.0 | ✅ |

**Modified files with per-file notices:**

Launcher (`BeamMP-Launcher/`):
- `src/Config.cpp` — Added configurable BackendUrl with JSON config parsing
- `src/Startup.cpp` — Update/download URLs use configurable BackendUrl
- `src/Security/Login.cpp` — Auth requests target configurable BackendUrl
- `src/Network/Http.cpp` — HTTP client instances connect to configurable BackendUrl
- `src/Network/Core.cpp` — Server list fetch uses configurable BackendUrl

Server (`BeamMP-Server/`):
- `src/Settings.cpp` — Added General_BackendUrl setting
- `include/Settings.h` — Added General_BackendUrl key to enum
- `include/Common.h` — Added backend URL resolution functions
- `src/Common.cpp` — Backend URL resolution uses configurable setting
- `src/TConfig.cpp` — BackendUrl parsed from config file and env var
- `src/TNetwork.cpp` — Player auth uses configurable BackendUrl
- `src/THeartbeatThread.cpp` — Heartbeat uses configurable BackendUrl list

Backend (`backend/`):
- `main.py` — Original work (not derived from upstream BeamMP code)

### 4. No Additional Restrictions (Section 10)

You may not impose any further restrictions on the exercise of the rights
granted by AGPL-3.0. This means:
- You cannot restrict who may use, modify, or redistribute the code
- You cannot add DRM or technical protection measures
- You cannot require royalties or fees for the license rights themselves

### 5. No Warranty (Sections 15–16)

The software is provided "as is" without warranty. This applies to both the
original BeamMP code and all modifications made in this project.

---

## Summary of Modifications

### BeamMP-Server (`BeamMP-Server/`)
- **Purpose**: Replace official backend communication with self-hosted backend
- **Scope**: Settings, config parsing, heartbeat, authentication, and URL resolution
- **Nature**: Added configurable `BackendUrl` setting (read from `ServerConfig.toml`
  or `BEAMMP_BACKEND_URL` env var) replacing hardcoded `backend.beammp.com`
- **Files modified**: `Settings.cpp`, `Settings.h`, `Common.h`, `Common.cpp`,
  `TConfig.cpp`, `TNetwork.cpp`, `THeartbeatThread.cpp`

### BeamMP-Launcher (`BeamMP-Launcher/`)
- **Purpose**: Connect to self-hosted backend instead of official infrastructure
- **Scope**: Config parsing, update checks, authentication, HTTP client, server list
- **Nature**: Added configurable `BackendUrl` (read from `Launcher.cfg` JSON)
  replacing hardcoded `backend.beammp.com`
- **Files modified**: `Config.cpp`, `Startup.cpp`, `Security/Login.cpp`,
  `Network/Http.cpp`, `Network/Core.cpp`

### BeamMP Lua Mod (`Original mod/`, `MPCoreNetwork.lua`)
- **Purpose**: Route in-game network calls to self-hosted backend
- **Scope**: Core networking Lua script
- **Nature**: Backend URL and protocol adjustments

---

## What You Can Do (Your Rights Under AGPL-3.0)

Under AGPL-3.0, you have the right to:

- ✅ **Use** the software for any purpose
- ✅ **Study** how the software works and modify it
- ✅ **Redistribute** copies of the original or modified software
- ✅ **Distribute modified versions** to others

As long as you:

- ✅ Keep the AGPL-3.0 license on all copies and derivatives
- ✅ Provide source code to all users (including network users)
- ✅ Clearly mark your modifications
- ✅ Preserve all copyright and license notices

---

## What You Cannot Do

- ❌ Distribute modified versions under a different license
- ❌ Remove or obscure copyright notices or license terms
- ❌ Distribute binaries without offering corresponding source
- ❌ Add restrictions beyond those in AGPL-3.0
- ❌ Claim the original work as solely your own

---

## Upstream Project Links

- BeamMP Organization: https://github.com/BeamMP
- BeamMP Mod: https://github.com/BeamMP/BeamMP
- BeamMP Server: https://github.com/BeamMP/BeamMP-Server
- BeamMP Launcher: https://github.com/BeamMP/BeamMP-Launcher
- BeamMP Website: https://beammp.com
- BeamMP Patreon: https://www.patreon.com/BeamMP
