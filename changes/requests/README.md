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

Empty. `request_code_change` is exposed as an MCP tool (gated on
`SELF_CONFIGURE`), so Hermes can file a request here. The directory is
resolved to this repository checkout when it is writable, otherwise to the
LifeOps state directory (`LIFEOPS_CHANGE_REQUESTS_DIR` overrides both).
