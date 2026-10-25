"""The public source must not include a default author signing secret."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(secret):
    spec = importlib.util.spec_from_file_location("public_license_fixture", ROOT / "license_client.py")
    result = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"TENDER_AUTO_LICENSE_SECRET": secret}):
        spec.loader.exec_module(result)
    return result


class PublicLicenseTests(unittest.TestCase):
    def test_unconfigured_is_fail_closed(self):
        lic = module("")
        with self.assertRaises(ValueError):
            lic._sign({"fixture": True})
        self.assertIsNone(lic._unsign("invalid"))
        self.assertFalse(lic.validate()[0])

    def test_own_build_roundtrip(self):
        lic = module("test-fixture-only-" * 4)
        self.assertEqual(lic._unsign(lic._sign({"fixture": True})), {"fixture": True})

    def test_other_build_cannot_validate(self):
        a, b = module("first-test-fixture-" * 4), module("second-test-fixture-" * 4)
        self.assertIsNone(b._unsign(a._sign({"fixture": True})))


if __name__ == "__main__":
    unittest.main()
