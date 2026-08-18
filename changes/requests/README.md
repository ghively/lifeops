# Code change requests

Hermes cannot modify protected machinery — authorization, approval validation,
payment code, the secret store, migrations, MCP authentication, or CI. When it
finds a problem there, it files a request here instead (BUILD_SPEC sections 73
and 74).

A coding agent or a human makes the change. The separation is the point: an
assistant that can rewrite its own safety boundary does not have one.

## Format

One JSON file per request, named `{id}.json` — the serialised
`ChangeRequest` model (`core/lifeops/domain/self_config.py`, BUILD_SPEC
section 74's schema field for field): `component`, `problem`,
`observed_behavior`, `desired_behavior`, `task_ids`, `trace_ids`,
`failure_count`, `risk`, `suggested_acceptance_tests`, `created_at`,
`requested_by`. Written by `LifeOpsCore.request_code_change`.

## Status

Empty. `request_code_change` exists in LifeOpsCore (Phase 11), gated on
`SELF_CONFIGURE`, but is not yet exposed as an MCP tool or HTTP route — so
nothing can file a request here yet except code calling the core directly.
Exposing it to Hermes is recorded as an open gap in the 2026-08-18 audit
(`docs/audits/`).
