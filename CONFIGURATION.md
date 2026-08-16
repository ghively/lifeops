# Configuration

LifeOps separates two things that are usually conflated.

| | Deployment settings | Runtime configuration |
|---|---|---|
| Examples | Ports, data directories, NornicDB URI | DeepSeek key, ElevenLabs voice, Telegram token, calendar account |
| Source | Environment variables / `.env` | LifeOps Console |
| Owner | Whoever installs LifeOps | The user, after deployment |
| Code | `core/lifeops/settings.py` | `core/lifeops/config/` |
| Storage | Process environment | Config document + SecretStore |

The split exists so that **no developer is ever blocked waiting for a user's
credential** (BUILD_SPEC sections 5 and 88). Adapters, schemas, validation,
health checks, and Console forms are all buildable without a single real key.

---

## Deployment settings

Environment variables, prefixed `LIFEOPS_`. A `.env` file in the repository root
is read if present.

| Variable | Default | Purpose |
|---|---|---|
| `LIFEOPS_NORNIC_URI` | `bolt://127.0.0.1:7687` | NornicDB Bolt endpoint |
| `LIFEOPS_NORNIC_USER` | `admin` | |
| `LIFEOPS_NORNIC_PASSWORD` | — | Generated into `nornicdb.env` |
| `LIFEOPS_NORNIC_DATABASE` | — | Named database, if used |
| `LIFEOPS_HTTP_HOST` | `127.0.0.1` | Core bind address |
| `LIFEOPS_HTTP_PORT` | `8080` | |
| `LIFEOPS_CORS_ORIGINS` | `["http://localhost:5173"]` | Console origin |
| `LIFEOPS_STATE_DIR` | `~/.local/share/lifeops` | Durable state root |
| `LIFEOPS_LOG_LEVEL` | `INFO` | |
| `LIFEOPS_LOG_JSON` | `true` | |
| `LIFEOPS_SAFE_MODE` | `false` | Boot in safe mode |

MCP server:

| Variable | Default | Purpose |
|---|---|---|
| `LIFEOPS_MCP_CLIENT_ID` | — | Client identity; `--client` overrides |
| `LIFEOPS_MCP_TRANSPORT` | `stdio` | |

Console (build time):

| Variable | Default | Purpose |
|---|---|---|
| `VITE_LIFEOPS_URL` | `http://127.0.0.1:8080` | Core base URL |
| `VITE_LIFEOPS_PORT` | `8080` | Dev-server proxy target |

---

## Runtime configuration

Set entirely in **Console → Configuration**. Every form is generated from a
provider's own field schema, served by the API — so adding a provider requires
no frontend change.

### Provider states

| State | Meaning |
|---|---|
| `not_configured` | Required fields are still missing |
| `disabled` | Complete, but switched off |
| `configured` | Complete and enabled, never health-checked |
| `healthy` | Last health check passed |
| `unhealthy` | Last health check failed |

`not_configured` and `disabled` are distinct on purpose: "I have not set this up
yet" and "I set it up and turned it off" mean different things to a human
reading the System screen. Missing settings outrank the enabled flag, because a
provider that cannot work should not merely read as "off".

### A fresh deployment

```
DeepSeek        Not configured
ElevenLabs      Not configured
Telegram        Not configured
Calendar        Disabled
Email           Disabled
Browser         Disabled
Telephony       Disabled
Local ASR/TTS   Disabled
```

The Console is fully reachable in this state, and Today, Tasks, and System all
work. This is asserted by the Phase 0 exit test, not just intended.

---

## How secrets are handled

Submitting a provider form routes secret fields straight to the SecretStore.
They never enter the configuration document and never enter NornicDB.

Reads return only:

```json
{ "api_key": { "configured": true, "fingerprint": "a1b2c3d4e5f6" } }
```

The fingerprint lets a human confirm *which* key is installed without it being
readable. Submitting an empty string clears the secret.

Updates are partial: only changed fields are sent, so editing a timeout never
requires re-entering an API key.

Details in [SECURITY.md](SECURITY.md).

---

## Configuration API

```
GET    /api/v1/config/providers                  schemas + status
GET    /api/v1/config/providers/{id}
PUT    /api/v1/config/providers/{id}             partial update
POST   /api/v1/config/providers/{id}/test        health check
POST   /api/v1/config/providers/{id}/discover    dynamic options (voices, models)
GET    /api/v1/config/system
PUT    /api/v1/config/system
GET    /api/v1/config/clients                    permissions per client
```

In Phase 0, `test` and `discover` report honestly that no adapter exists yet and
name the phase it arrives in. A Test button that fakes success is worse than one
that says "not yet" — and that behaviour is asserted in the test suite.

---

## Where configuration lives

Non-secret settings go to `~/.local/share/lifeops/config/lifeops.config.json`,
not to NornicDB.

They have to be readable *before* a database connection exists: the Console must
be able to render "NornicDB: unreachable" without first reaching NornicDB.

Writes are atomic — written to a temporary file, fsynced, then renamed — so an
interrupted write cannot truncate the document.

---

## Adding a provider

Define it in `core/lifeops/config/provider_registry.py`:

```python
MY_PROVIDER = ProviderDefinition(
    id="my_provider",
    category=ProviderCategory.MESSAGING,
    display_name="My Provider",
    summary="What it does, in one line the user will read.",
    available_in_phase=7,
    fields=[
        BooleanField("enabled", "Enabled", default=False),
        SecretField("api_key", "API key", required=True),
        SelectField("channel", "Channel", options_from="channels"),
    ],
    capabilities=["send_message", "health_check"],
)
```

Register it in `_REGISTRY`. The Console picks it up with no frontend change:
form fields, validation, state badge, and Test button all follow from the
schema.

`available_in_phase` is shown in the UI, so a provider that is visible but not
yet functional reads as planned work rather than as a bug.
