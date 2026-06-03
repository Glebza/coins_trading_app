import sys

print(
    "framework.instruments CLI moved to: python -m manutil <command>\n"
    "Commands: sync-shares | load-klines-all | load-klines | update-volatility",
    file=sys.stderr,
)
raise SystemExit(1)
