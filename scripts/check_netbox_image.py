import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


BASE_IMAGE = re.compile(
    r"ghcr\.io/netbox-community/netbox:v(\d+\.\d+\.\d+)@(sha256:[a-f0-9]{64})"
)
VERSION = re.compile(r"v?(\d+\.\d+\.\d+)")


def release(value: str) -> str:
    match = VERSION.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError(f"Expected an exact NetBox release, got {value!r}")
    return match.group(1)


def verify_netbox_image(
    chart: dict[str, Any], tag: str, image: dict[str, Any]
) -> str:
    expected = release(chart["appVersion"])
    configured = release(tag)
    labels = image["config"]["Labels"]
    published = release(labels["org.opencontainers.image.version"])
    if {configured, published} != {expected}:
        raise ValueError(
            f"Chart {chart['version']} requires NetBox {expected}; "
            f"configured={configured}, published={published}. "
            "Publish and test the matching Diode image before accepting this update."
        )
    base = BASE_IMAGE.fullmatch(labels["org.opencontainers.image.base.name"])
    if not base or labels["org.opencontainers.image.base.digest"] != base.group(2):
        raise ValueError("Custom NetBox image must identify its immutable upstream base")
    if {expected, configured, published, base.group(1)} != {expected}:
        raise ValueError(
            f"Chart {chart['version']} requires NetBox {expected}; "
            f"configured={configured}, published={published}, base={base.group(1)}. "
            "Publish and test the matching Diode image before accepting this update."
        )
    return expected


def read_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(subprocess.check_output(
        ["yq", "-o=json", ".", str(path)], text=True
    ))
    if not isinstance(value, dict):
        raise ValueError(f"Expected one manifest object in {path}")
    return value


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    app = root / "kubernetes/apps/observability/netbox/app"
    source = read_manifest(app / "ocirepository.yaml")["spec"]
    values = read_manifest(app / "helmrelease.yaml")["spec"]["values"]["image"]
    chart = json.loads(subprocess.check_output(
        ["crane", "config", source["url"].removeprefix("oci://") + ":" + source["ref"]["tag"]],
        text=True,
    ))
    digest = values["digest"]
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise ValueError("The custom NetBox image must be digest-pinned")
    image = json.loads(subprocess.check_output(
        ["crane", "config", "--platform", "linux/amd64",
         values["registry"] + "/" + values["repository"] + "@" + digest],
        text=True,
    ))
    version = verify_netbox_image(chart, values["tag"], image)
    print(f"NetBox chart {chart['version']} and tested custom-image base agree on {version}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError) as error:
        print(f"NetBox image compatibility check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
