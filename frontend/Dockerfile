# Build the SPA, then serve it with Caddy, which also proxies /api to the backend.
# Build context is the repository root (the app reads CHANGELOG.md for its patch notes).
FROM node:22-alpine AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY CHANGELOG.md /src/CHANGELOG.md
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /src/frontend/dist /srv
COPY frontend/Caddyfile /etc/caddy/Caddyfile
