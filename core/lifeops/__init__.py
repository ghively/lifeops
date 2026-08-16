"""LifeOps Core.

The portable personal domain/API layer, deterministic safety boundary, action
executor, integration layer, and shared MCP server that sits between agents
(Hermes and other trusted MCP clients) and NornicDB.

LifeOps Core is not an agent. It holds no planner and runs no reasoning loop.
It owns the user's durable personal state and the rules that govern changes
to it.
"""

__version__ = "0.1.0"
