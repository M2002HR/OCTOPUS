# Documentation index

This directory is the canonical English documentation for the project.

| Document | Read it when you need to… |
| --- | --- |
| [Architecture](architecture.md) | Understand modules, data flow, state, and persistence |
| [Configuration](configuration.md) | Create or change the root `.env` safely |
| [Voice turn detection](voice-turn-detection.md) | Tune latency versus interruption resistance |
| [Deployment](deployment.md) | Build and operate the Docker stack |
| [Testing](testing.md) | Run unit, integration, deployment, and live-call tests |
| [Operations](operations.md) | Inspect logs, audit data, retention, and incident procedures |
| [Troubleshooting](troubleshooting.md) | Resolve common setup, Ajil, Telegram, and VoIP failures |

The root `.env` is the only configuration source. Do not put secrets in a submodule `.env`,
source code, documentation, shell history, or Git.
