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

## Memory

Added in Phase 2 (BUILD_SPEC sections 42–47, 91).

```
(:Memory {
  id, subject_id, type, content,
  source_type, source_id, observed_at, created_at,
  confidence, importance,
  valid_from, valid_to, supersedes, entity_ids,
  created_by_client, invalidation_reason
})
```

| Field | Notes |
|---|---|
| `type` | `episodic` · `semantic` · `preference_candidate` · `summary` · `association` |
| `source_type` | Same vocabulary and trust ranking as preferences (section 46) |
| `confidence`, `importance` | 0–1 |
| `valid_from` / `valid_to` | Temporal, like preferences — never edited in place |
| `supersedes` | ID of the record this one replaces |

Recall uses a BM25 fulltext index (`lifeops_memory_content`) with a
parameterized substring fallback when the index is absent. Embeddings stay off
until a provider is configured.

Memory is observational only (section 44): the memory service holds no reference
to the task, preference, approval, or payment repositories, so a memory write
structurally cannot rewrite transactional reality. A `preference_candidate` is
not a `Preference` and never appears through the preference APIs.

---

## World entities (Phase 3)

```
(:Household  {id, display_name, facts_json, created_at, updated_at,
              created_by_client})
(:Provider   {...})
(:Asset      {...})
(:Person     {...})   the Phase 0 node, projected into the world graph
(:Preference {...})   the Phase 0 node, projected when current (section 15)
```

The three Phase 3 types share one shape deliberately (BUILD_SPEC section 36:
only add what a real workflow needs). Splitting them into near-identical
labels with distinct properties would model a difference nothing has asked
for yet.

`facts` is a flat bag of *current* key facts — `{"insurance": "Progressive",
"mileage": "114203"}` — stored as the JSON string `facts_json`, because
Neo4j-compatible property values cannot be maps and a dict property fails at
write time. Keys are sorted before serialisation so identical facts compare
equal. The bag is capped (50 keys, 100-character keys, 500-character values)
so an agent cannot turn one entity into an unbounded document store.

Facts are current-only in Phase 3: there is no per-fact supersession chain.
`get_entity_history` therefore reports the memories referencing an entity and
states that scope in a `covers` field rather than implying more.

Persons and preferences are part of the world graph but keep their richer
models in `domain/people.py` and `domain/preferences.py`. The world repository
*projects* them and never writes them — one `:Preference` node is read by two
repositories, and `create_entity` refuses both types.

A preference projects as BUILD_SPEC section 15 draws it: `display_name` is the
preference's **value** (`"After 10 AM"`), with its `key`, source, and confidence
carried as facts so the inspector shows which preference it is. Only *current*
preferences are nodes — a superseded one leaves the graph and takes its
`PREFERS` edge with it, while both versions stay queryable through preference
history. That is section 15's current view; the temporal toggle it also lists
is not built yet.

---

## Durable work (Phase 4)

Added in Phase 4 (BUILD_SPEC sections 13, 51, 54, 55, 57-62). Four labels,
none of them a workflow engine: a waiting item is a follow-up with a lease, an
action is an outbox row, an approval binds a human decision to an exact
payload, and an audit record is one append-only line answering "why did
Hermes do that?".

```
(:WaitingItem {id, task_id, subject, waiting_on_entity_id, waiting_since,
               expected_by, next_action_at, last_contact_at, followup_count,
               max_followups, status, attempt_count, lease_owner,
               lease_until, created_by_client})

(:Action {id, type, status, idempotency_key, payload_hash, payload_json,
          task_id, target_entity_id, created_at, attempt_count,
          last_attempt_at, external_reference, verification_state,
          failure_reason, created_by_client})

(:Approval {id, action_id, payload_hash, requested_by, approved_by,
            approved_at, expires_at, consumed_at, status, action_type,
            target_entity_id, amount, created_at})

(:AuditRecord {id, requester, user, client, session, intent, tool, risk,
               approval, action, target, result, verification, timestamp,
               trace_id, details_json})
```

`payload` (Action) and `details` (AuditRecord) are dicts, and Neo4j-compatible
property values cannot be maps, so both are stored as JSON strings —
`payload_json` and `details_json` — with keys sorted before serialisation,
the same discipline `facts_json` uses in the World entities section.

`WaitingRepository.claim` is a single conditional `SET` guarded by a `WHERE`
clause on `lease_until`, never a read followed by a write: that is what makes
two workers racing for the same lease resolve to exactly one winner (section
55). `idempotency_key` on `Action` carries a uniqueness constraint for the
same reason section 61 exists — a duplicate key would defeat the mechanism
that stops a blind retry from double-booking or double-charging.
`AuditRepository` has no update or delete Cypher anywhere in this codebase;
append-only is enforced by the absence of the method, not by a rule someone
has to remember.

---

## Relationships

```
(:Person)-[:PREFERS]->(:Preference)         subject of a preference
(:Preference)-[:SUPERSEDES]->(:Preference)  temporal chain
(:Task)-[:ASSIGNED_TO]->(:Person)           owner
(:Task)-[:ABOUT]->(entity)                  related entities (Phase 3)
(:Person)-[:REMEMBERS]->(:Memory)           subject of a memory (Phase 2)
(:Memory)-[:SUPERSEDES]->(:Memory)          temporal chain (Phase 2)

(a)-[:MEMBER_OF]->(b)                       world graph (Phase 3)
(a)-[:OWNS]->(b)
(a)-[:USES_PROVIDER]->(b)
(a)-[:RELATED_TO]->(b)

(:WaitingItem)-[:WAITING_ON]->(entity)      who/what is being waited on (Phase 4)
(:Task)-[:WAITING_ON]->(:WaitingItem)       the task this item blocks (Phase 4)
(:Action)-[:FOR_TASK]->(:Task)              the task an action serves (Phase 4)
(:Approval)-[:AUTHORIZES]->(:Action)        section 59's binding (Phase 4)
(:Person)-[:APPROVED]->(:Approval)          section 59's binding (Phase 4)
```

`WaitingItem`'s two `WAITING_ON` edges point in opposite directions off the
node — outward to the entity being waited on, inward from the task it
blocks — so dropping the stale entity edge on update (`(w)-[:WAITING_ON]->()`)
never touches the task edge.

Reassigning a task deletes the stale `ASSIGNED_TO` edge before creating the new
one, so the graph never shows a task assigned to two people. `ABOUT` follows the
same discipline when a task's related set changes.

`Task.related_entity_ids` remains the source of truth for reads even though
Phase 3 also writes `ABOUT` edges: tasks written before Phase 3 carry only the
property, so the migration is write-path only and both are unioned on read.

The full section 39 vocabulary is declared in `domain/world.py` and accepted by
the world API — all twenty types, in the spec's order. Some have no writer yet
beyond a hand-made link; that is the spec's initial vocabulary, and section 39's
warning bounds inventing new types rather than implementing fewer.

Edges whose endpoints are not world entities — `(:Task)-[:ABOUT]->(asset)` is
the common case — are reported on the entity they touch but dropped during
graph assembly, so the World screen never renders an arrow into a Task.

---

## Constraints and indexes

```cypher
CREATE CONSTRAINT lifeops_person_id     FOR (p:Person)     REQUIRE p.id IS UNIQUE
CREATE CONSTRAINT lifeops_preference_id FOR (p:Preference) REQUIRE p.id IS UNIQUE
CREATE CONSTRAINT lifeops_task_id       FOR (t:Task)       REQUIRE t.id IS UNIQUE
CREATE CONSTRAINT lifeops_household_id  FOR (h:Household)  REQUIRE h.id IS UNIQUE
CREATE CONSTRAINT lifeops_provider_id   FOR (p:Provider)   REQUIRE p.id IS UNIQUE
CREATE CONSTRAINT lifeops_asset_id      FOR (a:Asset)      REQUIRE a.id IS UNIQUE
CREATE CONSTRAINT lifeops_memory_id     FOR (m:Memory)     REQUIRE m.id IS UNIQUE
CREATE CONSTRAINT lifeops_waiting_id    FOR (w:WaitingItem) REQUIRE w.id IS UNIQUE
CREATE CONSTRAINT lifeops_action_id     FOR (a:Action)      REQUIRE a.id IS UNIQUE
CREATE CONSTRAINT lifeops_action_idempotency_key
                                         FOR (a:Action)      REQUIRE a.idempotency_key IS UNIQUE
CREATE CONSTRAINT lifeops_approval_id   FOR (ap:Approval)   REQUIRE ap.id IS UNIQUE
CREATE CONSTRAINT lifeops_audit_id      FOR (r:AuditRecord) REQUIRE r.id IS UNIQUE

CREATE INDEX lifeops_preference_subject_key FOR (p:Preference) ON (p.subject_id, p.key)
CREATE INDEX lifeops_task_state             FOR (t:Task)       ON (t.state)
CREATE INDEX lifeops_task_created           FOR (t:Task)       ON (t.created_at)
CREATE INDEX lifeops_memory_subject         FOR (m:Memory)     ON (m.subject_id)
CREATE INDEX lifeops_waiting_task           FOR (w:WaitingItem) ON (w.task_id)
CREATE INDEX lifeops_waiting_status         FOR (w:WaitingItem) ON (w.status)
CREATE INDEX lifeops_action_task            FOR (a:Action)      ON (a.task_id)
CREATE INDEX lifeops_action_status          FOR (a:Action)      ON (a.status)
CREATE INDEX lifeops_approval_action        FOR (ap:Approval)   ON (ap.action_id)
CREATE INDEX lifeops_approval_status        FOR (ap:Approval)   ON (ap.status)
CREATE INDEX lifeops_audit_target           FOR (r:AuditRecord) ON (r.target)

CREATE FULLTEXT INDEX lifeops_memory_content FOR (m:Memory) ON EACH [m.content]
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
