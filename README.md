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

### Терминология Карвера (для блока 2)

- **Trading rule** — один чистый алгоритм. Pure function: `prices → scaled forecast ∈ [-20, +20]`,
  средний `|forecast| ≈ 10`. Примеры: `EWMAC`, `breakout`, `carry`, `RSI mean-reversion`.
- **Trading rule variation** — та же rule с другой параметризацией.
  Например, `EWMAC(2,8)`, `EWMAC(8,32)`, `EWMAC(64,256)` — три вариации одного правила.
- **Combined forecast** (блок 3) — взвешенная сумма прогнозов нескольких rules / variations,
  домноженная на FDM и снова обрезанная до ±20. Связка вида "EWMAC + RSI + Bollinger" — это
  уже combined forecast, **а не одно правило**.
- **Trading model / strategy** — combined forecast + позицирование + риск-менеджмент.
  Это уже не правило, а целая система (блоки 2–6).

### Жёсткие требования к правилу

1. **Continuous, не binary.** Чем сильнее сигнал — тем больше forecast. Никаких `if/else`,
   никаких "режимов", никаких резких порогов (cliff edges).
2. **Unitless / instrument-invariant.** Forecast не должен зависеть от номинала цены инструмента.
   Достигается либо отношением (числитель и знаменатель в одних единицах), либо делением на
   оценку волатильности инструмента в тех же единицах.
3. **Scaled to ±20, avg(|forecast|) ≈ 10.** После домножения на `forecast_scalar` среднее
   абсолютное значение forecast по истории должно быть ~10. Cap = 20.
4. **No instrument-specific tuning.** `forecast_scalar` считается **через все инструменты сразу**,
   не per-instrument. Иначе — неявный overfitting.
5. **Идея, не паттерн.** У правила должна быть экономическая/поведенческая/структурная гипотеза,
   почему оно работает. См. шаблон ниже.

### Шаблон гипотезы

Перед тем как писать формулу нового правила, заполнить ВСЕ пять пунктов. Если хотя бы один
не заполняется — это не гипотеза, а догадка; возвращаемся думать. Бэктест на этом этапе
**не открываем**, чтобы не было implicit overfitting.

```markdown
# Hypothesis: <короткое snake_case имя, например "trend_following_eqty_ru">

## One-liner
<одно предложение: что и почему>

## 1. Cause (причина)
<2–4 предложения: какой экономический / поведенческий / структурный механизм работает.
Что заставляет цены вести себя именно так?>

## 2. Effect (testable claim)
<что именно мы должны увидеть в данных, в количественных терминах>
- Direction: <up / down / abs / cross-sectional spread>
- Magnitude: <ожидаемый размер движения, в bps или σ>
- Statistical signature: <автокорреляция / cross-sectional spread / event study / ...>

## 3. Conditions (условия применимости)
- Universe: <какие инструменты — например, ликвидные акции MOEX>
- Regime: <какие режимы рынка / vol / liquidity>
- Sample: <сколько лет истории нужно для проверки>

## 4. Horizon (горизонт)
- Signal lookback: <сколько дней / часов смотрим назад>
- Holding period: <сколько держим позицию>

## 5. Why hasn't it been arbitraged away?
<один абзац: capacity limit / compensation for risk / costs / behavioral persistence /
regulatory constraints. Если ответа нет — гипотеза, скорее всего, мёртвая.>

## Falsifiability (когда выбрасываем гипотезу)
- Минимальный Sharpe для принятия (после costs): <число, обычно > 0.2 для сырого rule>
- Минимальная доля инструментов с положительным PnL: <доля, обычно > 0.5>
- Если <конкретное событие в бэктесте> — гипотеза опровергнута.

## Implementation sketch
- raw_forecast = <формула в терминах OHLCV / производных>
- vol normalization: <как делим на vol>
- предполагаемый forecast_scalar: <грубая оценка>
- planned variations: <например, [(2,8), (8,32), (64,256)] для EWMAC-семейства>
```

### Примеры заполненных гипотез

**Trend-following (под EWMAC).** Институциональные инвесторы добавляют позиции медленно из‑за
мандата и ограничений на market impact → серия однонаправленных потоков на горизонте недель/месяцев.
Поведенчески: участники недореагируют на новости (anchoring + disposition effect).
Эффект: положительная автокорреляция месячных доходностей с лагом 1–6 мес. Universe: ликвидные
акции с большой долей институционалов. Horizon: lookback 1–12 мес, holding недели–месяцы.
Почему не арбитражировано: эффект — плата за хвостовой риск трендовых стратегий (большие просадки
во время разворотов). Формула: `(EMA_fast - EMA_slow) / instrument_vol_in_price_units`.

**Mean-reversion (под RSI / Bollinger fade).** Маркет-мейкеры и арбитражёры обеспечивают ликвидность
на коротких горизонтах; при отклонении цены от средней без новой фундаментальной информации они
входят на возврат. Эффект: слабая отрицательная автокорреляция дневных доходностей **в спокойных
режимах волатильности**. Условие: фильтр по vol-of-vol. Horizon: сигнал на минутах/часах,
удержание часы/дни. Почему не арбитражировано: capacity limit (для крупных фондов transaction costs
больше edge). **Важно**: на трендовых рынках гипотеза проигрывает — поэтому MR-правило не должно
быть единственным, только в портфеле с trend-following.

### Где гипотеза рождается мёртвой (антипаттерны)

- ❌ "Я взял три индикатора и они дали хорошую кривую на бэктесте" — reverse engineering.
- ❌ "На графике видно, что после трёх красных свечей часто идёт зелёная" — паттерн без причины.
- ❌ Sharpe = 2.5 в бэктесте без объяснения почему — почти всегда переподгонка.
- ❌ Гипотеза, которая работает только на одном тикере — выборка слишком мала.
- ❌ В формулировке больше двух условий "и/или" — почти наверняка fitting.

### Источники гипотез

1. **Академика (SSRN / journals)**: Jegadeesh & Titman 1993 (momentum), Fama & French 1992 (value),
   Koijen et al. 2018 (carry), Frazzini & Pedersen 2014 (BAB), De Bondt & Thaler 1985 (LT reversal),
   Bernard & Thomas 1989 (post-earnings drift).
2. **Поведенческие искажения**: underreaction, overreaction, disposition, anchoring, herding.
3. **Структурные потоки**: index rebalancing (MOEX index review), quarter/year-end, futures roll,
   margin call cascades, ETF creation/redemption, дивидендные отсечки.
4. **Макро**: фазы business cycle, заседания ЦБ, inflation regimes.
5. **Микроструктура** (если есть intraday): order flow imbalance, bid-ask bounce,
   open/close auction dislocations.

### Чек-лист "правило готово к production"

- [ ] Гипотеза заполнена по шаблону выше.
- [ ] Реализовано как pure function: `pd.DataFrame(OHLCV) → pd.Series(forecast)`.
- [ ] Forecast unitless и не зависит от номинала цены.
- [ ] Forecast continuous, без `if/else` и резких порогов.
- [ ] `forecast_scalar` посчитан через весь универсум так, что `mean(|forecast|) ≈ 10`.
- [ ] Forecast clipped в ±20.
- [ ] Минимум 3 разумные вариации (разные lookback'и).
- [ ] Sharpe правила положительный после costs на > 50% инструментов универсума.
- [ ] Корреляция нового правила с уже существующими ≤ ~0.85 (иначе дублирует).
- [ ] Turnover приемлем для класса инструмента (для акций RU — не более ~10–20 разворотов в год).

---

## Volatility

- Цель по **Sharpe ratio**: **1.0**.
- Целевая **percentage volatility**: **27%**.

---

## Сборка вселенной акций (черновик пайплайна)

- Для каждой акции — **дневные свечи** за последние **5 лет** (или больше, см. выше).
- **Медианная дневная волатильность** — отобрать, например, **> 2%** (уточнить под финальную методику).
- **Медианный объём** и сравнение **медианы с 75-м перцентилем** по распределению дневных объёмов.


Вопросы сплошняком:
как считать slippage? 



