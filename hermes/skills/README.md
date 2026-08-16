# Hermes skills

Skills define procedure and tool usage. They do not duplicate deterministic
policy — LifeOps already enforces capabilities, state transitions, approval,
and verification server-side, and restating those rules in a prompt creates two
places to be wrong.

Phase 0 ships no skills. The first set (BUILD_SPEC section 75) arrives with the
Console foundation and memory provider:

```
personal-core        waiting-for-manager   daily-brief
weekly-review        provider-manager      appointment-manager
calendar-manager     email-triage
```

## Template

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
