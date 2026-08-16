"""LifeOps Core entrypoint — runs the HTTP API for LifeOps Console.

The MCP server runs as its own process (``lifeops-mcp``) because MCP clients
launch and own their transport. Both processes share the same NornicDB and the
same LifeOps domain rules, so the state they see is identical.
"""

from __future__ import annotations

import argparse

import uvicorn

from lifeops.api.http import create_app
from lifeops.observability.logging import configure_logging
from lifeops.settings import get_settings


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(prog="lifeops", description="LifeOps Core API")
    parser.add_argument("--host", default=settings.http_host)
    parser.add_argument("--port", type=int, default=settings.http_port)
    parser.add_argument("--reload", action="store_true", help="Reload on code change.")
    args = parser.parse_args(argv)

    configure_logging(level=settings.log_level, json_output=settings.log_json)

    if args.reload:
        # The reloader needs an import string so the worker can re-import.
        uvicorn.run(
            "lifeops.main:app_factory",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
            log_config=None,
        )
        return

    uvicorn.run(create_app(), host=args.host, port=args.port, log_config=None)


def app_factory():  # pragma: no cover - used by uvicorn --reload
    return create_app()


if __name__ == "__main__":
    main()
