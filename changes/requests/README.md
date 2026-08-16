# Code change requests

Hermes cannot modify protected machinery — authorization, approval validation,
payment code, the secret store, migrations, MCP authentication, or CI. When it
finds a problem there, it files a request here instead (BUILD_SPEC sections 73
and 74).

A coding agent or a human makes the change. The separation is the point: an
assistant that can rewrite its own safety boundary does not have one.

## Format

One Markdown file per request, named `YYYY-MM-DD-short-slug.md`:

```yaml
---
component:            # which part of LifeOps
problem:              # what is wrong
observed_behavior:    # what happens now
desired_behavior:     # what should happen
risk:                 # low | medium | high
evidence:
  task_ids: []
  trace_ids: []
  failure_count: 0
suggested_acceptance_tests: []
---
```

Followed by prose explaining the context.

## Status

Empty. The `request_code_change` tool arrives in Phase 11.
