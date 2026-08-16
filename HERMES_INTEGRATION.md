# Attaching Hermes and other MCP clients

LifeOps MCP is the portable agent interface. Hermes is the primary consumer, but
any trusted MCP client connects the same way and sees the same state.

---

## Scope, stated plainly

**This repository does not contain the Hermes runtime.** Hermes is the user's
own personal assistant, installed separately.

What LifeOps owns and what Phase 0 delivers is the *server* side of the
contract: the MCP server, the tools, the client-identity model, and the
capabilities each identity holds. The Phase 0 exit test exercises that contract
over real MCP with `--client hermes-personal` — the exact identity and interface
Hermes uses.

What has not been exercised on this machine is Hermes itself connecting, because
Hermes is not installed here. The steps below are what completes that, and they
are the same steps that already work for Claude Code.

---

## Register the server

```bash
./hermes/bootstrap/register-mcp-client.sh hermes-personal
```

This prints a launch configuration:

```json
{
  "mcpServers": {
    "lifeops": {
      "command": "/path/to/lifeops/.venv/bin/python",
      "args": ["-m", "lifeops.mcp.server", "--client", "hermes-personal"],
      "cwd": "/path/to/lifeops",
      "env": {
        "LIFEOPS_NORNIC_URI": "bolt://127.0.0.1:7687",
        "LIFEOPS_NORNIC_USER": "admin",
        "LIFEOPS_NORNIC_PASSWORD": "…",
        "LIFEOPS_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

Paste it into Hermes's MCP server configuration. The script prints rather than
edits, because every MCP client stores this differently and silently rewriting
someone's assistant configuration is not a thing a build script should do.

The output contains the NornicDB password. Do not commit it.

A template is at [`hermes/config_templates/mcp_servers.json`](hermes/config_templates/mcp_servers.json).

---

## Client identity decides permissions

The `--client` value is the whole authorization story. It is bound to the
*connection*, not passed per call — a tool argument would be model-controlled,
letting an agent name itself `hermes-personal` and inherit Hermes's
capabilities.

| Client ID | Gets |
|---|---|
| `hermes-personal` | Read world, preferences, tasks; write preferences; create and update tasks |
| `interactive-mcp` | The same — a conversational client the user is talking to directly |
| `claude-code` | Read everything; create tasks. **Cannot** write preferences or update tasks |
| `lifeops-console` | The above plus configuration and approval |

An unrecognised `--client` exits non-zero, so a typo is loud rather than a
silent downgrade to fewer permissions.

Full table in [SECURITY.md](SECURITY.md).

---

## Claude Code

```bash
CFG=$(./hermes/bootstrap/register-mcp-client.sh claude-code \
      | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["mcpServers"]["lifeops"]))')
claude mcp add-json lifeops "$CFG" --scope local
claude mcp list
```

You should see:

```
lifeops: …/.venv/bin/python -m lifeops.mcp.server --client claude-code - ✔ Connected
```

---

## Verifying shared state

The point of LifeOps is that state belongs to it, not to any one agent
(BUILD_SPEC section 102). To see that:

In Hermes:

> Remember I prefer appointments after ten.

In Claude Code, or any second client:

> What are the current scheduling preferences?

It should report the preference Hermes saved, from a different process it has
never spoken to.

Then, in the second client:

> Create a task to call the dentist.

And back in Hermes:

> What tasks are open?

The task appears. So does it in **Console → Tasks**, tagged with the client that
created it.

A scripted version of this exact flow is `tests/e2e/test_phase0_exit.py`.

---

## What Hermes should use LifeOps for

Worth writing to LifeOps:

- Lasting preferences — "nothing before ten", "always the same mechanic"
- Durable tasks that should outlive the conversation
- Anything the user would expect to still be true next week

Not worth writing:

- Conversational filler and temporary speculation
- Unverified web claims stated as user facts
- Anything that belongs in the current context window

The MCP server's `instructions` field carries this guidance to the model, so it
arrives without prompt engineering on the Hermes side.

---

## Troubleshooting

**Will not connect.** Run it by hand — the error goes to stderr:

```bash
./.venv/bin/python -m lifeops.mcp.server --client hermes-personal
```

**`repository_error` on every call.** NornicDB is not running, or the password
in the launch config does not match. `./scripts/nornicdb.sh status`.

**`capability_denied`.** Working as intended. Check which identity the
connection declared against the table above.

**No tools listed.** Confirm the client launched the process with the right
`cwd`, so `lifeops` is importable.
