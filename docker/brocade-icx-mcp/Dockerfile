# Builds ghcr.io/osnabrugge/brocade-icx-mcp from upstream vespo92/BrocadeICXMCP.
# Upstream ships TypeScript source only (no image, package.json bin is null), so we
# compile dist/ here and run the stdio MCP server that ToolHive proxies over HTTP.
FROM docker.io/library/node:24-bookworm AS build
# renovate: datasource=git-refs depName=BrocadeICXMCP packageName=https://github.com/vespo92/BrocadeICXMCP
ARG BROCADE_REF=deb2041db3fa1a094fd028fd602405d518cf292a
WORKDIR /src
RUN git clone https://github.com/vespo92/BrocadeICXMCP.git . \
    && git checkout "${BROCADE_REF}" \
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
ENTRYPOINT ["node", "dist/servers/stdio.js"]
