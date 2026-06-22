import os
import unittest
from pathlib import Path
from unittest.mock import patch

from glebza.tradeapp.src.exchanges.tinvest_grpc import (
    _russian_trusted_ca_dir,
    load_grpc_root_certificates,
)


class TestTinvestGrpc(unittest.TestCase):
    def test_load_grpc_root_certificates_includes_russian_ca(self):
        with patch.dict(
            os.environ,
            {"TINVEST_GRPC_USE_CERTIFI": "0"},
            clear=False,
        ):
            os.environ.pop("TINVEST_GRPC_ROOT_CERTS", None)
            os.environ.pop("TINVEST_GRPC_USE_RUSSIAN_CA", None)
            roots = load_grpc_root_certificates()
        self.assertIsNotNone(roots)
        self.assertEqual(roots.count(b"-----BEGIN CERTIFICATE-----"), 2)

    def test_russian_ca_files_shipped_with_repo(self):
        certs_dir = _russian_trusted_ca_dir()
        self.assertTrue((certs_dir / "russian_trusted_root_ca.pem").is_file())
        self.assertTrue((certs_dir / "russian_trusted_sub_ca.pem").is_file())

    def test_load_grpc_root_certificates_custom_path(self):
        pem = _russian_trusted_ca_dir() / "russian_trusted_root_ca.pem"
        with patch.dict(
            os.environ,
            {"TINVEST_GRPC_ROOT_CERTS": str(pem)},
            clear=False,
        ):
            roots = load_grpc_root_certificates()
        self.assertIn(b"-----BEGIN CERTIFICATE-----", roots)


if __name__ == "__main__":
    unittest.main()
