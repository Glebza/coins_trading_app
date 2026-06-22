"""T-Invest session configuration for live trading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from exchanges.tinvest_broker import (
    resolve_grpc_target,
    resolve_production_account_id,
    resolve_sandbox_account_id,
)


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TinvestSession:
    """Credentials and runtime flags for T-Invest live/sandbox access."""

    token: str
    account_id: str
    sandbox: bool
    target: Optional[str] = None

    @classmethod
    def from_env(cls) -> "TinvestSession":
        token = os.environ.get("INVEST_TOKEN") or os.environ.get("T_INVEST_TOKEN")
        if not token:
            raise ValueError("INVEST_TOKEN or T_INVEST_TOKEN is required")

        sandbox = _env_flag("TINVEST_SANDBOX", default=True)
        target = resolve_grpc_target(sandbox=sandbox, target=os.environ.get("TINVEST_TARGET"))
        if sandbox:
            account_id = resolve_sandbox_account_id(token, target=target)
        else:
            account_id = resolve_production_account_id(token, target=target)

        return cls(
            token=token,
            account_id=account_id,
            sandbox=sandbox,
            target=target,
        )
