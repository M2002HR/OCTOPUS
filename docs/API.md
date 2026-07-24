# Local administration API

`agent-api` is a localhost-bound FastAPI service for health, redacted configuration, project
discovery, job inspection, enqueue, and cancellation. It is an operator interface, not the normal
Telegram UI.

Default base URL: `http://127.0.0.1:18090`.

| Method/path | Purpose |
| --- | --- |
| `GET /health` | Process liveness, product name, version |
| `GET /ready` | Ajil, PostgreSQL, and Redis readiness map |
| `GET /version` | Package version |
| `GET /config/redacted` | Validated policy with Bot/Ajil token presence redacted |
| `GET /projects` | Registered/discovered project metadata |
| `GET /jobs/{job_id}` | Job state, objective/result/error, Codex thread/turn IDs |
| `GET /jobs/{job_id}/events` | Ordered durable job events |
| `POST /jobs` | Create a text job for supplied Telegram user/chat IDs |
| `POST /jobs/{job_id}/cancel` | Persist cancellation request |
| `GET /docs` | OpenAPI UI outside `production` environment |

Example:

```bash
curl --noproxy '*' -fsS http://127.0.0.1:18090/ready
curl --noproxy '*' -fsS http://127.0.0.1:18090/jobs/JOB_ID
curl --noproxy '*' -X POST http://127.0.0.1:18090/jobs/JOB_ID/cancel
```

The API currently relies on localhost/network boundary rather than application authentication.
Never bind it publicly without adding authentication, authorization, rate limits, TLS/reverse
proxy policy, and endpoint-level ownership checks. In particular, direct API job/event lookups do
not apply the Telegram handler's owner scoping.

`/config/redacted` is designed for diagnostics, but rendered Compose configuration and unredacted
`agentctl config dump --no-redact` can expose deployment values and must not be published.

Liveness success does not imply dependencies are available; deployment acceptance uses `/ready`.
