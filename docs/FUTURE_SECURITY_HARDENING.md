# Future security hardening

The current deployment intentionally gives one trusted owner full Codex access to selected
workspaces and host tools. It is not a multi-tenant or untrusted-chat security boundary. Complete
the following before broader exposure.

## Identity and authorization

- Require non-empty Bot user/chat allowlists in production.
- Add role-based, per-command/tool/project authorization.
- Require explicit confirmation for destructive Git, filesystem, Docker, systemd, credential, and
  network actions.
- Separate administrator, operator, and read-only identities.
- Rotate/revoke Bot tokens and Telethon sessions through a documented incident procedure.
- Bind completion calls to verified owner identities and rate-limit calls per user/job/time.

## Codex and host isolation

- Replace `danger-full-access` default with least privilege.
- Run work in per-project sandboxes/containers or VMs.
- Restrict mounted workspace roots, Docker socket, systemd, browser profile, and network egress.
- Enforce command/network allow/deny policy outside model instructions.
- Add quotas for subprocesses, CPU, memory, disk, artifacts, and concurrent jobs.
- Require signed/approved escalation for leaving read-only/workspace-write.

## Secrets

- Replace plaintext `.env` production secrets with a secrets manager or protected runtime
  injection.
- Never mount the complete Codex/SSH/browser home when a narrower credential is possible.
- Encrypt PostgreSQL, Redis AOF, SQLite, backups, and artifacts at rest.
- Add automated secret scanning before commit/artifact upload.
- Redact URLs/query strings, subprocess environments, provider bodies, and browser data.

## Telegram and voice

- Use a dedicated primary Telethon account/session.
- Add call/message rate limits and abuse controls.
- Obtain and record processing/recording consent as required.
- Authenticate and monitor relay infrastructure; rotate relay credentials.
- Restrict SSH host keys/users/commands and firewall remote relay egress.
- Add stronger exactly-once user policy or confirmation if duplicate crash-boundary completion
  calls are unacceptable.

## Data governance

- Define retention and automated deletion for PostgreSQL messages/jobs/memory, voice transcripts,
  JSONL, artifacts, and ignored runtime test media.
- Add user export/deletion workflows.
- Encrypt and access-control backups; test restoration.
- Make audit storage append-only/tamper-evident and forward it to a protected collector.
- Classify content-bearing versus content-free tables/events and document operator access.

## Application and supply chain

- Pin base images by digest and dependency lockfiles/hashes.
- Scan dependencies, images, and recursive submodules.
- Sign builds/releases and generate an SBOM.
- Protect default branches and require reviewed CI.
- Add database migration compatibility/rollback tests.
- Harden HTTP headers, webhook verification, API authentication, and request rate limits.
- Remove/secure optional Swagger, Prometheus, Grafana, and local Bot API endpoints.

## Model/tool safety

- Treat Telegram content, attachments, memory, repository text, web pages, and quoted messages as
  untrusted prompt-injection sources.
- Keep authorization in deterministic code, not model output.
- Validate structured Ajil/Codex output schemas and path containment.
- Add policy/evaluation suites for data exfiltration, destructive commands, credential requests,
  and cross-project access.
- Retain the prohibition on exposing private chain-of-thought.

## Production readiness gate

Do not call the deployment production-hardened until threat modeling, authorization tests,
isolation/egress policy, secret rotation, encrypted retention, backup restore, incident response,
and independent security review are complete and evidenced.
