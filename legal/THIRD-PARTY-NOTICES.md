# Third-Party Notices

This project incorporates material from the projects listed below. The original
copyright notices and license terms are included here in compliance with AGPL-3.0.

---

## 1. BeamMP (Lua Mod)

- **Project**: BeamMP — Bringing multiplayer to BeamNG.drive
- **Repository**: https://github.com/BeamMP/BeamMP
- **License**: GNU Affero General Public License v3.0 (AGPL-3.0)
- **Copyright**: Copyright (C) BeamMP Ltd., BeamMP team and contributors
- **Used in**: `Original mod/` directory (reference copy), modified Lua networking in `MPCoreNetwork.lua`

### What was modified

- `MPCoreNetwork.lua` — Modified to communicate with the self-hosted backend
  instead of the official BeamMP API endpoints.

### Additional notices

The BeamMP Lua mod includes third-party assets and code with their own licenses.
See `Original mod/NOTICES.md` for the full list, which includes:
- Beamlings assets by VanilleVaschnille (used with permission, all rights reserved)
- BeamNG GmbH assets under bCDDL-1.1 and MIT licenses
- Patreon Ltd. assets (Patreon wordmark)

---

## 2. BeamMP-Server

- **Project**: BeamMP-Server — Server for the BeamMP multiplayer mod
- **Repository**: https://github.com/BeamMP/BeamMP-Server
- **License**: GNU Affero General Public License v3.0 (AGPL-3.0)
- **Copyright**: Copyright (C) BeamMP Ltd., BeamMP team and contributors
- **Used in**: `BeamMP-Server/` directory

### What was modified

- Network/HTTP layer modified to authenticate against the self-hosted backend
  (`beammp-backend`) instead of the official BeamMP API at `backend.beammp.com`.
- Server compiled from modified source as a custom build.

### Upstream note on building from source

The upstream README states: *"We only allow building unmodified (original)
source code for public use."* This is a project policy statement in the README,
not a license term. The AGPL-3.0 license explicitly grants the right to modify
and redistribute under its terms (Section 2 — Basic Permissions). This project
exercises those rights while complying with all AGPL-3.0 obligations.

---

## 3. BeamMP-Launcher

- **Project**: BeamMP-Launcher — Official BeamMP Launcher
- **Repository**: https://github.com/BeamMP/BeamMP-Launcher
- **License**: GNU Affero General Public License v3.0 (AGPL-3.0)
- **Copyright**: Copyright (C) 2024 BeamMP Ltd., BeamMP team and contributors
- **Used in**: `BeamMP-Launcher/` directory

### What was modified

- Network layer modified to connect to the self-hosted backend instead of the
  official BeamMP infrastructure.
- Modified to work with the custom authentication and server-list system
  provided by `beammp-backend`.

### License notice (from upstream README)

> BeamMP Launcher, a launcher for the BeamMP mod for BeamNG.drive
> Copyright (C) 2024 BeamMP Ltd., BeamMP team and contributors.
>
> This program is free software: you can redistribute it and/or modify
> it under the terms of the GNU Affero General Public License as published
> by the Free Software Foundation, either version 3 of the License, or
> (at your option) any later version.
>
> This program is distributed in the hope that it will be useful,
> but WITHOUT ANY WARRANTY; without even the implied warranty of
> MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
> GNU Affero General Public License for more details.

---

## License Text

The full text of the GNU Affero General Public License v3.0 is included in:
- `BeamMP-Server/LICENSE`
- `BeamMP-Launcher/LICENSE`
- https://www.gnu.org/licenses/agpl-3.0.html
