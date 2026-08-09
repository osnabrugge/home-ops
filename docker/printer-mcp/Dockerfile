# Builds ghcr.io/osnabrugge/printer-mcp — upstream ships an npm package only (no image),
# so install it globally here and run the stdio MCP server that ToolHive proxies over HTTP.
FROM docker.io/library/node:24-bookworm-slim
ENV NODE_ENV=production
# renovate: datasource=npm depName=mcp-3d-printer-server
ARG PRINTER_MCP_VERSION=1.2.5
# command -v asserts the bin name at build time rather than failing at runtime.
RUN npm install -g "mcp-3d-printer-server@${PRINTER_MCP_VERSION}" \
    && npm cache clean --force \
    && command -v mcp-3d-printer-server
# STL manipulation loads whole meshes into memory; give node room before the
# container limit kills it.
ENV NODE_OPTIONS=--max-old-space-size=1536
USER node
ENTRYPOINT ["mcp-3d-printer-server"]
