# Builds ghcr.io/osnabrugge/spoolman-mcp from upstream Disane87/spoolman-mcp.
# Upstream ships TypeScript source only (no image, package.json bin is null), so we
# compile dist/ here and run the stdio MCP server that ToolHive proxies over HTTP.
FROM docker.io/library/node:24-bookworm AS build
# renovate: datasource=git-refs depName=spoolman-mcp packageName=https://github.com/Disane87/spoolman-mcp.git
ARG SPOOLMAN_REF=88935e98bdf2a266a8441c35c3dade018e014a81
WORKDIR /build
WORKDIR /src
RUN git clone https://github.com/Disane87/spoolman-mcp.git . \
    && git checkout "${SPOOLMAN_REF}" \
    && npm ci \
    && npm run build \
    && npm prune --omit=dev \
    && npm cache clean --force

FROM docker.io/library/node:24-bookworm-slim AS runtime

ENV NODE_ENV=production
RUN mkdir -p /app && chown node:node /app
WORKDIR /app
COPY --chown=node:node --from=build /src/package.json ./package.json
COPY --chown=node:node --from=build /src/node_modules ./node_modules
COPY --chown=node:node --from=build /src/dist ./dist
USER node
# stdio transport: MCP JSON-RPC on stdout, logs on stderr/file. ToolHive attaches here.
ENTRYPOINT ["node", "dist/index.js"]
