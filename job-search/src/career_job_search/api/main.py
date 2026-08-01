from __future__ import annotations

import os

import uvicorn

from career_job_search.api.server import create_app

API_PORT_KEY = "CAREER_API_PORT"
API_PORT_DEFAULT = 8000


def main(argv: list[str] | None = None) -> int:
    port = int(os.environ.get(API_PORT_KEY, API_PORT_DEFAULT))
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
