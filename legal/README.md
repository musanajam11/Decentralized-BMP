# Legal & Licensing — Decentralized-BMP

This directory contains legal information about the upstream open-source
components used in this project and the obligations that apply.

## Project Overview

**Decentralized-BMP** is a modified distribution of the BeamMP multiplayer
system for [BeamNG.drive](https://www.beamng.com/). It replaces the official
BeamMP backend with a self-hosted alternative and includes modifications to the
launcher and server binaries.

## Upstream Components Used

| Component | Upstream Repository | License | Language |
|---|---|---|---|
| BeamMP (Lua mod) | https://github.com/BeamMP/BeamMP | AGPL-3.0 | Lua |
| BeamMP-Server | https://github.com/BeamMP/BeamMP-Server | AGPL-3.0 | C++ |
| BeamMP-Launcher | https://github.com/BeamMP/BeamMP-Launcher | AGPL-3.0 | C++ |

## Original Components

| Component | Description | License |
|---|---|---|
| beammp-backend | Self-hosted Python/FastAPI backend replacing the official BeamMP API | Original work |

## Key Documents

- [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) — Full attribution and
  license details for all upstream BeamMP components.
- [COMPLIANCE.md](COMPLIANCE.md) — AGPL-3.0 compliance checklist and
  obligations summary.

## Quick Summary

All three upstream BeamMP repositories are licensed under the
**GNU Affero General Public License v3.0 (AGPL-3.0)**. This is a strong
copyleft license that requires:

1. **Source availability** — The complete source code of any modified version
   must be made available to all users, including users who interact with the
   software over a network.
2. **Same license** — Modified versions must be distributed under AGPL-3.0.
3. **Prominent notice** — Modifications must be clearly marked and dated.
4. **License preservation** — The original license text and copyright notices
   must be retained.

See [COMPLIANCE.md](COMPLIANCE.md) for the full breakdown of obligations.
