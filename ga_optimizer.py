"""
シフト最適化コア（遺伝的アルゴリズム）
PuLP版と同じ入出力インターフェースを持つ。

依存: numpy のみ（pip install numpy）
"""

import random
import time
from collections import defaultdict
from typing import Union

import numpy as np

DAY_ORDER  = ["月", "火", "水", "木", "金", "土", "日"]
SLOT_ORDER = ["AM", "PM"]

# -----------------------------------------------
# 染色体の表現
# -----------------------------------------------
# candidates: availability のうち shifts に対応する (name, day, slot) のリスト
# 染色体: candidates と同じ長さの 0/1 の numpy 配列
# candidates[i] = 1 → そのスタッフをそのシフト枠に割り当てる

def _build_candidates(availability: set, shifts: dict) -> list:
    """割り当て候補リストを構築する。"""
    return [
        (name, day, slot)
        for (name, day, slot) in sorted(availability)
        if (day, slot) in shifts
    ]


# -----------------------------------------------
# 評価関数
# -----------------------------------------------
def _evaluate(
    chrom: np.ndarray,
    candidates: list,
    shifts: dict,
    staff_constraints: dict,
    fixed_assignments: set,
    staff_skills: dict,
    shift_skills: dict,
    penalty: float = 10.0,
    fairness_weight: float = 0.0,
) -> float:
    """
    染色体を評価してスコアを返す（大きいほど良い）。

    スコア = 充足人数の合計
           - penalty × 制約違反数
           - fairness_weight × (最大シフト数 - 最小シフト数)

    制約違反:
        V1. 1人1日1枠を超えた割り当て数
        V2. 各枠の必要人数を超えた割り当て数
        V3. 固定割り当てが 0 になっている数
        V4. min_shifts を下回った数
        V5. max_shifts を超えた数
        V6. 連続勤務上限を超えたウィンドウ数
        V7. スキル要件を満たさない（不足人数）
    """
    # 割り当て結果を集計
    assigned_by_name_day = defaultdict(list)  # {(name,day): [slot,...]}
    assigned_by_shift    = defaultdict(list)  # {(day,slot): [name,...]}
    assigned_by_name     = defaultdict(list)  # {name: [(day,slot),...]}

    for i, val in enumerate(chrom):
        if val == 1:
            name, day, slot = candidates[i]
            assigned_by_name_day[(name, day)].append(slot)
            assigned_by_shift[(day, slot)].append(name)
            assigned_by_name[name].append((day, slot))

    violations = 0.0

    # V1: 1人1日1枠
    for slots in assigned_by_name_day.values():
        if len(slots) > 1:
            violations += len(slots) - 1

    # V2: 各枠の上限
    for (day, slot), required in shifts.items():
        actual = len(assigned_by_shift[(day, slot)])
        if actual > required:
            violations += actual - required

    # V3: 固定割り当て
    for (name, day, slot) in fixed_assignments:
        idx = next(
            (i for i, c in enumerate(candidates) if c == (name, day, slot)), None
        )
        if idx is not None and chrom[idx] == 0:
            violations += 1

    # V4/V5: min/max シフト数
    for name, c in staff_constraints.items():
        count = len(assigned_by_name[name])
        if c.get("min_shifts") is not None and count < c["min_shifts"]:
            violations += c["min_shifts"] - count
        if c.get("max_shifts") is not None and count > c["max_shifts"]:
            violations += count - c["max_shifts"]

    # V6: 連続勤務上限
    for name, c in staff_constraints.items():
        max_consec = c.get("max_consecutive")
        if max_consec is None:
            continue
        window = max_consec + 1
        worked_days = {day for day, slot in assigned_by_name[name]}
        for start in range(len(DAY_ORDER) - max_consec):
            window_days = DAY_ORDER[start: start + window]
            count_in_window = sum(1 for d in window_days if d in worked_days)
            if count_in_window > max_consec:
                violations += count_in_window - max_consec

    # V7: スキル制約（y変数相当の判定）
    if staff_skills and shift_skills:
        for (day, slot), skill_reqs in shift_skills.items():
            assigned_names = assigned_by_shift[(day, slot)]
            # 各スキルについて、担当できる人数を数える
            # ただし1人は1スキルしか担当できないため貪欲に割り当てる
            remaining = list(assigned_names)
            for skill, req in skill_reqs.items():
                capable = [n for n in remaining if skill in staff_skills.get(n, set())]
                assigned_count = min(len(capable), req)
                # 担当済みとしてマーク（貪欲）
                for n in capable[:assigned_count]:
                    remaining.remove(n)
                if assigned_count < req:
                    violations += req - assigned_count

    # 充足スコア（ベース）
    fulfillment_score = sum(
        min(len(assigned_by_shift[(day, slot)]), required)
        for (day, slot), required in shifts.items()
    )

    # 公平性スコア（最大・最小シフト数の差を最小化）
    shift_counts = [len(v) for v in assigned_by_name.values()]
    fairness_penalty = 0.0
    if fairness_weight > 0.0 and len(shift_counts) >= 2:
        fairness_penalty = fairness_weight * (max(shift_counts) - min(shift_counts))

    return fulfillment_score - penalty * violations - fairness_penalty


# -----------------------------------------------
# 遺伝的操作
# -----------------------------------------------
def _random_chrom(candidates: list, shifts: dict, rng: random.Random) -> np.ndarray:
    """ランダムな染色体を生成する。"""
    return np.array([rng.randint(0, 1) for _ in candidates], dtype=np.int8)


def _crossover(p1: np.ndarray, p2: np.ndarray, rng: random.Random) -> tuple:
    """一点交叉。"""
    point = rng.randint(1, len(p1) - 1)
    c1 = np.concatenate([p1[:point], p2[point:]])
    c2 = np.concatenate([p2[:point], p1[point:]])
    return c1, c2


def _mutate(chrom: np.ndarray, mutation_rate: float, rng: random.Random) -> np.ndarray:
    """ビット反転突然変異。"""
    mask = np.array([rng.random() < mutation_rate for _ in chrom], dtype=bool)
    return np.where(mask, 1 - chrom, chrom).astype(np.int8)


def _tournament_select(
    population: list,
    scores: list,
    k: int,
    rng: random.Random,
) -> np.ndarray:
    """トーナメント選択。k 個をランダムに選び最も良い個体を返す。"""
    idxs = rng.sample(range(len(population)), k)
    best = max(idxs, key=lambda i: scores[i])
    return population[best].copy()


# -----------------------------------------------
# メインの GA ループ
# -----------------------------------------------
def solve_ga(
    availability: set,
    shifts: dict,
    staff_constraints: dict = None,
    fixed_assignments: set  = None,
    staff_skills: dict      = None,
    shift_skills: dict      = None,
    pop_size: int           = 100,
    n_generations: int      = 300,
    mutation_rate: float    = 0.02,
    tournament_k: int       = 3,
    penalty: float          = 10.0,
    seed: int               = 42,
    fairness_weight: float  = 0.0,
) -> dict:
    """
    遺伝的アルゴリズムでシフト最適化を解く。
    PuLP版の solve() と同じ形式の辞書を返す。

    Parameters
    ----------
    pop_size      : 個体数
    n_generations : 世代数
    mutation_rate : 突然変異率（1遺伝子あたりの反転確率）
    tournament_k  : トーナメント選択のサイズ
    penalty       : 制約違反1件あたりのペナルティ
    seed          : 乱数シード（再現性のため）
    """
    if staff_constraints is None:
        staff_constraints = {}
    if fixed_assignments is None:
        fixed_assignments = set()
    if staff_skills is None:
        staff_skills = {}
    if shift_skills is None:
        shift_skills = {}

    rng = random.Random(seed)
    np.random.seed(seed)

    start_time = time.time()

    candidates = _build_candidates(availability, shifts)
    if not candidates:
        return _empty_result(shifts)

    # 評価関数の引数をまとめる
    eval_kwargs = dict(
        candidates        = candidates,
        shifts            = shifts,
        staff_constraints = staff_constraints,
        fixed_assignments = fixed_assignments,
        staff_skills      = staff_skills,
        shift_skills      = shift_skills,
        penalty           = penalty,
        fairness_weight   = fairness_weight,
    )

    # 初期個体群
    population = [_random_chrom(candidates, shifts, rng) for _ in range(pop_size)]
    scores     = [_evaluate(c, **eval_kwargs) for c in population]

    best_chrom = population[int(np.argmax(scores))].copy()
    best_score = max(scores)

    history = []  # 世代ごとのベストスコア（比較グラフ用）

    for gen in range(n_generations):
        new_population = []

        # エリート保存（ベスト1個体をそのまま次世代へ）
        new_population.append(best_chrom.copy())

        while len(new_population) < pop_size:
            p1 = _tournament_select(population, scores, tournament_k, rng)
            p2 = _tournament_select(population, scores, tournament_k, rng)
            c1, c2 = _crossover(p1, p2, rng)
            c1 = _mutate(c1, mutation_rate, rng)
            c2 = _mutate(c2, mutation_rate, rng)
            new_population.extend([c1, c2])

        population = new_population[:pop_size]
        scores     = [_evaluate(c, **eval_kwargs) for c in population]

        gen_best_idx   = int(np.argmax(scores))
        gen_best_score = scores[gen_best_idx]
        history.append(gen_best_score)

        if gen_best_score > best_score:
            best_score = gen_best_score
            best_chrom = population[gen_best_idx].copy()

    elapsed = time.time() - start_time

    # ベスト染色体から結果を集計
    assigned          = defaultdict(list)
    assigned_by_staff = defaultdict(list)

    for i, val in enumerate(best_chrom):
        if val == 1:
            name, day, slot = candidates[i]
            assigned[(day, slot)].append(name)
            assigned_by_staff[name].append((day, slot))

    fulfillment = {}
    for (day, slot), required in shifts.items():
        actual = len(assigned.get((day, slot), []))
        fulfillment[(day, slot)] = {
            "required":  required,
            "actual":    actual,
            "satisfied": actual >= required,
        }

    total_required = sum(v["required"] for v in fulfillment.values())
    total_actual   = sum(v["actual"]   for v in fulfillment.values())

    shift_counts  = [len(v) for v in assigned_by_staff.values()] if assigned_by_staff else [0]
    fairness_gap  = max(shift_counts) - min(shift_counts) if len(shift_counts) >= 2 else 0

    return {
        "status":            "GA",
        "assigned":          dict(assigned),
        "assigned_by_staff": dict(assigned_by_staff),
        "fulfillment":       fulfillment,
        "total_required":    total_required,
        "total_actual":      total_actual,
        "fill_rate":         total_actual / total_required if total_required > 0 else 0.0,
        "elapsed":           elapsed,
        "history":           history,
        "fairness_gap":      fairness_gap,
    }


def _empty_result(shifts: dict) -> dict:
    """候補が空のときのフォールバック。"""
    fulfillment = {
        (day, slot): {"required": req, "actual": 0, "satisfied": False}
        for (day, slot), req in shifts.items()
    }
    total_required = sum(v["required"] for v in fulfillment.values())
    return {
        "status": "GA", "assigned": {}, "assigned_by_staff": {},
        "fulfillment": fulfillment,
        "total_required": total_required, "total_actual": 0, "fill_rate": 0.0,
        "elapsed": 0.0, "history": [],
    }