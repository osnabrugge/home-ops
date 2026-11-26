import copy
import unittest

from check_netbox_image import verify_netbox_image


CHART = {"version": "8.3.116", "appVersion": "v4.7.6"}
BASE_DIGEST = "sha256:" + "1" * 64
IMAGE = {"config": {"Labels": {
    "org.opencontainers.image.version": "4.7.6",
    "org.opencontainers.image.base.name":
        "ghcr.io/netbox-community/netbox:v4.7.6@" + BASE_DIGEST,
    "org.opencontainers.image.base.digest": BASE_DIGEST,
}}}


class NetBoxImageTests(unittest.TestCase):
    def test_matching_chart_configured_image_and_base_are_accepted(self):
        self.assertEqual(verify_netbox_image(CHART, "4.7.6", IMAGE), "4.7.6")

    def test_chart_update_cannot_silently_keep_old_application(self):
        for field in ("configured", "published", "base"):
            with self.subTest(field=field):
                image = copy.deepcopy(IMAGE)
                tag = "4.7.6"
                if field == "configured":
                    tag = "4.7.4"
                elif field == "published":
                    image["config"]["Labels"]["org.opencontainers.image.version"] = "4.7.4"
                else:
                    image["config"]["Labels"]["org.opencontainers.image.base.name"] = (
                        "ghcr.io/netbox-community/netbox:v4.7.4@" + BASE_DIGEST
                    )
                with self.assertRaisesRegex(ValueError, "matching Diode image"):
                    verify_netbox_image(CHART, tag, image)

    def test_matching_version_label_does_not_hide_invalid_base(self):
        for base, digest in (
            ("ghcr.io/netbox-community/netbox:v4.7.6", BASE_DIGEST),
            (IMAGE["config"]["Labels"]["org.opencontainers.image.base.name"], "sha256:" + "2" * 64),
        ):
            with self.subTest(base=base, digest=digest):
                image = copy.deepcopy(IMAGE)
                image["config"]["Labels"]["org.opencontainers.image.base.name"] = base
                image["config"]["Labels"]["org.opencontainers.image.base.digest"] = digest
                with self.assertRaisesRegex(ValueError, "immutable upstream base"):
                    verify_netbox_image(CHART, "4.7.6", image)


if __name__ == "__main__":
    unittest.main()
