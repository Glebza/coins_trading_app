"""T-Invest gRPC channel factory with explicit CA roots.

T-Invest API endpoints are signed by НУЦ Минцифры РФ. Mozilla/certifi alone is not enough;
see https://developer.tinkoff.ru/invest/intro/intro/cases (certificate errors section).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

import grpc
from t_tech.invest._error_hub import init_error_hub
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.services import Services
from t_tech.invest.typedefs import ChannelArgumentType

_RUSSIAN_TRUSTED_CA_FILES = (
    "russian_trusted_root_ca.pem",
    "russian_trusted_sub_ca.pem",
)


def _env_truthy(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _read_pem_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="ascii").strip()
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("ascii")


def _russian_trusted_ca_dir() -> Path:
    # glebza/tradeapp/certs — sibling of src/
    return Path(__file__).resolve().parents[2] / "certs"


def _iter_russian_trusted_ca_paths() -> Iterable[Path]:
    custom_dir = os.environ.get("TINVEST_GRPC_RUSSIAN_CA_DIR", "").strip()
    base_dir = Path(custom_dir) if custom_dir else _russian_trusted_ca_dir()
    for filename in _RUSSIAN_TRUSTED_CA_FILES:
        path = base_dir / filename
        if path.is_file():
            yield path


def load_grpc_root_certificates() -> Optional[bytes]:
    """Return PEM roots for gRPC TLS, or None to use gRPC defaults."""
    custom_path = os.environ.get("TINVEST_GRPC_ROOT_CERTS", "").strip()
    if custom_path:
        return _read_pem_bytes(Path(custom_path))

    chunks: list[bytes] = []
    if _env_truthy("TINVEST_GRPC_USE_CERTIFI", default=True):
        try:
            import certifi

            chunks.append(_read_pem_bytes(Path(certifi.where())))
        except ImportError:
            pass

    if _env_truthy("TINVEST_GRPC_USE_RUSSIAN_CA", default=True):
        for path in _iter_russian_trusted_ca_paths():
            chunks.append(_read_pem_bytes(path))

    if not chunks:
        return None
    return b"".join(chunks)


def create_tinvest_channel(
    *,
    target: Optional[str] = None,
    options: Optional[ChannelArgumentType] = None,
) -> grpc.Channel:
    from t_tech.invest.channels import _required_options, _with_options

    effective_target = target or INVEST_GRPC_API
    channel_options = _with_options(list(options or []), _required_options)
    roots = load_grpc_root_certificates()
    creds = grpc.ssl_channel_credentials(root_certificates=roots)
    return grpc.secure_channel(effective_target, creds, options=channel_options)


class TInvestGrpcClient:
    """Drop-in for ``t_tech.invest.Client`` with certifi + Russian CA TLS roots."""

    def __init__(
        self,
        token: str,
        *,
        target: Optional[str] = None,
        sandbox_token: Optional[str] = None,
        options: Optional[ChannelArgumentType] = None,
        app_name: Optional[str] = None,
    ) -> None:
        self._token = token
        self._sandbox_token = sandbox_token
        self._app_name = app_name
        self._target = target or INVEST_GRPC_API
        self._channel = create_tinvest_channel(target=target, options=options)

    def __enter__(self) -> Services:
        init_error_hub(self)
        channel = self._channel.__enter__()
        return Services(
            channel,
            token=self._token,
            sandbox_token=self._sandbox_token,
            app_name=self._app_name,
        )

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._channel.__exit__(exc_type, exc_val, exc_tb)
        return False
