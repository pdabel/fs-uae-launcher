# syntax=docker/dockerfile:1.16
#
# Netplay server image. Replaces the python:3.13-alpine image that ran
# launcher/server/game.py; see "Rollout" step 8 in
# docs/netplay-go-server-design.md.
#
# Build context is fsnp-server/ (the Go module), not the repository root.

# Cross-compile from the build platform instead of emulating the target under
# QEMU — the Go toolchain does this natively, and the result is static.
FROM --platform=$BUILDPLATFORM golang:1.24-alpine AS build

ARG TARGETOS
ARG TARGETARCH
ENV CGO_ENABLED=0

WORKDIR /src
COPY . .
RUN GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags="-s -w" -o /fsnp-server ./cmd/fsnp-server

# No libc, no shell, no package manager: the binary is the whole image. This
# also means there is no entrypoint.sh to go wrong — the server reads
# PORT/PLAYERS/PASSWORD/LOG_FILE from the environment itself.
FROM scratch AS base

ENV PORT=25101
ENV PLAYERS=2
# PASSWORD is read from the environment too, but is deliberately not declared
# here: declaring a secret-shaped name in ENV trips SecretsUsedInArgOrEnv, and
# the server already defaults to no password. Pass -e PASSWORD=... at runtime.

COPY --from=build /fsnp-server /fsnp-server

# Numeric uid: a scratch image has no /etc/passwd to name a user in.
USER 101
EXPOSE 25101
ENTRYPOINT ["/fsnp-server"]
