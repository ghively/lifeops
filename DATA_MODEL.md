# Data model

Everything durable lives in NornicDB as labelled nodes and relationships.
LifeOps writes plain graph structure; the temporal behaviour comes from
explicit validity windows rather than from database features, which keeps it
portable.

Phase 0 implements three entity types. The rest arrive with the phases that need
them (BUILD_SPEC section 36) — adding a type before a real workflow requires it
is how a schema becomes a museum.

---

## Canonical IDs

Every entity gets an application-generated stable ID. External provider
identifiers are properties. Display names are never identity.

| Shape | Example | Used for |
|---|---|---|
| Slug | `person_gene`, `provider_abc_electric` | Long-lived, human-meaningful entities |
| ULID | `task_01j5x...`, `preference_01j5x...` | Entities created continuously at runtime |

ULIDs sort lexicographically by creation time, so "most recent first" needs no
secondary index.

Slugs fold Unicode to ASCII first, so "Zoë" and "Zoe" do not become two
different canonical people.

---

## Person

```
(:Person {
  id, display_name, is_primary, aliases,
  timezone, created_at, updated_at
})
```

Exactly one Person carries `is_primary` — the human the assistant acts for.
Promoting a person demotes every other in the same transaction, so "who is this
for?" is never ambiguous.

Deliberately thin. Contact details, household membership, and relationships
arrive in Phase 3 where they belong as graph edges rather than as a widening
property bag.

---

## Preference

```
(:Preference {
  id, subject_id, key, value,
  source_type, source_id, confidence, importance,
  observed_at, created_at,
  valid_from, valid_to, supersedes,
  created_by_client, notes
})
```

| Field | Notes |
|---|---|
| `key` | Stable dotted topic, e.g. `scheduling.earliest_appointment_time` |
| `value` | Free text — a personal preference is often a sentence, and typing it early would push the nuance into a prompt instead of the record |
| `valid_to` | `null` means still true; every current-state query filters on this |
| `source_type` | Feeds the trust hierarchy in [SECURITY.md](SECURITY.md) |
| `confidence` | 0–1. Explicit statements are 1.0; inferences arrive lower and surface in the Console for correction rather than being acted on silently |

### Key normalisation

`Scheduling.Earliest`, `  scheduling earliest  `, and `scheduling__earliest` all
collapse to `scheduling.earliest` / `scheduling_earliest`. Two spellings of one
key must not become two competing current values.

### Temporal supersession

```
                      user changes their mind
                                ↓
A  "after 10"   valid_from: 2026-08-16   valid_to: 2027-03-02
B  "after 9"    valid_from: 2027-03-02   valid_to: null

(B)-[:SUPERSEDES]->(A)
```

Both writes share one transaction. Committing only the first would leave the
subject with no current value; committing only the second would leave two.

Re-saving an identical value returns the existing record rather than creating
another, so repeated conversation turns do not pile up history.

---

## Task

```
(:Task {
  id, title, description, state, priority,
  created_at, updated_at, due_at,
  owner_entity_id, assigned_client, current_action, waiting_item_id,
  verification_required, verification_state, verification_evidence,
  related_entity_ids, source, created_by_client
})
```

### States

```
CAPTURED  PLANNED  READY  EXECUTING  WAITING_EXTERNAL
NEEDS_APPROVAL  VERIFYING  COMPLETED  BLOCKED  FAILED  CANCELLED
```

| Group | States |
|---|---|
| Terminal | `COMPLETED`, `CANCELLED` |
| Active | `EXECUTING`, `WAITING_EXTERNAL`, `NEEDS_APPROVAL`, `VERIFYING` |
| Needs a human | `NEEDS_APPROVAL`, `BLOCKED`, `FAILED` |

`FAILED` is recoverable — it may return to `READY` or `PLANNED` — but it cannot
jump straight to `COMPLETED`.

### Verification

| `verification_state` | Meaning |
|---|---|
| `not_required` | Local work |
| `pending` | Awaiting evidence |
| `verified` | Evidence recorded |
| `failed` | The external system disagreed |

A task with `verification_required` reaches `COMPLETED` only from `VERIFYING`
and only with evidence. Enforced in the domain layer, so HTTP and MCP get the
same gate.

`related_entity_ids` is a property in Phase 0 because the entity types it points
at do not exist yet. Phase 3 promotes it to real edges — a migration of one
repository, not a change to the domain.

---

## Relationships

Phase 0 writes three:

```
(:Person)-[:PREFERS]->(:Preference)         subject of a preference
(:Preference)-[:SUPERSEDES]->(:Preference)  temporal chain
(:Task)-[:ASSIGNED_TO]->(:Person)           owner
```

Reassigning a task deletes the stale `ASSIGNED_TO` edge before creating the new
one, so the graph never shows a task assigned to two people.

The wider vocabulary from BUILD_SPEC section 39 — `MEMBER_OF`, `USES_PROVIDER`,
`WAITING_ON`, `REQUIRES_APPROVAL`, `DERIVED_FROM`, and the rest — is defined
there and written as the phases that use them land.

---

## Constraints and indexes

```cypher
CREATE CONSTRAINT lifeops_person_id     FOR (p:Person)     REQUIRE p.id IS UNIQUE
CREATE CONSTRAINT lifeops_preference_id FOR (p:Preference) REQUIRE p.id IS UNIQUE
CREATE CONSTRAINT lifeops_task_id       FOR (t:Task)       REQUIRE t.id IS UNIQUE

CREATE INDEX lifeops_preference_subject_key FOR (p:Preference) ON (p.subject_id, p.key)
CREATE INDEX lifeops_task_state             FOR (t:Task)       ON (t.state)
CREATE INDEX lifeops_task_created           FOR (t:Task)       ON (t.created_at)
```

Applied on every boot; safe to re-run. Uniqueness on canonical IDs is the one
invariant worth pushing into the database — a duplicate `person_gene` would
silently fork the user's world.

---

## Timestamps

RFC 3339 UTC strings with a trailing `Z`, e.g. `2026-08-16T16:40:00Z`.

Stored as strings deliberately: string comparison on this format is also
chronological comparison, so validity-window and range filters work without
depending on a temporal type. Time is injected through a `Clock` rather than
read from `datetime.now()`, which keeps supersession tests deterministic instead
of racing the wall clock.

---

## What is not in NornicDB

| Data | Where | Why |
|---|---|---|
| Secrets | `SecretStore`, AES-GCM, outside the repository | The world model is read broadly; credentials must not be in that blast radius |
| Provider settings | `~/.local/share/lifeops/config/lifeops.config.json` | Must be readable before a database connection exists — the Console has to render "NornicDB: unreachable" without reaching NornicDB |
| Browser cookies | Never persisted | BUILD_SPEC section 66 |
| Binary files | Object storage, with only metadata in the graph (Phase 1) | |
