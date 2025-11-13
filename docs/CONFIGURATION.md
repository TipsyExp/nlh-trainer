# Configuration

The trainer backend is configured via environment variables.  All variables are optional; sensible defaults are chosen for development, but production deployments should set explicit values.

## Hand auto-advance (gating)

| Variable | Description | Default |
|---------|-------------|---------|
| `HAND_AUTO_ENABLED` | When set to `"true"`, enables the `/api/hand/auto` endpoint and causes bots to auto-advance after each human action. When `false`, `/api/hand/auto` returns HTTP `501` and the frontend must manually poll. | *Recommended:* `true` for local dev, `false` for prod |
returns HTTP `501` and the frontend must manually poll until the next decision. | `true` in development; `false` in production |

## Bot behaviour

| Variable | Description | Default |
|---------|-------------|---------|
| `BOT_MODE` | Controls whether bots act automatically.  Accepts `"heuristic"` (use built‑in heuristics) or `"none"` (no bot actions). | `"heuristic"` |
| `BOT_PROFILE` | Name of the bot policy to use.  Known profiles include `"TAG"` (tight‑aggressive) and `"CALLCHECK"`. | None |
| `BOT_MAX_STEPS` | Caps the number of bot actions performed in a single auto‑advance loop to prevent runaway behaviour. | `100` |
| `BOT_TIME_BUDGET_MS` | Maximum time in milliseconds allowed for a bot decision.  Policies exceeding this budget should return a safe fallback action. | `1000` |

## Debugging

| Variable | Description | Default |
|---------|-------------|---------|
| `ENGINE_DEBUG_HTTP` | When set to `"true"`, exposes debug endpoints that emit structured engine events and invariants.  Disable in production environments for performance. | `false` |

## Example development environment (recommended)

Create a `.env` file for local development with the following contents:

```bash
ENGINE_DEBUG_HTTP=true
BOT_MODE=heuristic
BOT_PROFILE=TAG
BOT_MAX_STEPS=100
BOT_TIME_BUDGET_MS=1000
HAND_AUTO_ENABLED=true
```

Frontend configuration should mirror the backend:

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
NEXT_PUBLIC_ENABLE_HAND_AUTO=true
NEXT_PUBLIC_DEV_TOOLS=true
```

The variables `ALLOW_DEV_AUTO` and `MAX_BOT_STEPS` have been removed. Use `HAND_AUTO_ENABLED` and `BOT_MAX_STEPS` instead.