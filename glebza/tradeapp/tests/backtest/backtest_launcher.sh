#!/bin/bash

# Properly escape the DATABASE_URL and avoid spaces around the '=' sign
export API_KEY=ZaJjmroJ67mRpRwPyd7LWKjMgePLBZWoTkiMuegL3sDVjdtnZGIvKlpy86ZveOjw
export API_SECRET=MdV1q449CFOQ2vbims8cZ3NMmbc3RtayL5GgTN2rlpfKdbgw4UmVPe68TKyUdUtf
export DATABASE_URL="postgresql+psycopg://trader:Coins_for_coins%211@pikouledet.beget.app:5432/traderDB?options=-csearch_path%3Dbacktests"
export DATABASE_DEFAULT_SCHEMA=backtests
export PYTHONPATH="${PYTHONPATH}:/Users/glebskalatsky/PycharmProjects/coins_trading_app"
# Get input parameters
start_dtm=$1
end_dtm=$2

# Ensure both parameters are provided
if [ -z "$start_dtm" ] || [ -z "$end_dtm" ]; then
  echo "Error: Please provide start_dtm and end_dtm as arguments."
  echo "Usage: $0 <start_dtm> <end_dtm>"
  exit 1
fi

echo "Starting backtest from $start_dtm to $end_dtm"

# Run the Python script with the provided parameters
python3 /Users/glebskalatsky/PycharmProjects/coins_trading_app/glebza/tradeapp/tests/backtest/test_deviations_strategy.py \
  --kline_interval=1m \
  --backtest_start_date="$start_dtm" \
  --backtest_end_date="$end_dtm" \
  --backtest_interval=day \
  --start_cash=1000 \
  --symbol=BTCUSDT
