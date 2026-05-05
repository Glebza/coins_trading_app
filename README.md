# Coins trading app

Фреймворк в духе подхода Роберта Карвера к книге [**Systematic Trading**](https://www.systematictrading.org/).

---

## Крупные блоки

1. **Инструменты** — чем торгуем (фьючерсы, акции и т.д.).
2. **Trading rules and forecasts** — правила и прогнозы.
3. **Combined forecasts** — комбинирование сигналов.
4. **Volatility targeting** — целевой риск.
5. **Scaled positions** — масштабирование позиций.
6. **Portfolios** — портфели.
7. **Speed and size** — горизонты и размер.

---

## Модуль инструментов

В коде: `glebza/tradeapp/src/framework/instruments`.

**Источник рыночных и справочных данных в приложении** — **T‑Invest API** (Т‑Банк Инвестиции): котировки, свечи, карточки инструментов; в Python используется SDK **`t-tech-investments`** (`t_tech.invest`). Официальный портал: [developer.tbank.ru/invest](https://developer.tbank.ru/invest).

Дополнительно, для справочников биржи (в т.ч. то, чего нет в T‑Invest — например, уровни котировальных списков), ориентир **MOEX ISS**: [iss.moex.com/iss/reference](https://iss.moex.com/iss/reference/).

Планируемые классы активов: акции, облигации, фьючерсы, ETF, опционы.

### Акции (требования и заметки)

- История: не **менее 10 лет** тому назад.
- Абсолютная цена бумаги **не главный фильтр** (на РФ нет экстремально «дорогих» лотов в западном смысле).
- Важно понимать драйверы капитализации; возможны **фундаментальные ограничения**.
- Отбор по **достаточной волатильности** и **ликвидности**.
- Диверсификация: число эмитентов, сектора, **низкая корреляция** между именами.
- **Комиссии брокера** по акциям считаем одинаковыми для упрощения.
- **Skew** — отдельно проработать расчёт, если войдёт в стратегию.

### Первый отбор: ликвидность + волатильность (backtest-схема)

Идея: оставить инструменты из **верхнего квартиля** по **медиане дневного объёма** (в лотах, см. T‑Invest) и по **последней сохранённой дневной annualized volatility**, исключить **только для квалов**.

Ниже пример запроса к БД `backtest`, схема `backtests` (при необходимости сузьте окно дат по `kline_1d.k_interval`).

```sql
WITH per_ticker AS (
  SELECT
    ticker_id,
    percentile_disc(0.5) WITHIN GROUP (ORDER BY volume) AS med_volume
  FROM backtests.kline_1d
  -- optional: WHERE k_interval >= DATE '2024-01-01'
  GROUP BY ticker_id
),
med_vol_thresh AS (
  SELECT percentile_disc(0.80) WITHIN GROUP (ORDER BY med_volume) AS p80
  FROM per_ticker
),
latest_vol AS (
  SELECT DISTINCT ON (instrument_id)
    instrument_id,
    annualized_volatility,
    as_of AS vol_as_of,
    interval_name
  FROM backtests.instrument_volatility
  WHERE interval_name = '1d'
  ORDER BY instrument_id, as_of DESC
),
vol_thresh AS (
  SELECT percentile_disc(0.80) WITHIN GROUP (ORDER BY annualized_volatility) AS p80
  FROM latest_vol
)
SELECT
  i.ticker,
  i_s.name,
  i_s.for_qual_investor_flag,
  i_s.api_trade_available_flag,
  p.med_volume,
  lv.annualized_volatility,
  lv.vol_as_of,
  lv.interval_name
FROM backtests.instruments i
JOIN backtests.instrument_share i_s ON i.id = i_s.instrument_id
JOIN per_ticker p ON i.id = p.ticker_id
JOIN latest_vol lv ON i.id = lv.instrument_id
CROSS JOIN med_vol_thresh mvt
CROSS JOIN vol_thresh vt
WHERE p.med_volume >= mvt.p80
  AND lv.annualized_volatility >= vt.p80
  AND NOT i_s.for_qual_investor_flag;
```
В дальнейшем нужно добавить не только акции, а также расширить количество инструментов для торгов. еще нужно увидеть корреляцию между инструментами и выбрать максимально нескоррелированные 
---

## Trading rules and forecasts

В коде: `glebza/tradeapp/src/framework/forecasts.py`.

---

## Volatility

- Цель по **Sharpe ratio**: **1.0**.
- Целевая **percentage volatility**: **27%**.

---

## Сборка вселенной акций (черновик пайплайна)

- Для каждой акции — **дневные свечи** за последние **5 лет** (или больше, см. выше).
- **Медианная дневная волатильность** — отобрать, например, **> 2%** (уточнить под финальную методику).
- **Медианный объём** и сравнение **медианы с 75-м перцентилем** по распределению дневных объёмов.
