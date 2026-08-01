# MCP Server — Career Dashboard

Minimal authenticated HTTP server exposing career-job-search tools via the
[Model Context Protocol](https://modelcontextprotocol.io) (MCP).

## Endpoints

### `GET /health`

Health check. Returns `200 OK` with `{"status": "ok"}` when the server is running.

### `POST /tools/score_recruiter`

Scores a recruiter profile using the CV matching engine and returns connection
suitability.

**Request body:**
```json
{
  "profile_url": "https://www.linkedin.com/in/example",
  "name": "Jane Doe",
  "headline": "Talent Acquisition at Example Corp"
}
```

**Response:**
```json
{
  "ok": true,
  "match_score": 0.85,
  "should_send": true
}
```

## Authentication

Send the token via one of:
- Header: `x-career-mcp-token: <token>`
- Header: `Authorization: Bearer <token>`

Configure the token in your environment:
```bash
CAREER_MCP_TOKEN=your-token-here
```

Falls back to `CAREER_DASHBOARD_TOKEN` if `CAREER_MCP_TOKEN` is not set.

## Running

```bash
cd job-search
uv run python mcp/server.py
```

Binds to `127.0.0.1:8000` by default (localhost only).
