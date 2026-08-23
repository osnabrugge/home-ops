# Builds ghcr.io/osnabrugge/onshape-mcp from upstream hedless/onshape-mcp.
# Upstream publishes no container image, only a Python package, so we pin a
# commit and build our own rather than tracking a moving branch.
FROM docker.io/library/python:3.12-slim-bookworm AS build
# renovate: datasource=git-refs depName=onshape-mcp packageName=https://github.com/hedless/onshape-mcp
ARG ONSHAPE_MCP_REF=54d21ccc4a5376f692cddd01959305be01e40a53
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir \
    "onshape-mcp @ git+https://github.com/hedless/onshape-mcp.git@${ONSHAPE_MCP_REF}"

FROM docker.io/library/python:3.12-slim-bookworm AS runtime
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 65532 --user-group --no-create-home --shell /usr/sbin/nologin nonroot
USER 65532:65532
ENTRYPOINT ["onshape-mcp"]
