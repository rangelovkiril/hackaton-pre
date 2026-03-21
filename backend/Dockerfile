# Build stage
FROM oven/bun:1 AS build

WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY src ./src

RUN env -i PATH="$PATH" HOME="$HOME" \
    bun build src/index.ts --compile --minify --outfile server

# Production image with slim image for tools
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app
COPY --from=build --chown=app:app /app/server ./server

USER app
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s \
    CMD curl -f http://localhost:3000/health || exit 1

CMD ["./server"]
