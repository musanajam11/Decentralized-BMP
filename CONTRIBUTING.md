# Contributing to Decentralized-BMP

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b my-feature`
3. Make your changes
4. Test your changes (see below)
5. Commit with a clear message: `git commit -m "Add feature X"`
6. Push and open a pull request

## Project Layout

| Directory | What to Edit | Language |
|---|---|---|
| `backend/` | API server and web dashboard | Python (FastAPI) |
| `BeamMP-Launcher/src/` | Launcher client | C++ |
| `BeamMP-Server/src/` | Game server | C++ |

## Testing

### Backend

```bash
cd backend
docker compose up -d --build
# Check http://localhost:8420 for the dashboard
```

### Launcher / Server

Build with CMake (see root README for full instructions), then run against a local backend instance.

## Guidelines

- **No hardcoded domains.** All backend URLs must be read from configuration. Use `backend.yourdomain.xyz` as the placeholder default.
- **Keep the backend API compatible.** The launcher and server depend on specific endpoint contracts. Don't change endpoint paths or response formats without updating all three components.
- **AGPL-3.0 applies.** All modifications to upstream BeamMP code must be distributed under AGPL-3.0. See `legal/` for details.
- **Test with Docker.** The backend is designed to run in Docker — always verify your changes work in a container.

## Reporting Issues

Open an issue with:
- Component affected (backend, launcher, server)
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages
