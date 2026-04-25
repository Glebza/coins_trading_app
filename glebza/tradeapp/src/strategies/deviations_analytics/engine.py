"""
DeviTrade — Trading Engine
============================
Торговый движок: API Bybit, PaperTrade, TradingEngine.
Вся бизнес-логика стратегии девиаций.
"""

import sys
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict
from pathlib import Path

import numpy as np
import requests

from PySide6.QtCore import Signal, QObject

from detector import detect_patterns, Pattern, FIBO_LEVELS  # noqa: E402

# ================================================================
#  Paths
# ================================================================

if getattr(sys, 'frozen', False):
    _APP_DIR = Path(sys.executable).resolve().parent
else:
    _APP_DIR = Path(__file__).resolve().parent

LOGS_DIR = _APP_DIR / 'logs'
REALDATA_DIR = _APP_DIR / 'realdata'

# ================================================================
#  Helpers
# ================================================================

def ts_to_str(ts_ms, fmt="%m-%d %H:%M"):
    if not ts_ms:
        return "N/A"
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime(fmt)


def format_price(price):
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    return f"{price:.6f}"


def fibo_price(box_low, box_high, level):
    return box_low + (box_high - box_low) * level


# ================================================================
#  Bybit API
# ================================================================

def fetch_klines(symbol, interval="5", limit=200, end_time=None):
    url = "https://api.bybit.com/v5/market/kline"
    params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
    if end_time:
        params["end"] = end_time
    try:
        r = requests.get(url, params=params, timeout=10)
        d = r.json()
        if d.get("retCode") != 0:
            return []
        klines = d["result"]["list"]
        klines.sort(key=lambda x: int(x[0]))
        return klines
    except Exception:
        return []


def fetch_full_history(symbol, n_candles=2000):
    all_data = []
    end_time = None
    while len(all_data) < n_candles:
        batch = fetch_klines(symbol, "5", 200, end_time)
        if not batch:
            break
        all_data.extend(batch)
        end_time = int(batch[0][0])
        time.sleep(0.15)
    seen = set()
    unique = []
    for k in all_data:
        ts = int(k[0])
        if ts not in seen:
            seen.add(ts)
            unique.append(k)
    unique.sort(key=lambda x: int(x[0]))
    unique = unique[-n_candles:]
    ts = np.array([int(k[0]) for k in unique], dtype=np.int64)
    o = np.array([float(k[1]) for k in unique])
    h = np.array([float(k[2]) for k in unique])
    l = np.array([float(k[3]) for k in unique])
    c = np.array([float(k[4]) for k in unique])
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c}


def append_new_candles(data, symbol):
    latest_ts = int(data["timestamp"][-1])
    klines = fetch_klines(symbol, "5", 50)
    if not klines:
        return 0
    added = 0
    for k in klines:
        ts = int(k[0])
        if ts > latest_ts:
            data["timestamp"] = np.append(data["timestamp"], ts)
            data["open"] = np.append(data["open"], float(k[1]))
            data["high"] = np.append(data["high"], float(k[2]))
            data["low"] = np.append(data["low"], float(k[3]))
            data["close"] = np.append(data["close"], float(k[4]))
            added += 1
        elif ts == latest_ts:
            idx = len(data["close"]) - 1
            data["high"][idx] = max(data["high"][idx], float(k[2]))
            data["low"][idx] = min(data["low"][idx], float(k[3]))
            data["close"][idx] = float(k[4])
    return added


# ================================================================
#  Trade data
# ================================================================

@dataclass
class PaperTrade:
    id: int
    symbol: str
    direction: str
    entry_price: float
    entry_ts: int
    stop_price: float
    tp_prices: List[float]
    tp_portions: List[float]
    position_usd: float
    leverage: float
    box_low: float
    box_high: float
    status: str = 'open'
    remaining: float = 1.0
    tp_hits: int = 0
    realized_pnl: float = 0.0
    stopped: bool = False
    fully_closed: bool = False
    close_ts: int = 0
    close_reason: str = ''


# ================================================================
#  Trading Engine
# ================================================================

class TradingEngine(QObject):
    log_signal = Signal(str)
    state_updated = Signal(dict)
    finished = Signal()

    def __init__(self, settings: dict, coins: List[str]):
        super().__init__()
        self.settings = settings
        self.coins = coins
        self._running = False
        self.data: Dict[str, dict] = {}
        self.patterns: Dict[str, List[Pattern]] = {}
        self.equity = settings["initial_capital"]
        self.initial_capital = settings["initial_capital"]
        self.open_trades: List[PaperTrade] = []
        self.closed_trades: List[PaperTrade] = []
        self.trade_counter = 0
        self.known_box_keys: Dict[str, set] = {c: set() for c in coins}
        self.box_cooldowns: Dict[str, float] = {}
        self.coin_dir_cooldowns: Dict[str, float] = {}
        self.total_signals = 0
        self.total_skipped = 0
        self.candle_updates = 0
        self.equity_history: List[dict] = []
        self.start_time = 0.0
        LOGS_DIR.mkdir(exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = LOGS_DIR / f"live_{ts_str}.txt"

    def _log(self, msg):
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        line = f"[{timestamp}] {msg}"
        self.log_signal.emit(line)
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass

    def _box_key(self, pat):
        return f"{pat.p1_idx}_{pat.p2_idx}_{pat.p3_idx}"

    def stop(self):
        self._running = False

    def run(self):
        self._running = True
        self.start_time = time.time()
        duration = self.settings["live_duration_hours"] * 3600
        s = self.settings
        self._log(f"=== LIVE PAPER TRADING START ===")
        self._log(f"Монеты: {len(self.coins)} | Длительность: {s['live_duration_hours']}ч")
        self._log(f"Капитал: ${self.equity:,.0f} | Риск: {s['risk_per_trade']}% | Плечо: {s['max_leverage']}x")
        self._log("")
        for coin in self.coins:
            if not self._running:
                break
            self._log(f"  Загрузка {coin}...")
            data = fetch_full_history(coin, s["bootstrap_candles"])
            if len(data["close"]) < 100:
                self._log(f"  ПРОПУСК: {coin} (мало свечей)")
                continue
            self.data[coin] = data
            patterns = detect_patterns(
                data['open'], data['high'], data['low'], data['close'],
                impulse_pct=s["impulse_pct"])
            self.patterns[coin] = patterns
            for p in patterns:
                self.known_box_keys[coin].add(self._box_key(p))
            self._log(f"  {coin}: {len(data['close'])} свечей, {len(patterns)} боксов, "
                      f"цена={data['close'][-1]:.4f}")
        self._log(f"\nЗагрузка завершена. {len(self.data)} монет.")
        self._log(f"{'=' * 60}\n")
        self._emit_state()
        last_status = 0
        last_pattern = 0
        poll = s["poll_interval_sec"]
        while self._running:
            elapsed = time.time() - self.start_time
            if elapsed >= duration:
                break
            now = time.time()
            for coin in list(self.data.keys()):
                if not self._running:
                    break
                new = append_new_candles(self.data[coin], coin)
                if new > 0:
                    self.candle_updates += new
                self._check_trades(coin)
                self._scan_deviations(coin)
                time.sleep(0.1)
            if now - last_pattern >= 300:
                for coin in list(self.data.keys()):
                    if not self._running:
                        break
                    self._update_patterns(coin)
                last_pattern = now
            if now - last_status >= 120:
                self._emit_state()
                last_status = now
            for _ in range(int(poll)):
                if not self._running:
                    break
                time.sleep(1)
        self._close_all_trades()
        self._emit_state()
        self._log("\n=== СЕССИЯ ЗАВЕРШЕНА ===")
        self.finished.emit()

    def _check_trades(self, symbol):
        if symbol not in self.data:
            return
        data = self.data[symbol]
        n = len(data["close"])
        if n < 2:
            return
        hi = float(data["high"][n - 1])
        lo = float(data["low"][n - 1])
        ts = int(data["timestamp"][n - 1])
        fee = self.settings["fee_rate"] / 100.0
        for trade in self.open_trades:
            if trade.symbol != symbol or trade.status != 'open':
                continue
            hit_stop = ((trade.direction == 'long' and lo <= trade.stop_price) or
                        (trade.direction == 'short' and hi >= trade.stop_price))
            if hit_stop:
                portion_usd = trade.position_usd * trade.remaining
                pnl_pct = ((trade.stop_price - trade.entry_price) / trade.entry_price
                           if trade.direction == 'long' else
                           (trade.entry_price - trade.stop_price) / trade.entry_price)
                pnl = portion_usd * pnl_pct - portion_usd * fee
                trade.realized_pnl += pnl
                trade.remaining = 0
                trade.stopped = True
                trade.status = 'closed'
                trade.close_ts = ts
                trade.close_reason = 'STOP'
                self.equity += pnl
                self._log(f"  *** СТОП *** {symbol} {trade.direction.upper()} "
                          f"#{trade.id} | PnL: ${trade.realized_pnl:+,.2f} | Баланс: ${self.equity:,.2f}")
                now = time.time()
                bk = f"{symbol}_{trade.box_low:.6f}_{trade.box_high:.6f}"
                self.box_cooldowns[bk] = now + self.settings["box_cooldown_min"] * 60
                dk = f"{symbol}_{trade.direction}"
                self.coin_dir_cooldowns[dk] = now + self.settings["dir_cooldown_min"] * 60
                self.closed_trades.append(trade)
                self._emit_state()
                continue
            for tp_idx, (tp_price, portion) in enumerate(zip(trade.tp_prices, trade.tp_portions)):
                if tp_idx < trade.tp_hits:
                    continue
                hit_tp = ((trade.direction == 'long' and hi >= tp_price) or
                          (trade.direction == 'short' and lo <= tp_price))
                if not hit_tp:
                    break
                portion_usd = trade.position_usd * portion
                pnl_pct = ((tp_price - trade.entry_price) / trade.entry_price
                           if trade.direction == 'long' else
                           (trade.entry_price - tp_price) / trade.entry_price)
                pnl = portion_usd * pnl_pct - portion_usd * fee
                trade.realized_pnl += pnl
                trade.remaining -= portion
                trade.tp_hits += 1
                self.equity += pnl
                self._log(f"  +++ ТП{trade.tp_hits} +++ {symbol} {trade.direction.upper()} "
                          f"#{trade.id} | PnL: ${trade.realized_pnl:+,.2f} | Баланс: ${self.equity:,.2f}")
                self._emit_state()
            if trade.remaining < 1e-6:
                trade.fully_closed = True
                trade.status = 'closed'
                trade.close_ts = ts
                trade.close_reason = f'ПОЛНЫЙ_{trade.tp_hits}ТП'
                self.closed_trades.append(trade)
                self._log(f"  === ПОЛНОЕ ЗАКРЫТИЕ === {symbol} #{trade.id} | Итого: ${trade.realized_pnl:+,.2f}")
                self._emit_state()
        self.open_trades = [t for t in self.open_trades if t.status == 'open']

    def _scan_deviations(self, symbol):
        if symbol not in self.data:
            return
        s = self.settings
        if len(self.open_trades) >= s["max_open_total"]:
            return
        if sum(1 for t in self.open_trades if t.symbol == symbol and t.status == 'open') >= s["max_open_per_coin"]:
            return
        data = self.data[symbol]
        n = len(data["close"])
        if n < 50:
            return
        now = time.time()
        for pat in self.patterns.get(symbol, []):
            if pat.p3_idx < n - 500:
                continue
            bl, bh = pat.box_low, pat.box_high
            br = bh - bl
            mid = (bl + bh) / 2.0
            if br / mid * 10000 < s["min_box_range_bp"]:
                continue
            bk = f"{symbol}_{bl:.6f}_{bh:.6f}"
            if bk in self.box_cooldowns and now < self.box_cooldowns[bk]:
                continue
            tol = br * s["retest_tol"] / 100.0
            if any(t.symbol == symbol and t.box_low == bl and t.box_high == bh for t in self.open_trades):
                continue
            self._scan_range(data, symbol, max(pat.p3_idx + 1, n - 100), n, bl, bh, br, tol, pat)

    def _scan_range(self, data, symbol, start, end, bl, bh, br, tol, pat=None):
        s = self.settings
        n = end
        i = start
        fee = s["fee_rate"] / 100.0
        cb = s["confirm_bars"]
        mdd = s["min_dev_depth"] / 100.0
        while i < n - cb - 1:
            hi_v = float(data["high"][i])
            lo_v = float(data["low"][i])
            dt = 'bottom' if lo_v < bl else ('top' if hi_v > bh else None)
            if dt is None:
                i += 1
                continue
            de = lo_v if dt == 'bottom' else hi_v
            hco = False
            ret = False
            j = i
            while j < min(n, i + 40):
                if dt == 'bottom':
                    de = min(de, float(data["low"][j]))
                    if float(data["close"][j]) < bl:
                        hco = True
                    if float(data["close"][j]) >= bl:
                        ret = True
                        j += 1
                        break
                else:
                    de = max(de, float(data["high"][j]))
                    if float(data["close"][j]) > bh:
                        hco = True
                    if float(data["close"][j]) <= bh:
                        ret = True
                        j += 1
                        break
                j += 1
            if not ret:
                i = j
                continue
            if not hco:
                i = j
                continue
            depth = (bl - de) / br if dt == 'bottom' else (de - bh) / br
            if depth < mdd:
                i = j
                continue
            cc = 0
            conf = False
            k = j
            while k < min(n, j + 15):
                if bl <= float(data["close"][k]) <= bh:
                    cc += 1
                    if cc >= cb:
                        conf = True
                        k += 1
                        break
                else:
                    cc = 0
                k += 1
            if not conf:
                i = k
                continue
            ri = None
            for m in range(k, min(n, k + 80)):
                if dt == 'bottom':
                    if float(data["low"][m]) <= bl + tol and float(data["close"][m]) >= bl - tol * 0.3:
                        ri = m
                        break
                else:
                    if float(data["high"][m]) >= bh - tol and float(data["close"][m]) <= bh + tol * 0.3:
                        ri = m
                        break
            if ri is None:
                i = k + 1
                continue
            if ri < n - 3:
                i = ri + 1
                continue
            if dt == 'bottom':
                d = 'long'
                ep = bl
                sp = de
                tpl = [0.295, 0.5, 0.705, 1.0]
            else:
                d = 'short'
                ep = bh
                sp = de
                tpl = [0.705, 0.5, 0.295, 0.0]
            dk = f"{symbol}_{d}"
            if dk in self.coin_dir_cooldowns and time.time() < self.coin_dir_cooldowns[dk]:
                self.total_skipped += 1
                i = ri + 1
                continue
            tpp = [fibo_price(bl, bh, lv) for lv in tpl]
            tppo = [0.3, 0.3, 0.2, 0.2]
            sd = abs(ep - sp)
            if sd < 1e-8 or (d == 'long' and sp >= ep) or (d == 'short' and sp <= ep):
                i = ri + 1
                continue
            if sd / ep * 100 > s["max_stop_pct"]:
                i = ri + 1
                continue
            if (d == 'long' and tpp[0] <= ep) or (d == 'short' and tpp[0] >= ep):
                i = ri + 1
                continue
            dd_pct = (self.initial_capital - self.equity) / self.initial_capital
            if dd_pct > s["max_drawdown_pct"] / 100.0:
                self._log(f"  [СТОП ПО ПРОСАДКЕ] {dd_pct * 100:.1f}%")
                return
            rm = 0.5 if dd_pct > 0.10 else (0.75 if dd_pct > 0.05 else 1.0)
            ra = self.equity * (s["risk_per_trade"] / 100.0) * rm
            max_pos = self.equity * s.get("max_position_pct", 100.0) / 100.0
            pu = min(ra / (sd / ep), self.equity * s["max_leverage"], max_pos)
            lv = pu / self.equity if self.equity > 0 else 0
            if any(t.symbol == symbol and t.direction == d and abs(t.entry_price - ep) / ep < 0.001
                   for t in self.open_trades):
                i = ri + 1
                continue
            self.trade_counter += 1
            self.total_signals += 1
            trade = PaperTrade(
                id=self.trade_counter, symbol=symbol, direction=d,
                entry_price=ep, entry_ts=int(data["timestamp"][ri]), stop_price=sp,
                tp_prices=tpp, tp_portions=tppo, position_usd=pu, leverage=lv,
                box_low=bl, box_high=bh)
            self.open_trades.append(trade)
            self.equity -= pu * fee
            self._log(f"\n>>> СИГНАЛ #{trade.id} {symbol} {d.upper()} <<<")
            if pat:
                p1_ts = ts_to_str(int(data["timestamp"][pat.p1_idx]), "%Y-%m-%d %H:%M")
                p2_ts = ts_to_str(int(data["timestamp"][pat.p2_idx]), "%Y-%m-%d %H:%M")
                p3_ts = ts_to_str(int(data["timestamp"][pat.p3_idx]), "%Y-%m-%d %H:%M")
                pt = "Bullish" if pat.pattern_type == 1 else "Bearish"
                self._log(f"  Паттерн: {pt} | P3 Fibo: {pat.p3_fibo_level:.3f}")
                self._log(f"  P1: {pat.p1_price:.4f} [{p1_ts}] свеча #{pat.p1_idx}")
                self._log(f"  P2: {pat.p2_price:.4f} [{p2_ts}] свеча #{pat.p2_idx}")
                self._log(f"  P3: {pat.p3_price:.4f} [{p3_ts}] свеча #{pat.p3_idx}")
                self._log(f"  Бокс: {bl:.4f} — {bh:.4f} (ширина {br/((bl+bh)/2)*100:.2f}%)")
            self._log(f"  Вход: {ep:.4f} | Стоп: {sp:.4f}")
            self._log(f"  ТП1-4: {', '.join(f'{p:.4f}' for p in tpp)}")
            self._log(f"  Размер: ${pu:,.2f} | Плечо: {lv:.1f}x")
            self._emit_state()
            i = ri + 1

    def _update_patterns(self, coin):
        if coin not in self.data:
            return
        data = self.data[coin]
        patterns = detect_patterns(
            data['open'], data['high'], data['low'], data['close'],
            impulse_pct=self.settings["impulse_pct"])
        nc = sum(1 for p in patterns if self._box_key(p) not in self.known_box_keys[coin])
        for p in patterns:
            self.known_box_keys[coin].add(self._box_key(p))
        if nc > 0:
            self._log(f"  {coin}: {nc} нов. бокс(ов) (всего {len(patterns)})")
        self.patterns[coin] = patterns

    def _close_all_trades(self):
        fee = self.settings["fee_rate"] / 100.0
        for trade in self.open_trades:
            if trade.symbol in self.data:
                lp = float(self.data[trade.symbol]["close"][-1])
                pu = trade.position_usd * trade.remaining
                pp = ((lp - trade.entry_price) / trade.entry_price if trade.direction == 'long'
                      else (trade.entry_price - lp) / trade.entry_price)
                pnl = pu * pp - pu * fee
                trade.realized_pnl += pnl
                trade.status = 'closed'
                trade.close_reason = 'КОНЕЦ_СЕССИИ'
                self.equity += pnl
                self.closed_trades.append(trade)
                self._log(f"  Закрытие #{trade.id} {trade.symbol}: ${trade.realized_pnl:+,.2f}")
        self.open_trades.clear()

    def _emit_state(self):
        now_t = time.time()
        elapsed = now_t - self.start_time if self.start_time else 0
        dur = self.settings["live_duration_hours"] * 3600
        rem = max(0, dur - elapsed)
        topnl = 0.0
        ol = []
        for t in self.open_trades:
            lp = float(self.data[t.symbol]["close"][-1]) if t.symbol in self.data else 0.0
            upnl = ((lp - t.entry_price) / t.entry_price if t.direction == 'long'
                    else (t.entry_price - lp) / t.entry_price) * t.position_usd * t.remaining
            topnl += upnl
            ol.append({
                'id': t.id, 'symbol': t.symbol, 'direction': t.direction,
                'entry_price': t.entry_price, 'stop_price': t.stop_price, 'tp_prices': t.tp_prices,
                'tp_hits': t.tp_hits, 'remaining': t.remaining, 'realized_pnl': t.realized_pnl,
                'position_usd': t.position_usd, 'leverage': t.leverage, 'current_price': lp,
                'unrealized_pnl': upnl, 'box_low': t.box_low, 'box_high': t.box_high,
                'entry_ts': t.entry_ts,
            })
        cll = [{
            'id': t.id, 'symbol': t.symbol, 'direction': t.direction,
            'entry_price': t.entry_price, 'realized_pnl': t.realized_pnl,
            'close_reason': t.close_reason, 'tp_hits': t.tp_hits,
            'leverage': t.leverage, 'entry_ts': t.entry_ts,
            'close_ts': t.close_ts, 'stopped': t.stopped,
        } for t in self.closed_trades]
        prices = {
            c: float(self.data[c]["close"][-1])
            for c in self.coins if c in self.data and len(self.data[c]["close"]) > 0
        }
        # Chart data for ALL coins (last 500 candles)
        chart_data = {}
        for sym in self.data:
            d = self.data[sym]
            nn = len(d["close"])
            sl = slice(max(0, nn - 500), nn)
            chart_data[sym] = {
                'timestamp': d["timestamp"][sl].tolist(),
                'open': d["open"][sl].tolist(),
                'high': d["high"][sl].tolist(),
                'low': d["low"][sl].tolist(),
                'close': d["close"][sl].tolist(),
            }
        # Patterns data for chart overlays
        # Индексы точек нужно сдвинуть на offset, т.к. chart_data — срез последних 500 свечей
        patterns_data = {}
        for sym, pats in self.patterns.items():
            d = self.data.get(sym)
            if not d:
                continue
            nn = len(d["close"])
            offset = max(0, nn - 500)
            sym_pats = []
            for p in pats:
                # Пропускаем паттерны, полностью вне видимого диапазона
                if p.p3_idx < offset:
                    continue
                sym_pats.append({
                    'p1_idx': max(0, p.p1_idx - offset),
                    'p2_idx': max(0, p.p2_idx - offset),
                    'p3_idx': p.p3_idx - offset,
                    'p1_price': p.p1_price,
                    'p2_price': p.p2_price,
                    'p3_price': p.p3_price,
                    'box_low': p.box_low,
                    'box_high': p.box_high,
                    'p3_fibo_level': p.p3_fibo_level,
                })
            patterns_data[sym] = sym_pats
        self.equity_history.append({
            'ts': int(now_t * 1000),
            'equity': self.equity,
            'open_pnl': topnl,
            'mtm': self.equity + topnl,
        })
        cpnl = sum(t.realized_pnl for t in self.closed_trades)
        wins = sum(1 for t in self.closed_trades if t.realized_pnl > 0)
        losses = len(self.closed_trades) - wins
        wp = sum(t.realized_pnl for t in self.closed_trades if t.realized_pnl > 0)
        lp2 = sum(t.realized_pnl for t in self.closed_trades if t.realized_pnl <= 0)
        pf = abs(wp / lp2) if lp2 != 0 else 0.0
        self.state_updated.emit({
            'equity': self.equity, 'initial_capital': self.initial_capital,
            'open_pnl': topnl, 'mtm': self.equity + topnl,
            'ret_pct': (self.equity - self.initial_capital) / self.initial_capital * 100,
            'mtm_ret': (self.equity + topnl - self.initial_capital) / self.initial_capital * 100,
            'elapsed': elapsed, 'remaining': rem, 'duration': dur,
            'closed_pnl': cpnl, 'wins': wins, 'losses': losses,
            'win_rate': wins / max(1, wins + losses) * 100, 'pf': pf,
            'total_signals': self.total_signals, 'total_skipped': self.total_skipped,
            'candle_updates': self.candle_updates,
            'open_trades': ol, 'closed_trades': cll, 'prices': prices,
            'chart_data': chart_data, 'patterns_data': patterns_data,
            'equity_history': self.equity_history[-500:],
        })
