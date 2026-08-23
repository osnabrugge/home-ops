# Builds ghcr.io/osnabrugge/talos-mcp from upstream eleboucher/talos-mcp.
# The canonical source is a personal Forgejo instance (see go.mod module path);
# GitHub is a mirror, so we pin a commit from the mirror rather than trusting the
# author's prebuilt image at registry.erwanleboucher.dev.
FROM docker.io/library/golang:1.26-bookworm AS build
# renovate: datasource=git-refs depName=talos-mcp packageName=https://github.com/eleboucher/talos-mcp
ARG TALOS_MCP_REF=018f9c8af22ef6b9538857c0ba8482d75dec6ae7
WORKDIR /src
RUN git clone https://github.com/eleboucher/talos-mcp.git . \
    && git checkout "${TALOS_MCP_REF}"
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" \
    -o /out/talos-mcp ./cmd/talos-mcp

FROM gcr.io/distroless/static-debian12:nonroot AS runtime
COPY --from=build /out/talos-mcp /usr/local/bin/talos-mcp
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/talos-mcp"]
