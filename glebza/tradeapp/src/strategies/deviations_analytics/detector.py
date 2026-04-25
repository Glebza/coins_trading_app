"""
Rule-based детектор паттернов боковика с уровнями Фибоначчи.

Логика паттерна:
1. P1 = кульминация продаж/покупок (экстремум - самый верх или низ)
2. P2 = первичный тест противоположного уровня (откат)
3. P3 = закрытие бара максимально близкое к P1 или P2 (на уровне Фибо)

Фибоначчи строится от P1 к P2:
- Уровень 1.0 всегда сверху (= box_high)
- Уровень 0.0 всегда снизу (= box_low)
- Стандартные уровни: 0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0

P3 должен касаться одного из уровней Фибоначчи (желательно близко к 0 или 1).
"""

import argparse
import csv
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

# Стандартные уровни Фибоначчи
FIBO_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


@dataclass
class Pattern:
    """Найденный паттерн."""
    p1_idx: int
    p2_idx: int
    p3_idx: int
    p1_price: float
    p2_price: float
    p3_price: float
    pattern_type: int  # 1=bullish (P1 сверху), 2=bearish (P1 снизу)
    box_low: float
    box_high: float
    confidence: float
    p3_fibo_level: float  # На каком уровне Фибо находится P3


def price_to_fibo_level(price: float, box_low: float, box_high: float) -> float:
    """
    Конвертирует цену в уровень Фибоначчи.
    
    box_low = 0.0, box_high = 1.0
    """
    if box_high == box_low:
        return 0.5
    return (price - box_low) / (box_high - box_low)


def find_nearest_fibo_level(fibo_value: float) -> Tuple[float, float]:
    """
    Находит ближайший стандартный уровень Фибо.
    
    Returns:
        (nearest_level, distance)
    """
    distances = [(abs(fibo_value - level), level) for level in FIBO_LEVELS]
    min_dist, nearest = min(distances, key=lambda x: x[0])
    return nearest, min_dist


def find_local_extrema(prices: np.ndarray, window: int = 5) -> Tuple[np.ndarray, np.ndarray]:
    """
    Находит локальные максимумы и минимумы.
    
    Returns:
        maxima_idx: индексы локальных максимумов
        minima_idx: индексы локальных минимумов
    """
    n = len(prices)
    maxima = []
    minima = []
    
    for i in range(window, n - window):
        window_prices = prices[i - window:i + window + 1]
        center_price = prices[i]
        
        if center_price == window_prices.max():
            maxima.append(i)
        elif center_price == window_prices.min():
            minima.append(i)
    
    return np.array(maxima), np.array(minima)


def find_impulse(prices: np.ndarray, min_pct: float = 0.01, lookback: int = 20) -> List[Tuple[int, int, float]]:
    """
    Находит импульсные движения.
    
    Returns:
        Список (start_idx, end_idx, direction) где direction = 1 (вверх) или -1 (вниз)
    """
    impulses = []
    n = len(prices)
    
    for i in range(lookback, n):
        # Ищем резкое движение за последние lookback свечей
        start_price = prices[i - lookback]
        end_price = prices[i]
        change_pct = (end_price - start_price) / start_price
        
        if abs(change_pct) >= min_pct:
            direction = 1 if change_pct > 0 else -1
            impulses.append((i - lookback, i, direction))
    
    return impulses


def find_p2_after_p1(
    prices: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    p1_idx: int,
    p1_price: float,
    pattern_type: int,
    max_distance: int = 40,
    min_retrace_pct: float = 0.3,
) -> Optional[Tuple[int, float]]:
    """
    Ищет P2 — противоположный экстремум после P1.
    
    P1 = уровень 1.0 или 0.0 (в зависимости от типа)
    P2 = уровень 0.0 или 1.0 (противоположный)
    
    Для bullish (P1 = максимум = 1.0): P2 = минимум = 0.0
    Для bearish (P1 = минимум = 0.0): P2 = максимум = 1.0
    """
    n = len(prices)
    search_end = min(p1_idx + max_distance, n)
    
    if pattern_type == 1:  # Bullish: P1 сверху (1.0), ищем P2 снизу (0.0)
        # Ищем минимум в окне после P1
        search_range = lows[p1_idx + 3:search_end]
        if len(search_range) == 0:
            return None
        min_idx_local = np.argmin(search_range)
        p2_idx = p1_idx + 3 + min_idx_local
        p2_price = float(lows[p2_idx])
        
        # Проверяем что P2 достаточно ниже P1
        retrace = (p1_price - p2_price) / p1_price
        if retrace < min_retrace_pct * 0.01:  # min_retrace_pct в %
            return None
            
    else:  # Bearish: P1 снизу (0.0), ищем P2 сверху (1.0)
        search_range = highs[p1_idx + 3:search_end]
        if len(search_range) == 0:
            return None
        max_idx_local = np.argmax(search_range)
        p2_idx = p1_idx + 3 + max_idx_local
        p2_price = float(highs[p2_idx])
        
        retrace = (p2_price - p1_price) / p1_price
        if retrace < min_retrace_pct * 0.01:
            return None
    
    return p2_idx, p2_price


def find_p3_confirmation(
    prices: np.ndarray,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    p1_idx: int,
    p2_idx: int,
    p1_price: float,
    p2_price: float,
    pattern_type: int,
    max_distance: int = 40,
    fibo_tolerance: float = 0.12,  # 12% допуск до уровня Фибо
) -> Optional[Tuple[int, float, float]]:
    """
    Ищет P3 — точка закрытия бара на уровне Фибоначчи близком к P1 или P2.
    
    P3 должен:
    1. Быть после P2
    2. Закрыться близко к уровню Фибоначчи (особенно 0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)
    3. Максимально близко к P1 или P2 по цене
    
    Returns:
        (idx, price, fibo_level) или None
    """
    n = len(closes)
    search_start = p2_idx + 3
    search_end = min(p2_idx + max_distance, n)
    
    box_low = min(p1_price, p2_price)
    box_high = max(p1_price, p2_price)
    
    best_p3 = None
    best_fibo_dist = float('inf')
    
    # P3 = "закрытие бара максимально приближённое или равное P1 или P2"
    # Значит P3 допустим ТОЛЬКО рядом с уровнем 0.0 (= цена P2) или 1.0 (= цена P1)
    # Никаких промежуточных уровней — 0.236, 0.382, 0.5, 0.618, 0.786 НЕ допускаются
    allowed_levels = [0.0, 1.0]
    
    for i in range(search_start, search_end):
        close = closes[i]
        
        # Вычисляем уровень Фибо для этой цены
        fibo_level = price_to_fibo_level(close, box_low, box_high)
        
        # P3 должен быть в пределах бокса
        if fibo_level < -0.15 or fibo_level > 1.15:
            continue
        
        # Расстояние до ближайшего допустимого уровня (0.0 или 1.0)
        dist_to_0 = abs(fibo_level - 0.0)
        dist_to_1 = abs(fibo_level - 1.0)
        
        if dist_to_0 < dist_to_1:
            nearest_level = 0.0
            fibo_dist = dist_to_0
        else:
            nearest_level = 1.0
            fibo_dist = dist_to_1
        
        # P3 должен быть достаточно близко к P1 или P2
        if fibo_dist > fibo_tolerance:
            continue
        
        if fibo_dist < best_fibo_dist:
            best_fibo_dist = fibo_dist
            best_p3 = (i, close, nearest_level)
    
    return best_p3


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                period: int = 14) -> np.ndarray:
    """
    Average True Range — мера волатильности.
    
    True Range = max(high-low, |high-prev_close|, |low-prev_close|)
    ATR = скользящее среднее TR за period свечей
    """
    n = len(closes)
    tr = np.zeros(n, dtype=np.float32)
    
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    
    # Простое скользящее среднее
    atr = np.zeros(n, dtype=np.float32)
    for i in range(n):
        start = max(0, i - period + 1)
        atr[i] = tr[start:i + 1].mean()
    
    return atr


def is_quality_impulse(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    atr: np.ndarray,
    p1_idx: int,
    p1_price: float,
    lookback: int = 15,
    min_atr_multiple: float = 2.0,
    min_directional_ratio: float = 0.55,
) -> Tuple[bool, float]:
    """
    Проверяет что перед P1 был настоящий импульс, а не шум на флэте.
    
    Критерии:
    1. Движение должно быть >= min_atr_multiple * ATR
       (на флэте ATR высокий относительно движения → отсеивается)
    2. Направленность: большинство свечей должны двигаться в одну сторону
       (на флэте свечи зигзагят → ratio низкий)
    3. Скорость: движение за lookback свечей должно быть резким
    
    Returns:
        (is_impulse, impulse_strength)
    """
    if p1_idx < lookback + 5:
        return False, 0.0
    
    # Окно до P1
    start = p1_idx - lookback
    window_closes = closes[start:p1_idx + 1]
    start_price = window_closes[0]
    end_price = p1_price
    
    # 1. Абсолютное движение vs ATR
    move = abs(end_price - start_price)
    local_atr = atr[p1_idx]
    
    if local_atr <= 0:
        return False, 0.0
    
    atr_multiple = move / local_atr
    if atr_multiple < min_atr_multiple:
        return False, 0.0
    
    # 2. Направленность — какая доля свечей двигалась в сторону импульса
    direction = 1 if end_price > start_price else -1
    directional_count = 0
    total = len(window_closes) - 1
    
    for i in range(1, len(window_closes)):
        if direction > 0 and window_closes[i] > window_closes[i - 1]:
            directional_count += 1
        elif direction < 0 and window_closes[i] < window_closes[i - 1]:
            directional_count += 1
    
    if total <= 0:
        return False, 0.0
    
    directional_ratio = directional_count / total
    if directional_ratio < min_directional_ratio:
        return False, 0.0
    
    # 3. Сравнение с предшествующим периодом — до импульса должно быть спокойнее
    # Смотрим ATR за период ДО импульса (предыдущие lookback свечей)
    pre_start = max(0, start - lookback)
    if pre_start < start:
        pre_atr = atr[start]
        # Импульсное движение должно быть значительно больше предыдущей волатильности
        pre_range = (highs[pre_start:start].max() - lows[pre_start:start].min()
                     if start > pre_start else move)
        if move < pre_range * 0.8:
            # Движение не превышает предыдущий диапазон — это не импульс, это продолжение флэта
            return False, 0.0
    
    # Strength = atr_multiple * directional_ratio (чем больше, тем качественнее)
    strength = atr_multiple * directional_ratio
    
    return True, strength


def detect_patterns(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    min_box_pct: float = 0.5,
    max_p1_p3_distance: int = 80,
    impulse_pct: float = 1.0,
    impulse_lookback: int = 15,
    min_atr_multiple: float = 2.0,
    min_directional_ratio: float = 0.55,
) -> List[Pattern]:
    """
    Детектирует паттерны боковика на основе правил.
    
    Улучшенная фильтрация импульсов:
    - ATR-фильтр: импульс должен быть >= min_atr_multiple * ATR
    - Направленность: >= min_directional_ratio свечей в одну сторону  
    - Контекст: движение должно быть сильнее предыдущего диапазона
    """
    patterns = []
    n = len(closes)
    
    # Предрассчитываем ATR для всех данных
    atr = compute_atr(highs, lows, closes, period=14)
    
    # Находим локальные экстремумы
    maxima_idx, minima_idx = find_local_extrema(closes, window=5)
    
    # Для каждого экстремума пробуем построить паттерн
    all_extrema = []
    for idx in maxima_idx:
        all_extrema.append((idx, highs[idx], 1))  # 1 = это максимум (P1 сверху = bullish)
    for idx in minima_idx:
        all_extrema.append((idx, lows[idx], 2))  # 2 = это минимум (P1 снизу = bearish)
    
    # Сортируем по индексу
    all_extrema.sort(key=lambda x: x[0])
    
    last_pattern_idx = -100  # Для min_gap
    
    for p1_idx, p1_price, pattern_type in all_extrema:
        if p1_idx < 30:  # Нужен контекст до P1 (для ATR тоже)
            continue
        if p1_idx - last_pattern_idx < 50:  # min_gap
            continue
        
        # === Проверяем качество импульса ===
        
        # Базовая проверка процента (быстрая отсечка)
        lookback = min(impulse_lookback, p1_idx)
        start_price = closes[p1_idx - lookback]
        change_pct = abs((p1_price - start_price) / start_price) * 100
        
        if change_pct < impulse_pct:
            continue
        
        # Углублённая проверка качества импульса (ATR + направленность + контекст)
        is_impulse, strength = is_quality_impulse(
            closes, highs, lows, atr,
            p1_idx, p1_price,
            lookback=lookback,
            min_atr_multiple=min_atr_multiple,
            min_directional_ratio=min_directional_ratio,
        )
        
        if not is_impulse:
            continue
        
        # Ищем P2
        p2_result = find_p2_after_p1(
            closes, highs, lows,
            p1_idx, p1_price, pattern_type,
            max_distance=40,
            min_retrace_pct=min_box_pct,
        )
        
        if p2_result is None:
            continue
        
        p2_idx, p2_price = p2_result
        
        # Проверяем ширину бокса
        box_pct = abs(p1_price - p2_price) / min(p1_price, p2_price) * 100
        if box_pct < min_box_pct:
            continue
        
        # Ищем P3
        p3_result = find_p3_confirmation(
            closes, closes, highs, lows,
            p1_idx, p2_idx, p1_price, p2_price, pattern_type,
            max_distance=40,
            fibo_tolerance=0.08,
        )
        
        if p3_result is None:
            continue
        
        p3_idx, p3_price, p3_fibo_level = p3_result
        
        # Проверяем расстояние P1→P3
        if p3_idx - p1_idx > max_p1_p3_distance:
            continue
        
        # Вычисляем confidence на основе качества паттерна
        box_low = min(p1_price, p2_price)
        box_high = max(p1_price, p2_price)
        
        # Confidence = комбинация качества Фибо + силы импульса
        # P3 может быть только на 0.0 или 1.0 (= цена P2 или P1)
        fibo_score = 1.0  # всегда максимум, раз P3 на уровне P1/P2
        
        # Бонус от силы импульса (strength обычно 1.5-5.0)
        impulse_bonus = min(0.1, (strength - 1.0) * 0.03)
        
        confidence = min(0.99, fibo_score * 0.85 + impulse_bonus + 0.1)
        
        pattern = Pattern(
            p1_idx=p1_idx,
            p2_idx=p2_idx,
            p3_idx=p3_idx,
            p1_price=p1_price,
            p2_price=p2_price,
            p3_price=p3_price,
            pattern_type=pattern_type,
            box_low=box_low,
            box_high=box_high,
            confidence=confidence,
            p3_fibo_level=p3_fibo_level,
        )
        patterns.append(pattern)
        last_pattern_idx = p3_idx
    
    return patterns


def load_csv(path: str) -> dict:
    """Загружает данные из CSV."""
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            timestamps.append(int(row[0]))
            opens.append(float(row[1]))
            highs.append(float(row[2]))
            lows.append(float(row[3]))
            closes.append(float(row[4]))
    
    return {
        "timestamp": np.array(timestamps),
        "open": np.array(opens, dtype=np.float32),
        "high": np.array(highs, dtype=np.float32),
        "low": np.array(lows, dtype=np.float32),
        "close": np.array(closes, dtype=np.float32),
    }


def main():
    parser = argparse.ArgumentParser(description="Rule-based pattern detector")
    parser.add_argument("--data-path", required=True, help="Path to CSV")
    parser.add_argument("--min-box-pct", type=float, default=0.5, help="Min box width %")
    parser.add_argument("--max-distance", type=int, default=80, help="Max P1→P3 distance")
    parser.add_argument("--impulse-pct", type=float, default=1.0, help="Min impulse %")
    args = parser.parse_args()
    
    data = load_csv(args.data_path)
    print(f"Загружено {len(data['close'])} свечей")
    
    patterns = detect_patterns(
        data["open"],
        data["high"],
        data["low"],
        data["close"],
        min_box_pct=args.min_box_pct,
        max_p1_p3_distance=args.max_distance,
        impulse_pct=args.impulse_pct,
    )
    
    print(f"\nНайдено паттернов: {len(patterns)}")
    
    if patterns:
        print("\nТоп-10 по confidence:")
        sorted_patterns = sorted(patterns, key=lambda p: p.confidence, reverse=True)
        for i, p in enumerate(sorted_patterns[:10]):
            box_pct = (p.box_high - p.box_low) / p.box_low * 100
            p1_p3_dist = p.p3_idx - p.p1_idx
            type_str = "Bullish" if p.pattern_type == 1 else "Bearish"
            print(f"  {i+1}. [{p.p3_idx}] {type_str} | P1@{p.p1_idx} P2@{p.p2_idx} P3@{p.p3_idx} | "
                  f"dist={p1_p3_dist} | box={box_pct:.2f}% | P3 Fibo={p.p3_fibo_level:.3f} | conf={p.confidence:.2f}")


if __name__ == "__main__":
    main()
