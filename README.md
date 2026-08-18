# hackaton-pre

Prepared starter for HackTUES. The scaffolding that normally eats the first hours of a hackathon (containers, CI, an MQTT path between hardware and the web app) is already wired up, so the event itself is spent on the product rather than on setup.

## What is in here

- `backend/`: Bun and Elysia service. `src/plugins/mqtt-hub.ts` wraps an MQTT client with per topic handlers and opt-in payload parsers. `src/index.ts` listens on port 3000 and exposes two WebSocket routes, `/sensors` (pipes a fixed `sensors/#` subscription to the socket) and `/subscribe` (lets a client subscribe and publish dynamically), plus a heartbeat published to `status/heartbeat` every five seconds.
- `frontend/`: Next.js 16 with React 19 and Tailwind 4, built with `output: 'standalone'`. Contains the default page and an `/api/healt` route returning `ok`.
- `broker/`: Mosquitto configuration. A single anonymous listener on 1883, persistence to `/mosquitto/data/`, logs to file and stdout.
- `hardware/`: `mqtt_hub.py`, the Python counterpart of the backend hub, built on paho-mqtt with `@hub.on`, `@hub.watch`, and `hub.publish` primitives. `examples.py` demonstrates them and `hardware/README.md` documents the API in Bulgarian.
- `.github/`: CI running biome and `tsc --noEmit` on both apps, a Next build for the frontend, then container image builds pushed as `hacktues12-frontend` and `hacktues12-backend`. The check and build steps are factored into composite actions under `.github/actions/`.
- `compose.yaml`, `.env.example`: the local stack, described below.

## The compose stack

Three services on one internal bridge network, all with `restart: unless-stopped`, `no-new-privileges`, and json-file logging capped at three 10 MB files.

- `mosquitto`: `eclipse-mosquitto:2.0.20`, read only with a tmpfs at `/tmp`, config mounted read only from `broker/config`, data and logs bind mounted to `broker/data` and `broker/log`. The port is only exposed on the internal network, not published to the host. Its healthcheck publishes a message to a `healthcheck` topic.
- `backend`: built from `backend/`, published on 3000, waiting for the broker to report healthy.
- `frontend`: built from `frontend/`, published on 3001, waiting for the backend to report healthy.

Both application images are multi stage: a Bun build stage, then a `debian:bookworm-slim` runtime under a non-root `app` user with a `HEALTHCHECK` baked into the Dockerfile. The backend is compiled to a single binary with `bun build --compile`.

Both services read `env_file: .env`, which is not committed. `.env.example` is the template and currently holds one placeholder variable.

## What gets replaced during the hackathon

- The MQTT topics and handlers in `backend/src/index.ts`. The demo subscribes to `raw/#`, `sensors/+/temp`, and `binary/imu`, which are placeholders for real device topics.
- The broker address in `backend/src/index.ts`, hardcoded to `mqtt://localhost`. Inside the compose network the broker resolves as `mosquitto`.
- The frontend page and any API routes beyond the health check.
- `examples.py` in `hardware/`. `mqtt_hub.py` itself is meant to be copied and kept.
- `.env.example` and the resulting `.env`, which carry a single `TEST` variable today.

> [!WARNING]
> The backend Dockerfile healthcheck curls `/health`, but `src/index.ts` defines no such route, so the backend container never reports healthy. Because `frontend` declares `depends_on: backend: condition: service_healthy`, the frontend does not start from a clean `compose up`. Adding the route to the backend clears both.

Two smaller mismatches in the same area: the frontend is published as `3001:3001` while the Next standalone server listens on 3000 unless `PORT` is set, and the frontend health route is spelled `healt`.

## Documentation

- [`docs/git-rescue.md`](docs/git-rescue.md): recovery recipes for common Git mistakes, written in Bulgarian for use under time pressure.
- [`hardware/README.md`](hardware/README.md): full API reference for the Python MQTT hub.
