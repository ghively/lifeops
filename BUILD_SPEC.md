# Hermes LifeOps — End-to-End Engineering & Implementation Specification

**Version:** 5.0
**Date:** 2026-08-16
**Status:** Build-ready specification
**Primary assistant:** Hermes Agent
**Primary LLM:** DeepSeek V4 Flash API
**Primary persistent store:** NornicDB
**Primary portable agent interface:** Model Context Protocol (MCP)
**GUI:** Knowledge-OS frontend evolved into **LifeOps Console**
**Fastest-path hosted voice provider:** ElevenLabs
**Local accelerator:** NVIDIA RTX 3060 12 GB, prioritized for speech/modalities
**Primary implementation language:** Python for LifeOps Core; existing React/TypeScript Knowledge-OS frontend for Console

---

# 1. Executive Summary

Build one personal operating system around an existing Hermes agent.

The system is not a collection of independent agents and it is not a dashboard-first application.

The architecture is:

```text
Hermes
=
primary conversational assistant, planner, tool user, skill runner, and user-facing agent

LifeOps Core
=
portable personal domain/API layer, deterministic safety boundary, action executor,
integration layer, durable operational state interface, and shared MCP server

NornicDB
=
single application/world-model database providing graph, vector, BM25/hybrid retrieval,
temporal history, provenance, memory substrate, knowledge substrate, and operational state

LifeOps Console
=
the existing Knowledge-OS frontend evolved into the visual inspection, configuration,
approval, correction, and administration interface

DeepSeek V4 Flash API
=
main language/reasoning engine used by Hermes

ElevenLabs
=
fastest-path hosted voice provider for immediate high-quality TTS/voice setup

RTX 3060
=
local speech/modality accelerator for local ASR/TTS and optional future local modality workloads
```

The finished system must allow additional trusted clients such as Claude Code, ChatGPT-compatible MCP clients, Codex, or future agents to connect to the same LifeOps MCP interface and operate on the same personal world state, subject to client-specific permissions.

The user's data, memory, tasks, relationships, preferences, actions, and operational history belong to LifeOps, not to Hermes.

Hermes remains the primary assistant.

---

# 2. Non-Negotiable Architectural Rules

1. **One Hermes assistant.**
   - Do not create a separate "LifeOps agent."
   - Do not create a separate voice agent.
   - Voice, Telegram, web, and other interfaces must ultimately reach the same personal Hermes runtime/state.

2. **One primary application database.**
   - Use NornicDB.
   - Do not add SQLite, PostgreSQL, Qdrant, Neo4j, Redis, or another active state store by default.

3. **LifeOps Core is the authoritative application boundary.**
   - Agents do not directly mutate NornicDB.
   - The GUI does not directly mutate NornicDB.
   - External integrations do not directly mutate NornicDB.
   - All meaningful state changes pass through LifeOps domain operations.

4. **Reuse before building.**
   - If Hermes already provides a capability, use Hermes.
   - If NornicDB already provides a capability, use NornicDB.
   - If MCP already provides the transport/interface abstraction, use MCP.
   - If a small LifeOps module solves the problem, do not create a new service.

5. **Configuration must be GUI-driven.**
   - The coding agent must not stop development to ask the user for provider API keys, voice IDs, model IDs, email accounts, Telegram tokens, telephony credentials, browser endpoints, or similar runtime configuration.
   - The coding agent implements configuration schemas, adapters, validation, health checks, and GUI forms.
   - The user configures real provider values after deployment from LifeOps Console.
   - Development and CI use fake/mock/test configuration where needed.

6. **No unverified success.**
   - An external action is not complete merely because the model says it is.
   - Completion requires evidence from the target system.

7. **No infrastructure for hypothetical future problems.**
   - Additional systems require a demonstrated need and an explicit architectural decision.

---

# 3. Full Target Architecture

```text
                                      USER
                                       │
             ┌─────────────────────────┼──────────────────────────┐
             │                         │                          │
          Telegram                   Voice                 LifeOps Console
             │                         │                          │
             │                   ┌─────┴─────┐                    │
             │                   │Voice Bridge│                   │
             │                   └─────┬─────┘                    │
             │                         │                          │
             └─────────────────────────┼──────────────────────────┘
                                       │
                                  ┌────▼────┐
                                  │ HERMES  │
                                  └────┬────┘
                                       │
                      ┌────────────────┼─────────────────┐
                      │                │                 │
                      ▼                ▼                 ▼
                 DeepSeek API     MemoryProvider     LifeOps MCP
                                                        │
                                            ┌───────────▼───────────┐
                                            │     LifeOps Core      │
                                            └───────────┬───────────┘
                                                        │
                       ┌────────────────────────────────┼─────────────────────────────┐
                       │                                │                             │
                  Domain/Policy                    Integrations                    NornicDB
                       │                                │                             │
                       │                   ┌────────────┼─────────────┐               │
                       │                   │            │             │               │
                    Actions              Email       Calendar      Browser            │
                    Approval               │            │             │               │
                    Tasks                Shopping    Telephony       Web               │
                    Waiting                                                            │
                    Config                                                             │
                    Audit                                         ┌────────────────────┼──────────────────┐
                                                                  │                    │                  │
                                                                Graph               Vector            Temporal
                                                                  │                    │                  │
                                                                  └────────────── WORLD MODEL ────────────┘
```

Optional additional clients:

```text
Claude Code ─────┐
ChatGPT MCP ─────┼────► LifeOps MCP ─────► LifeOps Core ─────► NornicDB
Codex ───────────┤
Future Agent ────┘
```

All clients see the same underlying LifeOps state.

Permissions may differ by client identity.

---

# 4. What LifeOps Core Is

LifeOps Core is a headless Python application containing:

- MCP server
- HTTP API for LifeOps Console
- WebSocket/event stream for live Console updates
- domain models
- deterministic state transitions
- authorization and risk policy
- approval validation
- action execution
- idempotency
- verification
- integration adapters
- Nornic repository implementation
- runtime configuration service
- secret-store abstraction
- lightweight due-work processing
- audit/provenance recording
- memory API used by the Hermes MemoryProvider

LifeOps Core is **not**:

- another LLM agent
- an agent planner
- an agent swarm
- an orchestration framework
- another vector database
- another graph layer
- another context-engine product
- a generic automation platform

---

# 5. What Hermes Owns

Hermes remains responsible for:

- conversation
- reasoning
- planning
- deciding which semantic tools to call
- native skills
- SOUL/personality
- user interaction
- conversational context
- native web research where appropriate
- native cron where appropriate
- webhook-triggered runs where appropriate
- Telegram gateway
- memory-provider lifecycle integration
- tool discovery/progressive disclosure
- invoking LifeOps MCP operations

LifeOps must not recreate these facilities merely to centralize them.

---

# 6. What NornicDB Owns

Use NornicDB for capabilities it already provides:

- graph nodes
- graph relationships
- property graph queries
- vectors
- embeddings where suitable
- BM25/full-text
- hybrid retrieval
- graph expansion/traversal
- temporal/historical state
- transaction support
- provenance/history
- constraints
- persistent operational entities
- memories
- document metadata and extracted content
- relationships between personal-world entities
- action records
- approvals
- task state
- waiting state
- workflow continuation state

Do not build separate versions of:

- vector search
- graph search
- memory decay machinery already supported by Nornic
- graph relationship discovery already supported by Nornic
- full-text search
- temporal history database
- Qdrant integration
- Neo4j integration

unless the implemented Nornic capability is proven insufficient.

---

# 7. Why LifeOps MCP Exists Instead of Exposing Raw Nornic MCP

Agents must work in human/domain concepts, not raw database concepts.

Wrong:

```text
run_cypher()
create_node()
delete_relationship()
raw_vector_search()
set_property()
```

Correct:

```text
get_preferences()
create_task()
find_provider()
record_service_request()
find_calendar_availability()
prepare_appointment_booking()
commit_appointment_booking()
prepare_payment()
commit_payment()
```

A raw graph write cannot safely encode:

- authorization
- state-machine validity
- approval requirements
- idempotency
- external API execution
- verification
- audit provenance
- action retries

LifeOps Core must.

---

# 8. Repository Structure

Use a monorepo.

```text
lifeops/
│
├── README.md
├── BUILD_SPEC.md
├── ARCHITECTURE.md
├── DATA_MODEL.md
├── MCP_API.md
├── SECURITY.md
├── VOICE.md
├── OPERATIONS.md
├── TESTING.md
├── DISASTER_RECOVERY.md
├── AGENTS.md
├── CLAUDE.md
├── pyproject.toml
├── Makefile
│
├── core/
│   └── lifeops/
│       ├── main.py
│       │
│       ├── api/
│       │   ├── http.py
│       │   ├── websocket.py
│       │   └── schemas.py
│       │
│       ├── mcp/
│       │   ├── server.py
│       │   ├── tools/
│       │   └── resources/
│       │
│       ├── domain/
│       │   ├── people.py
│       │   ├── households.py
│       │   ├── preferences.py
│       │   ├── tasks.py
│       │   ├── waiting.py
│       │   ├── providers.py
│       │   ├── appointments.py
│       │   ├── events.py
│       │   ├── assets.py
│       │   ├── service_requests.py
│       │   ├── bills.py
│       │   ├── shopping.py
│       │   ├── actions.py
│       │   ├── approvals.py
│       │   └── configuration.py
│       │
│       ├── repositories/
│       │   ├── interfaces.py
│       │   └── nornic/
│       │       ├── client.py
│       │       ├── people.py
│       │       ├── preferences.py
│       │       ├── tasks.py
│       │       ├── memory.py
│       │       └── ...
│       │
│       ├── memory/
│       │   ├── api.py
│       │   ├── policy.py
│       │   └── schemas.py
│       │
│       ├── policy/
│       │   ├── risks.py
│       │   ├── authority.py
│       │   ├── approvals.py
│       │   └── capabilities.py
│       │
│       ├── actions/
│       │   ├── service.py
│       │   ├── outbox.py
│       │   ├── idempotency.py
│       │   └── verification.py
│       │
│       ├── integrations/
│       │   ├── calendar/
│       │   ├── email/
│       │   ├── browser/
│       │   ├── telephony/
│       │   ├── shopping/
│       │   └── payments/
│       │
│       ├── config/
│       │   ├── service.py
│       │   ├── provider_registry.py
│       │   └── validation.py
│       │
│       ├── secrets/
│       │   ├── interface.py
│       │   ├── local_encrypted.py
│       │   └── bitwarden.py
│       │
│       ├── worker/
│       │   └── due_work.py
│       │
│       └── observability/
│           ├── logging.py
│           └── tracing.py
│
├── console/
│   ├── [migrated Knowledge-OS frontend]
│   └── ...
│
├── hermes/
│   ├── memory_provider/
│   │   └── nornic_lifeops/
│   ├── skills/
│   ├── bootstrap/
│   └── config_templates/
│
├── voice/
│   ├── bridge/
│   ├── providers/
│   │   ├── elevenlabs/
│   │   ├── local_tts/
│   │   └── local_asr/
│   ├── audio/
│   └── tests/
│
├── deploy/
│   ├── compose.yaml
│   ├── compose.gpu.yaml
│   └── systemd/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── policy/
│   ├── persistence/
│   ├── voice/
│   └── chaos/
│
├── changes/
│   └── requests/
│
└── scripts/
    ├── bootstrap.sh
    ├── healthcheck.sh
    ├── backup.sh
    ├── restore-test.sh
    └── dev.sh
```

Do not create every directory immediately if the phase does not use it.

The layout above is the target structure, not permission to scaffold unused systems.

---

# 9. Knowledge-OS → LifeOps Console Migration

The existing Knowledge-OS frontend is the foundation.

Do not build a second GUI.

## 9.1 Keep

Preserve and adapt the existing:

- React/TypeScript application shell
- responsive sidebar
- top bar
- theme system
- Tailwind styling
- Radix components
- React Query
- Zustand where still useful
- authentication UI patterns
- WebSocket client patterns
- PWA behavior
- task UI patterns
- file UI patterns
- search UI patterns
- system/log UI patterns
- settings framework
- outliner/editor where useful for Knowledge

## 9.2 Remove or replace backend assumptions

Remove the existing architectural dependency on:

- SQLite as canonical state
- Qdrant
- custom embedding service
- custom context builder
- custom agent runtime
- OpenClaw-specific agent runtime
- custom agent memory runtime
- custom agent scheduler when Hermes cron already fits
- custom MCP server management where it duplicates Hermes/LifeOps configuration

The existing backend can be mined for reusable code patterns, but LifeOps Core becomes the authoritative backend.

## 9.3 Existing UI mapping

```text
Knowledge-OS Today
→ LifeOps Today

Knowledge-OS Inbox
→ Needs Attention / Waiting

Knowledge-OS Tasks
→ LifeOps durable Tasks

Knowledge-OS Files
→ LifeOps Files / Knowledge corpus

Knowledge-OS Search
→ LifeOps universal search backed by Nornic

Knowledge-OS Notes/Outliner
→ Knowledge

Knowledge-OS Agents
→ Hermes

Knowledge-OS Logs
→ Activity

Knowledge-OS Settings
→ LifeOps Configuration

New
→ World

New
→ Memory

New
→ Approvals
```

---

# 10. Final Console Navigation

Initial navigation:

```text
LIFEOPS

Today
Needs Attention
Waiting

LIFE
  Tasks
  Calendar

WORLD
  World
  Knowledge
  Files
  Memory

HERMES
  Hermes
  Activity

SYSTEM
  Configuration
  System
```

Do not create top-level pages for every entity type.

People, Providers, Assets, Household, and other entities should initially be browsable through **World**, universal search, related-entity panels, and contextual views.

Add dedicated entity collections later only if actual usage demonstrates they improve navigation.

---

# 11. Today Screen

Today is the default Console screen.

Purpose:

> Show what requires attention, what Hermes is doing, what is waiting, and what matters today.

Example:

```text
TODAY
Sunday, August 16

NEEDS YOU
────────────────────────────────────────────
Electrician booking
Thursday 1–3 PM · $89
Approval required
                                  [Review]

Grocery order
$128.42
Approval required
                                  [Review]

IN PROGRESS
────────────────────────────────────────────
Dentist appointment
Waiting for office response · 2h

Land Rover service
Researching providers

TODAY
────────────────────────────────────────────
10:30  Dentist
14:00  Pickup

RECENTLY COMPLETED
────────────────────────────────────────────
✓ Electric bill verified
✓ Grocery list prepared
```

This is a visual surface for LifeOps state.

It is not a replacement for talking to Hermes.

---

# 12. Needs Attention

Only show items requiring human participation.

Categories:

- approval
- clarification
- MFA
- decision
- unexpected price/term change
- failed external action
- security warning
- conflict the agent cannot resolve safely

Avoid putting routine informational notifications here.

The goal is to minimize interruption.

---

# 13. Waiting

Show work blocked on another person, organization, service, or future event.

Each item displays:

- subject
- task/workflow
- waiting on
- waiting since
- expected response time
- next follow-up
- follow-up count
- escalation state

Example:

```text
ABC Electric
Waiting for availability
2 hours

Pediatrician
Waiting for callback
2 days
Follow-up tomorrow

Insurance quote
Expected Monday
```

---

# 14. Tasks

Canonical task states:

```text
CAPTURED
PLANNED
READY
EXECUTING
WAITING_EXTERNAL
NEEDS_APPROVAL
VERIFYING
COMPLETED
BLOCKED
FAILED
CANCELLED
```

The existing Knowledge-OS Tasks UI should be adapted to these states.

Task fields:

```yaml
id:
title:
description:
state:
priority:
created_at:
updated_at:
due_at:
owner_entity_id:
assigned_client:
current_action:
waiting_item_id:
verification_required:
verification_state:
related_entity_ids:
source:
```

LifeOps validates state transitions.

LLMs do not arbitrarily assign impossible transitions.

---

# 15. World Screen

This is the visual Nornic world model.

Use an interactive graph library appropriate for the existing React stack; React Flow is acceptable.

Display:

- entities
- relationships
- entity type
- key current facts
- status
- graph neighborhood

Example:

```text
                         Gene
                       /      \
                 MEMBER_OF    PREFERS
                    │             │
                Household     After 10 AM
              /     │      \
          Vehicle  Home    Provider
             │      │         │
        Land Rover Outlet  ABC Electric
```

Requirements:

- zoom
- pan
- fit view
- type filters
- relationship filters
- search-to-node
- expand neighborhood
- collapse branch
- temporal/current view
- right-side entity inspector
- provenance/source links

Do not expose raw database editing from the graph.

Corrections use LifeOps domain operations.

---

# 16. Entity Inspector

Reusable side panel for any world entity.

Show:

- canonical name
- entity type
- current facts
- relationships
- relevant tasks
- relevant waiting items
- documents
- memories
- activity/history
- source/provenance

Example:

```text
LAND ROVER

TYPE
Vehicle

CURRENT
Insurance     Progressive
Mileage       114,203
Registration  Nov 2026

RELATED
ABC Auto
Progressive
Household

TASKS
Oil change · Due soon

DOCUMENTS
2026-insurance.pdf
service-invoice.pdf

HISTORY
...
```

---

# 17. Memory Screen

Purpose:

> Make persistent AI memory inspectable and correctable.

Views:

- Preferences
- Personal facts
- Relationships
- Episodic memories
- Semantic memories
- Procedures/routines
- Invalidated/superseded history

Each memory shows:

```yaml
id:
subject:
type:
content:
source_type:
source_id:
confidence:
importance:
observed_at:
created_at:
valid_from:
valid_to:
supersedes:
related_entities:
```

Actions:

- Correct
- Invalidate
- Supersede
- View source
- View relationships

Never directly modify protected operational state via memory correction.

---

# 18. Knowledge and Files

Keep human/reference knowledge distinct from personal memory.

Examples:

- insurance policies
- school handbooks
- contracts
- receipts
- service manuals
- warranties
- quotes
- household notes
- checklists
- user-written procedures

Actual binary files remain in file/object storage.

Nornic stores:

- document entity
- metadata
- storage reference
- extracted text
- chunks where needed
- embeddings
- relationships
- provenance

Initial extraction should remain simple.

Do not deploy a heavyweight document-processing stack until required by real documents.

---

# 19. Universal Search

Search across:

- people
- providers
- assets
- tasks
- appointments
- events
- memory
- documents
- knowledge
- bills
- actions
- historical facts

Use Nornic capabilities first:

```text
query
 ↓
hybrid semantic/BM25 retrieval
 ↓
graph relationship expansion when useful
 ↓
temporal/current-state filtering
 ↓
compact ranked result
```

Example result grouping:

```text
PEOPLE
Alex Rivera

PROVIDERS
ABC Electric

TASKS
Repair living room outlet

MEMORIES
ABC Electric previously serviced...

DOCUMENTS
ABC Electric invoice.pdf

ASSETS
Living Room Outlet
```

---

# 20. Hermes Screen

Do not reproduce a second agent platform.

Show the actual personal Hermes system:

- online/offline
- active profile
- primary model provider
- current model
- current activity
- LifeOps MCP status
- memory-provider status
- voice-provider status
- Telegram status
- recent high-level actions
- optional embedded conversation panel
- current cron/routine overview
- active skills summary

Do not rebuild:

- agent templates
- arbitrary agent factory
- separate scheduling platform
- separate custom memory runtime
- separate agent orchestration engine

---

# 21. Activity Screen

Human-readable audit trail first.

Example:

```text
10:32
Hermes searched previous electricians.

10:33
ABC Electric identified as a previous provider.

10:34
Provider contact started.

10:38
Availability received: Thursday 1–3 PM.

10:38
Booking approval requested.
```

Expandable technical detail:

- trace ID
- task ID
- client ID
- tool
- risk class
- duration
- action ID
- integration response metadata
- verification evidence

---

# 22. Configuration Is a First-Class LifeOps Feature

The system must be configurable after installation without editing source files or asking the coding agent to inject credentials.

Configuration comprises:

1. **Non-secret configuration**
   - stored through LifeOps configuration APIs
   - persisted in Nornic or a LifeOps config document as appropriate

2. **Secrets**
   - never stored in Nornic
   - stored through a SecretStore interface

3. **Provider definitions**
   - registered in code
   - expose schemas consumed dynamically by the Console

Example conceptual provider definition:

```python
ProviderDefinition(
    id="elevenlabs",
    category="voice_tts",
    fields=[
        SecretField("api_key", required=True),
        SelectField("voice_id", options_from="voices"),
        SelectField("model_id", options_from="models"),
        NumberField("stability"),
        NumberField("similarity_boost"),
        NumberField("speed"),
    ],
    capabilities=[
        "tts",
        "streaming_tts"
    ]
)
```

The Console renders configuration forms from these schemas.

Do not hardcode a different settings page for every provider unless custom UX materially helps.

---

# 23. First-Run Setup Wizard

On a fresh deployment, navigating to LifeOps Console opens a guided setup.

The coding agent does not ask these questions during development.

The deployed GUI does.

Suggested wizard:

## Step 1 — System

- LifeOps display name
- timezone
- household/user identity
- optional local network URL

Defaults should be sensible and editable later.

## Step 2 — Hermes

- Hermes endpoint/profile detection
- connectivity test
- display detected state

Where possible auto-discover local Hermes.

## Step 3 — Main Model

Preset:

```text
DeepSeek
```

Fields:

- API key
- API endpoint
- model
- optional timeout
- optional max tokens
- optional fallback

Provide a **Test connection** button.

## Step 4 — Voice

Offer:

```text
Recommended Quick Setup
ElevenLabs

Local / Advanced
RTX 3060 local providers

Disabled
```

The user can skip voice and return later.

## Step 5 — Messaging

- Telegram
- disabled initially if not configured

## Step 6 — Productivity

- Calendar
- Email

Can be skipped.

## Step 7 — Review

Show:

- connected providers
- missing optional integrations
- health state

Then launch Today.

No configuration choice should block the application unless it is absolutely required to boot the core.

---

# 24. Secret Storage

Implement:

```python
class SecretStore:
    get(name)
    set(name, value)
    delete(name)
    exists(name)
```

Initial backends:

## LocalEncryptedSecretStore

Default for easiest setup.

Requirements:

- AES-GCM or equivalent authenticated encryption
- randomly generated master key
- master key stored outside Git repository
- mode 0600
- secret ciphertext separate from Nornic
- never include decrypted values in API responses
- GUI shows only configured/not configured and optional last-four/fingerprint where appropriate

## BitwardenSecretStore

Optional later/production preference.

Configure from the GUI.

The existence of Bitwarden integration must not make first deployment dependent on Bitwarden.

Never log:

- API keys
- OAuth refresh tokens
- cookies
- passwords
- card information
- MFA codes

---

# 25. Configuration API

Minimum operations:

```text
GET  /api/config/providers
GET  /api/config/providers/{provider}
PUT  /api/config/providers/{provider}
POST /api/config/providers/{provider}/test
POST /api/config/providers/{provider}/discover
GET  /api/config/system
PUT  /api/config/system
```

Secret fields sent in a configuration update are immediately routed to SecretStore.

When reading configuration:

```json
{
  "api_key": {
    "configured": true
  }
}
```

Never return the key.

---

# 26. Configuration Console

Top-level sections:

```text
Configuration

AI
  Main Model
  Auxiliary Models

Voice
  Voice Mode
  ElevenLabs
  Local ASR
  Local TTS

Messaging
  Telegram

Productivity
  Calendar
  Email

Automation
  Browser
  Telephony

Storage
  Nornic
  Files
  Backups

Security
  Secrets
  Client Access
  Approval Policy

Advanced
  MCP
  Logging
```

Every provider card shows:

- Enabled/Disabled
- Connected/Disconnected
- configured model/account/voice
- last successful health check
- Test
- Configure
- optional advanced fields

---

# 27. ElevenLabs Voice Provider

ElevenLabs is the **quickest setup option**, not the only voice architecture.

Purpose:

- get natural streamed speech working quickly
- avoid blocking the main project on local TTS tuning
- provide a quality baseline
- permit later switch to local RTX-accelerated speech without changing Hermes/LifeOps architecture

The adapter must support streaming TTS.

Use the official API/SDK rather than screen automation.

Provider capabilities:

```text
text_to_speech
stream_text_to_speech
list_voices
list_models
health_check
```

Configuration fields:

```yaml
enabled:
api_key: secret
voice_id:
model_id:
output_format:
stability:
similarity_boost:
speed:
streaming: true
```

Default low-latency preset:

```text
Provider: ElevenLabs
Mode: streaming
Model: low-latency/Flash model supported by current ElevenLabs API
```

The implementation should discover current models through the provider API instead of permanently hardcoding one model identifier.

The Console must allow selecting available voices returned by ElevenLabs.

Buttons:

```text
Test connection
Refresh voices
Preview voice
Set as default
```

Voice preview:

- sends sample text
- plays returned audio in browser
- does not require Hermes

---

# 28. Voice Provider Abstraction

Do not hardwire Hermes directly to ElevenLabs.

```python
class TTSProvider:
    async def synthesize(text, options): ...
    async def stream(text_stream, options): ...
    async def health(): ...

class ASRProvider:
    async def transcribe(audio): ...
    async def stream(audio_stream): ...
    async def health(): ...
```

Implement:

```text
ElevenLabsTTSProvider

LocalTTSProvider
LocalASRProvider
```

Optional future:

```text
ElevenLabsASRProvider
```

if it offers a practical benefit.

Provider selection comes from LifeOps configuration.

---

# 29. Voice Modes

Console configuration:

```text
VOICE MODE

Quick Cloud
  ASR: configurable
  TTS: ElevenLabs

Hybrid Recommended
  ASR: RTX 3060 local
  TTS: ElevenLabs

Local
  ASR: RTX 3060 local
  TTS: RTX 3060 local
```

The user can switch without changing Hermes.

The **Hybrid Recommended** path is likely the best practical early configuration:

```text
microphone
 ↓
local streaming ASR
 ↓
Hermes
 ↓
DeepSeek
 ↓
streamed text
 ↓
ElevenLabs streaming TTS
 ↓
speaker
```

Later:

```text
ElevenLabs TTS
      ↓ replace
local TTS
```

without architecture changes.

---

# 30. Local ASR/TTS Candidates

Keep candidates configurable.

ASR candidates:

- faster-whisper large-v3-turbo
- faster-whisper distil-large-v3
- NVIDIA streaming ASR candidate if supported well on target hardware

TTS candidates:

- Qwen3-TTS 1.7B
- Qwen3-TTS 0.6B
- Chatterbox Turbo
- Kokoro fallback/reference

Do not make implementation completion depend on selecting the final winner.

Provider/model selection occurs through Console after supported adapters exist.

---

# 31. RTX 3060 Resource Priority

During active voice:

```text
Priority 0 — TTS
Priority 1 — ASR
Priority 2 — audio/turn-detection models
Priority 3 — background embeddings or optional modality work
Priority 4 — optional fallback local LLM
```

Do not allow background memory processing to make conversation unusable.

---

# 32. Voice Bridge

One Hermes.

```text
microphone / SIP
      ↓
ASR provider
      ↓
Voice Bridge
      ↓
same Hermes runtime
      ↓
DeepSeek + LifeOps
      ↓
streamed text response
      ↓
TTS provider
      ↓
audio
```

Required:

- streaming ASR
- partial transcripts
- endpointing
- Hermes streaming response
- phrase/clause TTS chunking
- interruption/barge-in
- output cancellation
- session continuity
- same LifeOps/MCP state as text interface

Do not create voice-only memory.

---

# 33. Voice Latency Objectives

Measure:

```text
end of user speech
→ first audible assistant response
```

Targets:

```text
p50 <= 700 ms
p95 <= 1.2 s
p99 <= 1.7 s
```

Barge-in:

```text
audible output stop p95 <= 150 ms
```

These are engineering goals, not claims about guaranteed provider behavior.

Instrument:

- ASR finalization
- Hermes request start
- LLM first token
- first TTS chunk submitted
- first audio received
- first audio played
- interruption detect
- playback stop

---

# 34. MCP Client Identity

Every non-local/portable agent request must resolve to a client identity.

Examples:

```yaml
client_id: hermes-personal
role: primary_assistant
```

```yaml
client_id: claude-code
role: engineering_assistant
```

```yaml
client_id: chatgpt
role: interactive_assistant
```

Do not infer authority from model/provider name alone.

---

# 35. Capability Manifest

LifeOps policy maps clients to capabilities.

Example:

| Capability | Hermes | Interactive MCP client | Coding agent |
|---|---:|---:|---:|
| Read world state | Yes | Yes | Yes |
| Search memory | Yes | Yes | Yes |
| Search knowledge | Yes | Yes | Yes |
| Create task | Yes | Yes | Yes |
| Update ordinary preference | Yes | Yes | No default |
| External email | Policy | Policy | No |
| Appointment booking | Approval | Approval | No |
| Shopping checkout | Approval | Approval | No |
| Financial payment | Approval | Block/Approval | No |
| Modify source repository | No | No | Repo-scoped only |

The Console allows inspecting client permissions.

Avoid building a huge policy language.

Use explicit capability maps and deterministic policy functions.

---

# 36. World Model

Initial canonical entity types:

```text
Person
Household
Preference
Task
WaitingItem
Provider
Appointment
Event
Asset
ServiceRequest
Bill
ShoppingList
Action
Approval
Memory
Knowledge
Document
WorkflowTemplate
```

Only add types required by real workflows.

---

# 37. Canonical IDs

Every entity receives an application-generated stable ID.

Examples:

```text
person_gene
household_primary
provider_abc_electric
asset_living_room_outlet
task_<ulid>
appointment_<ulid>
```

External provider identifiers are properties.

Display names are never canonical identifiers.

---

# 38. Identity Handling

Do not build a separate "entity resolver service."

On ingestion:

```text
1. explicit LifeOps ID match
2. stable external identifier match
3. verified email/phone/provider-account match
4. otherwise create entity
5. flag meaningful ambiguity for user/Hermes correction
```

Use Nornic graph/search capability where helpful.

Only add more sophisticated identity logic when actual duplicate patterns require it.

---

# 39. Core Relationships

Initial:

```text
MEMBER_OF
RELATED_TO
PREFERS
OWNS
USES_PROVIDER
ASSIGNED_TO
ABOUT
WITH_PROVIDER
FOR_ASSET
WAITING_ON
REQUIRES_APPROVAL
AUTHORIZES
CREATED_BY
REQUESTED_BY
EXECUTED_BY
VERIFIED_BY
DERIVED_FROM
SUPERSEDES
RELATED_MEMORY
REFERENCES
```

Do not attempt to predefine every relationship in a human life.

---

# 40. Temporal State

Changing facts should preserve history.

Example:

```text
Preference A
value: appointments after 10
valid_from: 2026-08-16
valid_to: null
```

Replacement:

```text
Preference A
valid_to: 2027-03-02

Preference B
value: appointments after 9
valid_from: 2027-03-02

Preference B ─SUPERSEDES→ Preference A
```

Use Nornic temporal/history capabilities rather than creating a parallel history store.

---

# 41. Repository Abstraction

LifeOps domain code must not scatter Cypher queries throughout the codebase.

Interfaces:

```python
class PersonRepository: ...
class PreferenceRepository: ...
class TaskRepository: ...
class MemoryRepository: ...
class ActionRepository: ...
```

Implementation:

```text
NornicPersonRepository
NornicPreferenceRepository
NornicTaskRepository
NornicMemoryRepository
...
```

Benefits:

- Nornic remains replaceable
- domain tests can use fakes
- agent API remains stable
- raw graph details do not leak through LifeOps

Do not create a generic mega-repository.

Repositories should follow domain boundaries.

---

# 42. Memory Architecture

Use:

```text
Hermes built-in USER.md / MEMORY.md
+
Nornic-backed external Hermes MemoryProvider
```

Built-in Hermes memory retains:

- critical identity
- extremely important standing preferences
- key conversational instructions
- human-readable assistant context

Nornic-backed memory stores:

- episodic memories
- semantic personal facts
- preferences
- relationship context
- learned routines
- related evidence
- temporal history
- provenance

---

# 43. Thin Hermes MemoryProvider

Implement an official Hermes MemoryProvider plugin.

Flow:

```text
Hermes
 ↓
LifeOpsMemoryProvider
 ↓
LifeOps memory API
 ↓
NornicDB
```

Core operations:

```text
prefetch
sync_turn
remember/store
search/recall
invalidate/forget where supported
session-end extraction hook
```

The plugin must remain thin.

Do not implement a second memory database or second domain model in the plugin.

---

# 44. Memory Safety

Automatic memory may create:

- observation
- episodic memory
- semantic association
- conversational summary
- low-risk inferred preference candidate

Automatic memory may not:

- approve an action
- mark a payment complete
- consume approval
- modify authorization policy
- rewrite verified task completion
- alter idempotency state
- grant financial/legal/medical authority

Rule:

> **Memory can observe the world. It cannot rewrite transactional reality.**

---

# 45. Memory Provenance

Memory fields:

```yaml
id:
subject_id:
type:
content:
source_type:
source_id:
observed_at:
created_at:
confidence:
importance:
valid_from:
valid_to:
supersedes:
entity_ids:
```

Source types:

```text
user_explicit
user_inferred
conversation
email
calendar
document
website
phone_call
system
agent
```

---

# 46. Trust Hierarchy

Default authority:

```text
USER EXPLICIT
  ↓
VERIFIED SYSTEM STATE
  ↓
TRUSTED FIRST-PARTY PROVIDER
  ↓
USER-APPROVED DOCUMENT
  ↓
EXTERNAL MESSAGE
  ↓
PUBLIC WEBSITE
  ↓
MODEL INFERENCE
```

External content creates evidence.

It does not create user authority.

---

# 47. Memory Promotion

Do not save every utterance permanently.

Durable candidates include:

- explicit preference
- recurring fact
- important relationship
- confirmed provider history
- durable household procedure
- significant life/admin event
- frequently reused knowledge

Avoid storing:

- conversational filler
- temporary speculation
- unverified web claims as user facts
- duplicate summaries
- secrets

Use Nornic's relevant memory scoring/decay capabilities before implementing a custom memory-scoring platform.

---

# 48. MCP Resources

Read-oriented context should use resources where convenient.

Suggested:

```text
lifeops://me
lifeops://today
lifeops://household
lifeops://waiting
lifeops://approvals
lifeops://entity/{id}
lifeops://task/{id}
lifeops://provider/{id}
```

Do not turn every read into a state-changing tool.

---

# 49. Initial MCP Tools

Phase 0 exposes exactly:

```text
get_person
get_preferences
save_preference
create_task
list_tasks
```

Nothing else until the spine is proven.

---

# 50. Expanded Read Tools

Later:

```text
get_person
find_person
get_preferences

get_task
list_tasks
list_waiting_items

get_provider
find_provider

get_asset
list_assets

get_appointment
list_appointments

get_bill
list_bills

search_memory
search_knowledge
get_related_entities
get_entity_history
```

---

# 51. Expanded Action Tools

Low-risk:

```text
save_preference
create_task
update_task
create_waiting_item
record_provider
record_asset
create_calendar_hold
```

External:

```text
send_email
request_quote
book_appointment
cancel_appointment
place_phone_call
build_grocery_cart
submit_grocery_order
prepare_payment
commit_payment
```

Tools are narrow and semantic.

Avoid `do_action`, `browser_action`, or `execute_anything`.

---

# 52. Context Retrieval

Do not initially build a separate Context Builder service.

LifeOps can provide a small context helper/module using Nornic retrieval:

```text
query/intention
 ↓
Nornic hybrid retrieval
 ↓
optional graph expansion
 ↓
current/temporal filters
 ↓
compact context result
```

If this eventually needs sophisticated intent-dependent orchestration, improve it inside LifeOps.

Do not preemptively create another service.

---

# 53. Task Completion Semantics

External tasks may become `COMPLETED` only when evidence exists.

Examples:

- appointment confirmation ID
- calendar event ID
- provider response
- message send confirmation
- order confirmation
- payment confirmation
- external API verified status

Without evidence:

```text
VERIFYING
```

or:

```text
WAITING_EXTERNAL
```

not `COMPLETED`.

---

# 54. WaitingItem Schema

```yaml
id:
task_id:
subject:
waiting_on_entity_id:
waiting_since:
expected_by:
next_action_at:
followup_count:
max_followups:
status:
last_contact_at:
```

A message being sent usually means the task moves to `WAITING_EXTERNAL`.

---

# 55. Lightweight Durable Continuation

Do not introduce Temporal initially.

Store durable continuation state in Nornic:

```text
state
next_action
wake_at
waiting_event
attempt_count
lease_owner
lease_until
```

A small LifeOps worker:

```text
query due items
 ↓
claim lease
 ↓
perform deterministic continuation or wake Hermes
 ↓
persist result
```

Use Hermes cron/webhooks for natural time/event-driven wakeups where appropriate.

---

# 56. Risk Classes

```text
R0 — Read only
R1 — Local/reversible
R2 — External communication
R3 — External commitment
R4 — Financial/legal/medical commitment
```

Defaults:

| Action | Risk | Default |
|---|---:|---|
| Read state | R0 | Automatic |
| Search memory | R0 | Automatic |
| Create task | R1 | Automatic |
| Save ordinary preference | R1 | Automatic |
| Calendar hold | R1 | Automatic |
| Routine email | R2 | Policy-controlled |
| Information phone call | R2 | Policy-controlled |
| Book appointment | R3 | Approval initially |
| Shopping checkout | R3 | Approval |
| Contractor booking | R3 | Approval |
| Manual bill payment | R4 | Approval always |
| New payee | R4 | Approval always |
| Medical consent | R4 | Never autonomous |
| Legal contract signature | R4 | Never autonomous |

---

# 57. Two-Phase Commit for Sensitive Actions

Use:

```text
PREPARE
 ↓
DISPLAY EXACT ACTION
 ↓
APPROVE
 ↓
COMMIT
 ↓
VERIFY
```

Approval binds to:

- actor
- client
- action type
- recipient/provider
- amount where relevant
- payload hash
- expiration

Material change invalidates approval.

---

# 58. Approval Screen

Example:

```text
ABC ELECTRIC

Thursday 1:00–3:00 PM
Diagnostic fee: $89

FOR
Living Room Outlet

HERMES MAY
✓ Book appointment
✕ Authorize repair work
✕ Authorize additional charges

[Decline]                    [Approve]
```

LifeOps determines whether approval is required.

Console only displays and submits the decision.

---

# 59. Approval Data Model

```yaml
approval_id:
action_id:
payload_hash:
requested_by:
approved_by:
approved_at:
expires_at:
consumed_at:
status:
```

Relationship:

```text
Person ─APPROVED→ Approval ─AUTHORIZES→ Action
```

---

# 60. Action Outbox

Every external write gets a durable Action record before execution.

```yaml
action_id:
type:
status:
idempotency_key:
payload_hash:
created_at:
attempt_count:
last_attempt_at:
external_reference:
verification_state:
```

Flow:

```text
persist intended action
 ↓
execute external request
 ↓
persist external result
 ↓
verify
 ↓
finalize state
```

Never blind-retry an external commitment.

Before retry, inspect whether the previous request may have succeeded.

---

# 61. Idempotency

Mandatory for:

- email writes when provider supports or LifeOps can reconcile
- appointment booking
- reservations
- shopping checkout
- payments
- other externally consequential writes

LifeOps generates and persists idempotency keys.

The LLM does not invent them.

---

# 62. Audit

Record:

```text
requester
user
client
session
intent
tool
risk
approval
action
target
result
verification
timestamp
trace_id
```

This allows:

> Why did Hermes do that?

and:

> Which client changed this?

---

# 63. Calendar Integration

Order:

1. read calendar
2. free/busy
3. create temporary hold
4. create event
5. update
6. cancel

Calendar records should relate to LifeOps entities.

Example:

```text
Appointment ─CALENDAR_EVENT→ external_event_id
```

Never claim a booking succeeded merely because a calendar hold exists.

---

# 64. Email Integration

Capabilities:

- search/read
- thread read
- send
- reply
- associate message with task/provider/entity
- create waiting item
- ingest relevant observations

Email content is untrusted input.

Prompt injection in email must not change LifeOps authority or policy.

---

# 65. Web and Browser

Use Hermes-native web search/extraction for research where possible.

Conceptual modes:

```text
SEARCH
find candidates

EXTRACT
read pages efficiently

BROWSER
interact with authenticated or dynamic sites
```

LifeOps gets involved when research becomes:

- durable state
- a task
- a provider
- a quote
- a commitment
- an external action

---

# 66. Browser Security

Separate persistent browser contexts:

```text
general
shopping
medical
billing
```

Never bypass MFA.

When MFA is required:

```text
NEEDS_ATTENTION
reason: MFA
```

Do not store session cookies in Nornic.

---

# 67. Provider Workflow

Example service workflow:

```text
identify problem
 ↓
inspect related asset/history
 ↓
find previous provider
 ↓
research alternatives if needed
 ↓
check scheduling preference
 ↓
check calendar
 ↓
contact provider
 ↓
collect availability/fees
 ↓
WAITING_EXTERNAL if needed
 ↓
prepare booking
 ↓
approval if policy requires
 ↓
book
 ↓
verify
 ↓
calendar event
 ↓
complete
```

---

# 68. Telephony

Telephony begins after local/hosted voice is stable.

Interface:

```python
class TelephonyProvider:
    async def dial(...)
    async def hangup(...)
    async def send_dtmf(...)
    async def get_status(...)
```

Calls receive a constrained objective.

Example:

```yaml
objective: schedule_electrician
provider: ABC Electric

collect:
  - availability
  - diagnostic_fee

authority:
  request_information: true
  provide_service_address: true
  reserve_slot: false
  authorize_charge: false
  authorize_repairs: false
```

A phone conversation cannot enlarge its own authority.

---

# 69. Structured Call Results

Do not rely only on transcript.

Store:

```yaml
connected:
objective_met:
availability:
diagnostic_fee:
commitments_made:
follow_up_required:
external_reference:
```

Transcript remains supplemental evidence.

---

# 70. Shopping

Initial capabilities:

```text
search
build cart
choose reasonable pickup/delivery slot
identify substitutions
show final total
```

Checkout:

- approval-gated initially
- exact total displayed
- exact merchant shown
- idempotency required
- verify confirmation
- never blindly retry

---

# 71. Bills

Capabilities:

- detect/record bill
- associate vendor/account
- amount
- due date
- expected autopay
- compare history
- anomaly detection
- later payment verification
- prepare manual payment

Expected autopay is not proof of payment.

---

# 72. Financial Actions

Implement last.

Rules:

- new payee always requires approval
- manual payment always requires approval
- amount changes invalidate approval
- external confirmation required
- credentials never exposed to Hermes
- idempotency mandatory
- no raw "pay arbitrary recipient" tool

---

# 73. Hermes Self-Configuration

Hermes may manage through approved interfaces:

- skills
- preferences
- routine templates
- cron jobs
- reminders
- non-critical prompts
- workflow templates

Hermes may not modify:

- authorization code
- approval validation
- payment code
- secret-store implementation
- database migrations
- MCP authentication
- container/runtime security
- browser security
- CI protection
- backup security

---

# 74. Code Change Requests

Expose:

```text
request_code_change()
```

Schema:

```yaml
component:
problem:
observed_behavior:
desired_behavior:
evidence:
  task_ids: []
  trace_ids: []
  failure_count:
risk:
suggested_acceptance_tests: []
```

Persist under:

```text
changes/requests/
```

Coding agents make protected code changes.

Hermes does not.

---

# 75. Hermes Skills

Initial:

```text
personal-core
waiting-for-manager
daily-brief
weekly-review
provider-manager
appointment-manager
calendar-manager
email-triage
```

Later:

```text
grocery-manager
bill-manager
household-maintenance
vehicle-maintenance
phone-call-manager
school-admin
```

Skills define procedure and tool usage.

They do not duplicate deterministic policy.

---

# 76. Skill Template

```markdown
# Purpose
# Trigger
# Relevant LifeOps State
# Allowed Tools
# Procedure
# Approval Boundary
# Failure Handling
# Waiting/Follow-Up Behavior
# Verification
# Completion Criteria
```

---

# 77. System Health Screen

Display:

```text
Hermes          Healthy
DeepSeek        Healthy
LifeOps Core    Healthy
NornicDB        Healthy
MemoryProvider  Healthy
Voice           ElevenLabs / Local / Disabled
Telegram        Connected / Disabled
Calendar        Connected / Disabled
Email           Connected / Disabled
Browser         Healthy / Disabled
Telephony       Healthy / Disabled
Backups         Last successful...
```

Include:

- Refresh
- Test integration
- view recent failures
- restart suggestions

Do not expose arbitrary shell execution through the GUI.

---

# 78. Observability

Start with:

- structured JSON logs
- trace IDs
- semantic operation names

Fields:

```text
trace_id
session_id
client_id
task_id
action_id
component
operation
duration_ms
result
risk_level
approval_id
```

Semantic operations:

```text
memory.recall
memory.write
graph.query
task.transition
policy.evaluate
approval.request
approval.consume
action.prepare
action.execute
action.verify
integration.call
voice.asr
voice.tts
```

Full Grafana/Tempo/Prometheus is optional later.

---

# 79. Backups

Back up:

- Nornic data
- Nornic export
- LifeOps non-secret configuration
- encrypted secrets store
- secret master key separately/securely
- Hermes skills
- Hermes safe configuration
- workflow templates
- audit history
- file/object-store content

Never declare backup complete until restore is tested.

---

# 80. Restore Test

Automate:

```text
create backup
 ↓
restore into temporary environment
 ↓
verify Nornic health
 ↓
verify known entities
 ↓
verify relationships
 ↓
verify task state
 ↓
verify memory retrieval
 ↓
verify configuration metadata
 ↓
report success/failure
```

Run periodically.

---

# 81. Nornic Escape Plan

Do not run a second database as insurance.

Instead maintain:

- repository interfaces
- stable domain IDs
- schema docs
- exports
- restore tests
- migration tests
- domain-level APIs

If Nornic must be replaced:

```text
Hermes unchanged
Console unchanged
MCP unchanged
LifeOps domain unchanged

replace repository implementation
```

---

# 82. Security Boundaries

Personal LifeOps environment must not contain unrelated infrastructure authority.

Do not include:

- production SSH keys
- vSphere admin credentials
- Ansible Vault secrets
- infrastructure Hermes memory
- unrelated production browser sessions
- cloud-admin tokens

LifeOps only receives personal capabilities required by configured integrations.

---

# 83. Safe Mode

Allows:

- conversation
- reads
- memory search
- tasks
- local state
- Console inspection

Disables:

- external communication
- booking
- browser writes
- shopping submission
- telephony writes
- payments

---

# 84. Emergency Stop

Stops:

- external writes
- telephony
- browser execution
- financial actions
- optional voice output if needed

Preserve:

- state
- logs
- audit
- database
- evidence

Provide the control in LifeOps Console.

---

# 85. CI

Every code change:

```text
format/lint
type checking
unit tests
domain-state tests
repository tests
MCP schema tests
HTTP API tests
policy tests
approval tests
idempotency tests
security tests
frontend unit tests
frontend build
```

Integration tests use a disposable Nornic instance.

---

# 86. Failure/Chaos Tests

Simulate:

- DeepSeek timeout
- Hermes restart
- Nornic restart
- Nornic unavailable
- LifeOps crash
- duplicate MCP request
- duplicate HTTP request
- calendar timeout
- email timeout
- browser crash
- ElevenLabs timeout
- ElevenLabs partial stream
- local ASR crash
- local TTS crash
- SIP disconnect
- provider returns success but verification temporarily unavailable

No failure may cause duplicate external commitments.

---

# 87. Phase 0 — Core Spine

Build only:

```text
Hermes
 ↓
LifeOps MCP
 ↓
LifeOps Core
 ↓
NornicDB
```

Domains:

```text
Person
Preference
Task
```

MCP tools:

```text
get_person
get_preferences
save_preference
create_task
list_tasks
```

Console:

- boot existing Knowledge-OS frontend under `console/`
- wire Configuration shell
- wire basic System health
- wire Tasks to LifeOps
- do not migrate every screen yet

---

# 88. Phase 0 Configuration Requirement

The coding agent must not ask for:

- DeepSeek API key
- ElevenLabs API key
- Telegram token
- voice ID
- model ID
- calendar credentials
- email credentials
- browser credentials
- telephony credentials

Instead implement:

- provider schemas
- empty/default config state
- GUI configuration
- fake/test providers
- provider Test buttons
- clear disabled state

The system can run with optional providers disabled.

---

# 89. Phase 0 Acceptance

Test:

1. Hermes saves:
   > I don't like appointments before ten.

2. LifeOps persists the preference.

3. Terminate Hermes session.

4. New Hermes session retrieves preference.

5. Restart Nornic.

6. Preference remains.

7. Console shows the preference/state where applicable.

8. A second MCP client can read the same preference.

9. Second MCP client creates a task.

10. Hermes lists the same task.

Required:

```text
No SQLite
No Qdrant
No Neo4j
No Redis
No Temporal
No extra workflow platform
```

---

# 90. Phase 1 — Console Foundation

Evolve Knowledge-OS into LifeOps Console.

Implement working:

```text
Today
Needs Attention
Waiting
Tasks
Search
Configuration
System
Activity
```

Backend becomes LifeOps Core.

Remove runtime dependency on Knowledge-OS SQLite/Qdrant architecture.

Do not yet implement full graph/memory visualization.

---

# 91. Phase 2 — Memory Provider

Implement thin Hermes LifeOps/Nornic MemoryProvider.

Acceptance:

- safe conversation memory stored
- fresh session recalls it
- memory queryable through LifeOps
- memory visible in Console
- user can invalidate/correct allowed memory
- memory cannot mutate protected transactional state

---

# 92. Phase 3 — World

Implement:

- World graph
- entity inspector
- people/household/provider/assets relationships
- graph filters
- search-to-node
- provenance
- entity history

Use LifeOps APIs.

Browser never gets raw Nornic credentials.

---

# 93. Phase 4 — Durable Work

Expand:

- task state machine
- WaitingItems
- due-work worker
- follow-up logic
- verification states
- Today/Waiting UI

Acceptance:

Work survives:

- conversation exit
- Hermes restart
- LifeOps restart
- Nornic restart

---

# 94. Phase 5 — Configuration + Voice Quick Path

Implement:

- ElevenLabs provider
- ElevenLabs GUI setup
- voice discovery
- voice preview
- streaming TTS
- selectable voice/model
- provider health
- Voice mode controls

Then integrate the Voice Bridge with Hermes.

ElevenLabs enables fastest path to polished speech.

Local speech remains optional.

---

# 95. Phase 6 — Local Voice

Implement supported local ASR/TTS adapters.

Console:

- model selection
- device selection
- load/unload
- health
- latency indicators
- active provider
- fallback provider

Verify same Hermes and same LifeOps state across voice/text.

---

# 96. Phase 7 — Calendar + Email

Read first.

Then reversible writes.

Then external communication.

Implement configuration entirely through Console.

No developer prompt for account details.

---

# 97. Phase 8 — Provider Workflows + Telephony

Start with:

- provider research
- information gathering
- phone calls
- waiting
- quote collection

Then:

- approval-gated booking

No phone-based payment authorization.

---

# 98. Phase 9 — Browser + Shopping

Implement:

- authenticated browser worker
- search/research
- cart building
- substitutions
- approval-gated checkout
- verification

Separate browser contexts.

---

# 99. Phase 10 — Bills + Financial Actions

Bills first.

Payments last.

Before enabling payment:

- action outbox proven
- approvals proven
- idempotency proven
- verification proven
- audit proven
- emergency stop proven
- backup/restore proven

---

# 100. Phase 11 — Hermes Self-Configuration

Enable safe self-management of:

- skills
- preferences
- routines
- cron
- workflow templates

Protected changes create Code Change Requests.

---

# 101. Electrician End-to-End Acceptance Scenario

Input:

> Get an electrician next week for the outlet behind the TV. Nothing before ten.

System should:

1. identify relevant asset
2. retrieve scheduling preference
3. look for provider history
4. inspect calendar
5. find/contact appropriate provider
6. collect availability
7. collect diagnostic fee
8. create waiting item when necessary
9. never authorize repairs
10. prepare booking
11. request approval if required
12. book exactly once
13. verify booking
14. record provider/action history
15. create calendar event
16. mark task completed only after verification

Console must visualize:

- task progress
- waiting state
- provider relationship
- approval
- activity
- final verified completion

---

# 102. Shared-Agent Acceptance Scenario

Hermes:

> Remember I prefer appointments after ten.

Claude Code:

> What are the current scheduling preferences?

Expected:

```text
Appointments after 10 AM.
```

Claude Code:

> Create a task to call the dentist.

Hermes:

> What tasks are open?

Expected:

```text
Call dentist.
```

This proves that state belongs to LifeOps.

---

# 103. Voice Acceptance Scenario

Configure ElevenLabs entirely from Console.

Steps:

1. Open Configuration → Voice → ElevenLabs.
2. Paste API key.
3. Test.
4. Refresh voices.
5. Select voice.
6. Preview voice.
7. Set provider active.
8. Start voice session.
9. Ask:
   > What tasks are open?
10. Hermes uses the same LifeOps task state as text.
11. Add a task by voice.
12. Refresh Console.
13. Task appears.
14. Start text session.
15. Task appears there too.

No manual file editing.

---

# 104. Provider Configuration Acceptance

A fresh code checkout/deployment must succeed without real third-party credentials.

Expected:

```text
DeepSeek: Not configured
ElevenLabs: Not configured
Telegram: Disabled
Calendar: Disabled
Email: Disabled
Telephony: Disabled
```

Console is reachable.

User configures providers later.

The developer/coding agent is never blocked on those values.

---

# 105. Anti-Overengineering Gate

Before introducing any new dependency/service, document:

```text
Problem:
What concrete failure exists now?

Existing capability check:
Can Hermes already solve it?
Can Nornic already solve it?
Can MCP already solve it?
Can LifeOps solve it as a small module?

Why new dependency is required:
...

Operational cost:
...

Removal/migration plan:
...
```

If a concrete problem cannot be shown:

> Do not add it.

---

# 106. Explicitly Prohibited Without New Evidence

Do not introduce during initial implementation:

```text
PostgreSQL
SQLite canonical DB
Qdrant
Neo4j
Redis
Kafka
RabbitMQ
Temporal
n8n
OPA
Kubernetes
dedicated vector service
dedicated graph service
separate memory service
separate entity resolver service
general event bus
multi-agent swarm framework
custom agent runtime replacing Hermes
```

---

# 107. Builder Execution Model

The coding agent receives the full specification but executes one phase at a time.

```text
READ SPEC
 ↓
INSPECT EXISTING CODE
 ↓
PLAN CURRENT PHASE
 ↓
IMPLEMENT
 ↓
TEST
 ↓
RUN ACCEPTANCE
 ↓
ADVERSARIAL REVIEW
 ↓
FIX
 ↓
DOCUMENT
 ↓
COMMIT
 ↓
NEXT PHASE
```

The coding agent must not pause for optional runtime configuration.

If a provider requires real credentials:

- implement adapter
- implement mock
- implement GUI configuration
- implement Test button
- leave provider disabled until user configures it

Continue development.

---

# 108. Coding-Agent Decision Rules

The coding agent may choose:

- ordinary implementation details
- library versions
- internal file organization
- test fixtures
- safe refactors

It must not independently change:

- primary architecture
- primary database
- Hermes-as-primary-agent rule
- LifeOps MCP boundary
- approval/risk model
- secret-storage policy
- GUI-driven configuration requirement
- external-action verification requirement
- Knowledge-OS-as-Console decision

If such a change appears necessary:

1. document the concrete failure
2. create an architecture decision proposal
3. do not silently redesign the system

---

# 109. Exact Phase 0 Builder Prompt

```text
Build Phase 0 of Hermes LifeOps according to BUILD_SPEC.md.

Do not redesign the architecture.

PRIMARY GOAL

Prove this spine:

Hermes
  -> LifeOps MCP
  -> LifeOps Core
  -> NornicDB

and begin converting the uploaded/existing Knowledge-OS frontend into LifeOps Console.

REQUIREMENTS

1. Create the LifeOps monorepo structure needed for Phase 0 only.

2. Deploy NornicDB with persistent storage and private/local network access.

3. Implement a repository abstraction around NornicDB.

4. Implement only these domain entities initially:
   - Person
   - Preference
   - Task

5. Expose exactly these initial MCP operations:
   - get_person
   - get_preferences
   - save_preference
   - create_task
   - list_tasks

6. Connect LifeOps MCP to the existing personal Hermes profile.

7. Demonstrate persistence across:
   - Hermes sessions
   - LifeOps restart
   - Nornic restart

8. Connect one second MCP-capable client and prove shared state.

9. Migrate the Knowledge-OS frontend into /console as the LifeOps Console foundation.

10. Replace its Phase-0 task/state API dependency with LifeOps Core.
    Do not carry forward SQLite or Qdrant as canonical storage.

11. Implement the Configuration shell and provider registry pattern.

12. Implement the default local encrypted SecretStore.

13. Add provider configuration placeholders for:
    - DeepSeek
    - ElevenLabs
    - Telegram
    - Calendar
    - Email
    - Browser
    - Telephony

14. Do NOT require real credentials for any provider during development.

15. The coder must never stop and ask the user for:
    - API keys
    - tokens
    - voice IDs
    - model IDs
    - account IDs
    - phone numbers
    - email accounts
    - provider credentials

    These values will be configured by the user later through LifeOps Console.

16. Implement provider state as:
    - Not configured
    - Configured
    - Healthy
    - Unhealthy
    - Disabled

17. Add automated unit/integration tests.

18. Document local deployment.

DO NOT IMPLEMENT YET

- full voice bridge
- telephony
- email actions
- calendar actions
- browser actions
- payments
- shopping
- Temporal
- Redis
- message queues
- SQLite canonical state
- Qdrant
- Neo4j
- separate entity-resolution service
- custom vector service
- separate memory database
- full document pipeline
- custom agent runtime
- multi-agent framework

PHASE 0 EXIT TEST

A. Hermes stores:
   "I don't like appointments before ten."

B. Kill that Hermes session.

C. A new Hermes session reads the preference from LifeOps.

D. Restart Nornic and repeat successfully.

E. A second MCP client reads the same preference.

F. The second MCP client creates:
   "Call dentist."

G. Hermes lists the same task.

H. LifeOps Console displays the same Task state.

I. No SQLite, Qdrant, Neo4j, Redis, or parallel source of truth exists.

J. Console starts without any third-party provider credentials.

Do not proceed to Phase 1 until all exit tests pass.
```

---

# 110. Definition of Done — Whole System

The project is complete when:

## Core

- Hermes uses LifeOps MCP reliably
- Nornic is the sole application/world-model DB
- repository abstraction prevents database leakage
- shared state works across multiple MCP clients

## Memory

- Hermes has automatic Nornic-backed memory
- memory is inspectable/correctable
- provenance exists
- untrusted content cannot create authority

## Work

- tasks survive restarts/conversations
- waiting/follow-up works
- completion requires verification

## Console

- Knowledge-OS has become LifeOps Console
- Today works
- Needs Attention works
- Waiting works
- Tasks works
- World works
- Memory works
- Knowledge/Files works
- Activity works
- Approvals works
- Configuration works
- System health works

## Configuration

- runtime providers can be configured from GUI
- secrets are never stored in Nornic
- no coder intervention is required for API keys/settings
- provider discovery/test controls work

## Voice

- ElevenLabs quick setup works from GUI
- same Hermes operates voice and text
- local voice can be selected later
- voice is interruptible/streamed

## Integrations

- calendar works
- email works
- provider workflows work
- browser workflows work
- telephony works
- shopping works according to risk policy
- bills work
- payment actions obey strict approval/idempotency/verification

## Safety

- client permissions enforced server-side
- approval binding works
- action outbox works
- idempotency works
- emergency stop works
- safe mode works

## Operations

- backups work
- restore is tested
- failures do not produce duplicate commitments
- useful audit trail exists

## Self-Improvement

- Hermes can safely manage skills/routines/preferences
- protected changes become Code Change Requests
- Hermes cannot rewrite protected machinery

---

# 111. Final Architecture Rule

> **Hermes is the assistant.**

> **LifeOps Core is the safe, portable personal operating layer.**

> **NornicDB is the persistent world model and application state substrate.**

> **Knowledge-OS becomes LifeOps Console instead of creating another GUI.**

> **ElevenLabs provides the fastest voice setup path, while local RTX-based speech remains a selectable option.**

> **Configuration belongs in the GUI. The coding agent builds configurable capability; it does not wait for the user's runtime credentials.**

> **Reuse Hermes, Nornic, MCP, and the existing Knowledge-OS frontend before building additional infrastructure.**

> **Every new component must solve a problem that exists, not one that might exist someday.**
