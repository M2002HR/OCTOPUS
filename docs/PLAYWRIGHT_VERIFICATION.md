# Browser and visual verification

Browser work is orchestrated from Telegram but executed by Codex in the selected workspace. The
current implementation does not run a second autonomous Playwright scheduler. It asks Codex to use
the project's existing Chrome Lab, Playwright, browser scripts, or CDP tooling, inspect the result,
and return validated artifacts.

## User commands

- `/browser` opens screenshot, test, and latest-artifact actions.
- `/browser screenshot` requests a real UI check, screenshot creation, inspection, and Telegram
  handoff.
- `/browser test` requests relevant browser/E2E tests and reports.
- `/browser artifact` finds and inspects the newest relevant existing artifact without changing
  source.

Natural-language tasks may request the same workflow, for example: “Open project Takane, verify
the dashboard in Chrome Lab, and send me a screenshot.”

## Execution model

1. The user explicitly selects a workspace.
2. OCTOPUS creates a durable Codex job with browser verification instructions.
3. Codex discovers the workspace's supported browser commands and application URL.
4. Codex starts/reuses only resources needed by that project.
5. Codex inspects browser/test output and any screenshot rather than merely checking file existence.
6. Codex appends a `[[telegram_file:/absolute/path]]` directive.
7. The worker validates containment, size, MIME metadata, and hash.
8. The Bot sends the artifact and persists content-safe evidence.

Browser success must include concrete evidence: a passed test, inspected screenshot, console/network
finding, or explicit failure. “The command ran” is not enough.

## Configured modes

`config/agent.yaml` defines:

| Setting | Default | Meaning |
| --- | --- | --- |
| `browser.default_mode` | `isolated_headless` | Preferred project browser mode |
| `browser.headless` | `true` | Default headless behavior |
| `browser.cdp_endpoint` | `http://127.0.0.1:9222` | Existing Chrome/Chrome Lab CDP endpoint |

Environment mappings are `PLAYWRIGHT_HEADLESS` and `CHROME_CDP_ENDPOINT`.

Supported policy concepts:

- **isolated headless**: a temporary browser context suitable for deterministic CI;
- **isolated headed**: a visible/Xvfb browser when visual interaction requires it;
- **CDP**: reuse an existing explicitly configured Chrome instance.

The selected project still owns its executable commands and dependencies. OCTOPUS does not
silently install browser packages into unrelated workspaces.

## Resource and secret safety

- Browser subprocesses/contexts must be closed on success, error, timeout, and cancellation.
- Ports and processes started for one job must be bounded and cleaned up.
- Screenshots and reports must remain inside the selected workspace or configured artifact root.
- Do not attach browser profiles, cookies, local storage databases, HAR files containing
  authorization headers, or screenshots displaying credentials.
- CDP grants broad access to the connected browser profile; use only a dedicated profile.
- A Telegram path or URL is untrusted input and never bypasses artifact containment.

## Artifacts

Artifact metadata includes job, kind, name, absolute path, MIME type, byte size, SHA-256, Telegram
file ID when sent, timestamps, expiry, and safe metadata. Direct Bot uploads are capped by
`artifacts.telegram_direct_upload_max_bytes` (47,185,920 bytes by default). Retention defaults to
30 days but requires an external cleanup policy if no scheduler is enabled.

## Verification

`RUN_LIVE_PLAYWRIGHT_TESTS=true` enables opt-in live checks. A production acceptance test should:

1. select a disposable/approved project;
2. start its app using documented commands;
3. request `/browser screenshot`;
4. confirm the UI is loaded rather than an error page;
5. inspect the received Telegram image;
6. check the artifact row and safe job events;
7. confirm no browser/server process is leaked after cancellation or completion.

If the project has no browser tooling or reachable page, Codex must return that limitation instead
of fabricating a screenshot.
