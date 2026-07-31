# Builds ghcr.io/osnabrugge/opnsense-mcp — upstream ships an npm package only (no image),
# so install it globally here and run the stdio MCP server that ToolHive proxies over HTTP.
FROM docker.io/library/node:24-bookworm-slim
ENV NODE_ENV=production
# renovate: datasource=npm depName=@richard-stovall/opnsense-mcp-server
ARG OPNSENSE_MCP_VERSION=0.5.3
# command -v asserts the bin name at build time rather than failing at runtime.
RUN npm install -g "@richard-stovall/opnsense-mcp-server@${OPNSENSE_MCP_VERSION}" \
    && npm cache clean --force \
    && command -v opnsense-mcp-server
USER node
ENTRYPOINT ["opnsense-mcp-server"]
