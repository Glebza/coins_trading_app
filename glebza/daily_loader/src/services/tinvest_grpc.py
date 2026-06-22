"""T-Invest gRPC client with Russian CA roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

import grpc
from t_tech.invest._error_hub import init_error_hub
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.services import Services
from t_tech.invest.typedefs import ChannelArgumentType

_RUSSIAN_CA_FILES = ("russian_trusted_root_ca.pem", "russian_trusted_sub_ca.pem")


def _read_pem(path: Path) -> bytes:
    text = path.read_text(encoding="ascii").strip()
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("ascii")


def _ca_bundle() -> bytes:
    custom = os.environ.get("TINVEST_GRPC_ROOT_CERTS", "").strip()
    if custom:
        return _read_pem(Path(custom))

    base = Path(__file__).resolve().parents[2] / "certs"
    if not base.is_dir():
        base = Path(__file__).resolve().parents[3] / "tradeapp" / "certs"

    chunks: list[bytes] = []
    try:
        import certifi

        chunks.append(_read_pem(Path(certifi.where())))
    except ImportError:
        pass
    for name in _RUSSIAN_CA_FILES:
        path = base / name
        if path.is_file():
            chunks.append(_read_pem(path))
    if not chunks:
        raise ValueError(f"no CA certificates found in {base}")
    return b"".join(chunks)


def create_channel(*, target: Optional[str] = None, options: Optional[ChannelArgumentType] = None) -> grpc.Channel:
    from t_tech.invest.channels import _required_options, _with_options

    effective = target or INVEST_GRPC_API
    channel_options = _with_options(list(options or []), _required_options)
    creds = grpc.ssl_channel_credentials(root_certificates=_ca_bundle())
    return grpc.secure_channel(effective, creds, options=channel_options)


class TinvestClient:
    def __init__(self, token: str, *, target: Optional[str] = None) -> None:
        self._token = token
        self._target = target
        self._channel = create_channel(target=target)

    def __enter__(self) -> Services:
        init_error_hub(self)
        channel = self._channel.__enter__()
        return Services(channel, token=self._token)

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._channel.__exit__(exc_type, exc_val, exc_tb)
        return False
