# BeamMP-Launcher

The launcher is the way we communicate outside the game. It handles downloading the mod, launching the game, and creating connections to servers.

## Modifications in This Fork

This fork adds a **configurable backend URL**. Instead of connecting to the official BeamMP infrastructure, the launcher reads `BackendUrl` from `Launcher.cfg` and directs all API calls there.

### Configuration

On first run, a `Launcher.cfg` file is created with defaults. Set `BackendUrl` to your self-hosted backend:

```json
{
    "Port": 4444,
    "Build": "Default",
    "BackendUrl": "https://backend.yourdomain.xyz"
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `Port` | int | `4444` | Local port for game communication |
| `Build` | string | `"Default"` | Build channel |
| `CachingDirectory` | string | `"./Resources"` | Path for cached mod files |
| `BackendUrl` | string | `"https://backend.yourdomain.xyz"` | URL of the self-hosted backend |
| `DeleteDuplicateMods` | bool | `false` | Remove duplicate mod files |
| `Dev` | bool | `false` | Enable dev mode (verbose logging, skip downloads/updates/launch) |

### Building

Requires CMake 3.10+, a C++20 compiler, and vcpkg.

```bash
cmake -B build -S . -DCMAKE_TOOLCHAIN_FILE=../vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build build --config Release
```

Dependencies (installed via vcpkg): `cpp-httplib`, `nlohmann-json`, `curl`, `openssl`, `zlib`.

## [Getting started](https://docs.beammp.com/game/getting-started/)

## License

BeamMP Launcher, a launcher for the BeamMP mod for BeamNG.drive
Copyright (C) 2024 BeamMP Ltd., BeamMP team and contributors.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
