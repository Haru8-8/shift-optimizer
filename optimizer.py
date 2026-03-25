"""
シフト最適化コア
使い方:
    pip install pulp
    python optimizer.py
    python optimizer.py --availability a.csv --shifts s.csv \
                        --constraints c.csv --fixed f.csv \
                        --staff-skills ss.csv --shift-skills sk.csv
"""

import argparse
import csv
import io
from collections import defaultdict
from typing import Union

import pulp

DAY_ORDER  = ["月", "火", "水", "木", "金", "土", "日"]
SLOT_ORDER = ["AM", "PM"]


# -----------------------------------------------
# ヘルパー
# -----------------------------------------------
def _open(source: Union[str, io.StringIO]):
    if isinstance(source, str):
        return open(source, encoding="utf-8", newline="")
    return source


def _check_columns(reader: csv.DictReader, required: set, filename: str):
    if reader.fieldnames is None:
        raise ValueError(f"{filename} が空です。")
    missing = required - {f.strip() for f in reader.fieldnames}
    if missing:
        raise ValueError(
            f"{filename} に必須カラムがありません: {', '.join(sorted(missing))}"
        )


def _parse_optional_int(row: dict, key: str, lineno: int, filename: str):
    val = row.get(key, "").strip()
    if not val:
        return None
    try:
        result = int(val)
    except ValueError:
        raise ValueError(
            f"{filename} の {lineno} 行目: {key} '{val}' は整数である必要があります。"
        )
    if result < 0:
        raise ValueError(
            f"{filename} の {lineno} 行目: {key} は 0 以上の値を指定してください。"
        )
    return result


# -----------------------------------------------
# CSV 読み込み
# -----------------------------------------------
def load_availability(source: Union[str, io.StringIO]) -> set:
    availability = set()
    f = _open(source)
    try:
        reader = csv.DictReader(f)
        _check_columns(reader, {"name", "day", "slot"}, "availability.csv")
        for i, row in enumerate(reader, start=2):
            name = row["name"].strip()
            day  = row["day"].strip()
            slot = row["slot"].strip()
            if not name or not day or not slot:
                raise ValueError(
                    f"availability.csv の {i} 行目に空の値があります: {dict(row)}"
                )
            if day not in DAY_ORDER:
                raise ValueError(
                    f"availability.csv の {i} 行目: day '{day}' は無効です。月〜日のいずれかを指定してください。"
                )
            if slot not in SLOT_ORDER:
                raise ValueError(
                    f"availability.csv の {i} 行目: slot '{slot}' は無効です。AM または PM を指定してください。"
                )
            availability.add((name, day, slot))
    finally:
        if isinstance(source, str):
            f.close()
    return availability


def load_shifts(source: Union[str, io.StringIO]) -> dict:
    shifts = {}
    f = _open(source)
    try:
        reader = csv.DictReader(f)
        _check_columns(reader, {"day", "slot", "required"}, "shifts.csv")
        for i, row in enumerate(reader, start=2):
            day  = row["day"].strip()
            slot = row["slot"].strip()
            if day not in DAY_ORDER:
                raise ValueError(f"shifts.csv の {i} 行目: day '{day}' は無効です。")
            if slot not in SLOT_ORDER:
                raise ValueError(f"shifts.csv の {i} 行目: slot '{slot}' は無効です。")
            try:
                required = int(row["required"].strip())
            except ValueError:
                raise ValueError(
                    f"shifts.csv の {i} 行目: required '{row['required']}' は整数である必要があります。"
                )
            if required < 0:
                raise ValueError(f"shifts.csv の {i} 行目: required は 0 以上の値を指定してください。")
            shifts[(day, slot)] = required
    finally:
        if isinstance(source, str):
            f.close()
    return shifts


def load_staff_constraints(source: Union[str, io.StringIO]) -> dict:
    constraints = {}
    f = _open(source)
    try:
        reader = csv.DictReader(f)
        _check_columns(reader, {"name"}, "staff_constraints.csv")
        for i, row in enumerate(reader, start=2):
            name = row.get("name", "").strip()
            if not name:
                raise ValueError(f"staff_constraints.csv の {i} 行目: name が空です。")
            constraints[name] = {
                "min_shifts":      _parse_optional_int(row, "min_shifts",      i, "staff_constraints.csv"),
                "max_shifts":      _parse_optional_int(row, "max_shifts",      i, "staff_constraints.csv"),
                "max_consecutive": _parse_optional_int(row, "max_consecutive", i, "staff_constraints.csv"),
            }
    finally:
        if isinstance(source, str):
            f.close()

    for name, c in constraints.items():
        if c["min_shifts"] is not None and c["max_shifts"] is not None:
            if c["min_shifts"] > c["max_shifts"]:
                raise ValueError(
                    f"staff_constraints.csv: {name} の min_shifts ({c['min_shifts']}) が "
                    f"max_shifts ({c['max_shifts']}) を超えています。"
                )
    return constraints


def load_fixed_assignments(source: Union[str, io.StringIO]) -> set:
    fixed = set()
    f = _open(source)
    try:
        reader = csv.DictReader(f)
        _check_columns(reader, {"name", "day", "slot"}, "fixed_assignments.csv")
        for i, row in enumerate(reader, start=2):
            name = row["name"].strip()
            day  = row["day"].strip()
            slot = row["slot"].strip()
            if not name or not day or not slot:
                raise ValueError(f"fixed_assignments.csv の {i} 行目に空の値があります。")
            if day not in DAY_ORDER:
                raise ValueError(f"fixed_assignments.csv の {i} 行目: day '{day}' は無効です。")
            if slot not in SLOT_ORDER:
                raise ValueError(f"fixed_assignments.csv の {i} 行目: slot '{slot}' は無効です。")
            fixed.add((name, day, slot))
    finally:
        if isinstance(source, str):
            f.close()
    return fixed


def load_staff_skills(source: Union[str, io.StringIO]) -> dict:
    """
    staff_skills.csv を読み込む。
    戻り値: {name: {skill, ...}}
    例: {'田中': {'レジ', 'キッチン'}, '鈴木': {'レジ'}}
    """
    skills = defaultdict(set)
    f = _open(source)
    try:
        reader = csv.DictReader(f)
        _check_columns(reader, {"name", "skill"}, "staff_skills.csv")
        for i, row in enumerate(reader, start=2):
            name  = row["name"].strip()
            skill = row["skill"].strip()
            if not name or not skill:
                raise ValueError(f"staff_skills.csv の {i} 行目に空の値があります。")
            skills[name].add(skill)
    finally:
        if isinstance(source, str):
            f.close()
    return dict(skills)


def load_shift_skills(source: Union[str, io.StringIO]) -> dict:
    """
    shift_skills.csv を読み込む。
    戻り値: {(day, slot): {skill: required_count, ...}}
    例: {('月', 'AM'): {'レジ': 1, 'キッチン': 1}}
    """
    shift_skills = defaultdict(dict)
    f = _open(source)
    try:
        reader = csv.DictReader(f)
        _check_columns(reader, {"day", "slot", "skill", "required"}, "shift_skills.csv")
        for i, row in enumerate(reader, start=2):
            day   = row["day"].strip()
            slot  = row["slot"].strip()
            skill = row["skill"].strip()
            if day not in DAY_ORDER:
                raise ValueError(f"shift_skills.csv の {i} 行目: day '{day}' は無効です。")
            if slot not in SLOT_ORDER:
                raise ValueError(f"shift_skills.csv の {i} 行目: slot '{slot}' は無効です。")
            if not skill:
                raise ValueError(f"shift_skills.csv の {i} 行目: skill が空です。")
            try:
                required = int(row["required"].strip())
            except ValueError:
                raise ValueError(
                    f"shift_skills.csv の {i} 行目: required '{row['required']}' は整数である必要があります。"
                )
            if required < 1:
                raise ValueError(f"shift_skills.csv の {i} 行目: required は 1 以上の値を指定してください。")
            shift_skills[(day, slot)][skill] = required
    finally:
        if isinstance(source, str):
            f.close()
    return dict(shift_skills)


# -----------------------------------------------
# バリデーション
# -----------------------------------------------
def validate_inputs(
    availability: set,
    shifts: dict,
    staff_constraints: dict,
    fixed_assignments: set,
    staff_skills: dict = None,
    shift_skills: dict = None,
) -> list:
    warnings = []
    staff_names = {name for name, _, _ in availability}

    for name, day, slot in fixed_assignments:
        if (name, day, slot) not in availability:
            warnings.append(
                f"固定割り当て: {name} の {day} {slot} は availability.csv に存在しません。"
                f"固定割り当てを有効にするには availability.csv にも追加してください。"
            )

    for name in staff_constraints:
        if name not in staff_names:
            warnings.append(f"staff_constraints.csv: {name} は availability.csv に存在しません。")

    available_shifts = {(day, slot) for _, day, slot in availability}
    for day, slot in available_shifts - set(shifts.keys()):
        warnings.append(
            f"availability.csv に {day} {slot} の出勤希望がありますが、"
            f"shifts.csv に対応するシフト枠がありません。"
        )

    # スキル関連の警告
    if staff_skills and shift_skills:
        for (day, slot), skill_reqs in shift_skills.items():
            if (day, slot) not in shifts:
                warnings.append(
                    f"shift_skills.csv: {day} {slot} は shifts.csv に存在しません。"
                )
                continue

            # スキル要件の合計がシフト必要人数を超えていないか
            total_skill_required = sum(skill_reqs.values())
            shift_required = shifts.get((day, slot), 0)
            if total_skill_required > shift_required:
                warnings.append(
                    f"{day} {slot}: スキル要件の合計人数 ({total_skill_required}) が "
                    f"シフト必要人数 ({shift_required}) を超えています。解なしになる可能性があります。"
                )

            for skill, req in skill_reqs.items():
                capable = sum(
                    1 for name, d, s in availability
                    if d == day and s == slot and skill in staff_skills.get(name, set())
                )
                if capable < req:
                    warnings.append(
                        f"{day} {slot} のスキル '{skill}' は {req} 名必要ですが、"
                        f"出勤可能なスタッフが {capable} 名しかいません。"
                    )

    if shift_skills and not staff_skills:
        warnings.append("shift_skills.csv がアップロードされていますが、staff_skills.csv がありません。スキル制約は無効になります。")

    if staff_skills and not shift_skills:
        warnings.append("staff_skills.csv がアップロードされていますが、shift_skills.csv がありません。スキル制約は無効になります。")

    return warnings


# -----------------------------------------------
# infeasible 分析
# -----------------------------------------------
def analyze_infeasible(
    availability: set,
    shifts: dict,
    staff_constraints: dict,
    fixed_assignments: set,
    staff_skills: dict = None,
    shift_skills: dict = None,
) -> list:
    """
    求解不能になりうる原因を分析してメッセージのリストを返す。
    solve() が Infeasible を返したときに呼び出す。
    """
    reasons = []

    # --- パターン1: 供給人数 < 必要人数 ---
    for (day, slot), required in shifts.items():
        available_count = sum(
            1 for name, d, s in availability if d == day and s == slot
        )
        if available_count < required:
            reasons.append(
                f"{day} {slot}: 必要人数 {required} 名に対して出勤可能なスタッフが {available_count} 名しかいません。"
            )

    # --- パターン2: min_shifts の合計 > 割り当て可能総数 ---
    total_min = sum(
        c["min_shifts"] for c in staff_constraints.values()
        if c.get("min_shifts") is not None
    )
    # 各スタッフの最大割り当て可能数（1日1枠なので出勤可能な日数が上限）
    staff_names = {name for name, _, _ in availability}
    total_capacity = sum(
        len({day for name2, day, slot in availability if name2 == name})
        for name in staff_names
    )
    if total_min > total_capacity:
        reasons.append(
            f"min_shifts の合計 ({total_min}) が全スタッフの出勤可能日数の合計 ({total_capacity}) を超えています。"
        )

    # --- パターン3: fixed_assignments の重複（同一スタッフ同一日に複数固定） ---
    fixed_by_name_day = defaultdict(list)
    for name, day, slot in fixed_assignments:
        fixed_by_name_day[(name, day)].append(slot)
    for (name, day), slots in fixed_by_name_day.items():
        if len(slots) > 1:
            reasons.append(
                f"固定割り当て: {name} の {day} に複数の枠 ({', '.join(slots)}) が固定されています。"
                f"1人1日1枠までしか割り当てできません。"
            )

    # --- パターン4: スキル制約で供給不足 ---
    if staff_skills and shift_skills:
        for (day, slot), skill_reqs in shift_skills.items():
            for skill, req in skill_reqs.items():
                capable = sum(
                    1 for name, d, s in availability
                    if d == day and s == slot and skill in staff_skills.get(name, set())
                )
                if capable < req:
                    reasons.append(
                        f"{day} {slot}: スキル '{skill}' を持つ出勤可能スタッフが {capable} 名しかいませんが {req} 名必要です。"
                    )

    if not reasons:
        reasons.append(
            "自動検出できませんでした。制約の組み合わせが複雑な可能性があります。"
            "max_consecutive や min_shifts を緩めてみてください。"
        )

    return reasons


# -----------------------------------------------
# 最適化
# -----------------------------------------------
def solve(
    availability: set,
    shifts: dict,
    staff_constraints: dict = None,
    fixed_assignments: set  = None,
    staff_skills: dict      = None,
    shift_skills: dict      = None,
    fairness_weight: float  = 0.0,
) -> dict:
    """
    fairness_weight > 0 のとき、目的関数に公平性項を追加する。

    目的関数:
        最大化: 充足スコア - fairness_weight × (最大シフト数 - 最小シフト数)

    公平性項はソフト制約なので、他に入れる人がいない場合は
    特定スタッフへの集中が起こることはある。
    min_shifts / max_shifts でハードに縛る方法と使い分けること。
    """
    if staff_constraints is None:
        staff_constraints = {}
    if fixed_assignments is None:
        fixed_assignments = set()
    if staff_skills is None:
        staff_skills = {}
    if shift_skills is None:
        shift_skills = {}

    prob = pulp.LpProblem("ShiftOptimizer", pulp.LpMaximize)

    x = {
        (name, day, slot): pulp.LpVariable(f"x_{name}_{day}_{slot}", cat="Binary")
        for (name, day, slot) in availability
        if (day, slot) in shifts
    }

    # スタッフ別シフト数の合計変数
    staff_names = sorted({name for name, _, _ in availability})
    by_name = defaultdict(list)
    for (name, day, slot), var in x.items():
        by_name[name].append(var)

    # 目的関数
    if fairness_weight > 0.0 and len(staff_names) >= 2:
        # 公平性のための補助変数（最大・最小シフト数）
        max_shifts_var = pulp.LpVariable("max_shifts_var", lowBound=0, cat="Integer")
        min_shifts_var = pulp.LpVariable("min_shifts_var", lowBound=0, cat="Integer")

        # 各スタッフのシフト数が max_shifts_var 以下・min_shifts_var 以上
        for name in staff_names:
            if by_name[name]:
                prob += pulp.lpSum(by_name[name]) <= max_shifts_var, f"FairnessMax_{name}"
                prob += pulp.lpSum(by_name[name]) >= min_shifts_var, f"FairnessMin_{name}"

        prob += (
            pulp.lpSum(x.values()) - fairness_weight * (max_shifts_var - min_shifts_var),
            "TotalAssigned_Fairness"
        )
    else:
        prob += pulp.lpSum(x.values()), "TotalAssigned"

    # 制約1: 1人1日1枠
    by_name_day = defaultdict(list)
    for (name, day, slot), var in x.items():
        by_name_day[(name, day)].append(var)
    for (name, day), vars_ in by_name_day.items():
        prob += pulp.lpSum(vars_) <= 1, f"OneShiftPerDay_{name}_{day}"

    # 制約2: 各枠の上限
    by_shift = defaultdict(list)
    for (name, day, slot), var in x.items():
        by_shift[(day, slot)].append(var)
    for (day, slot), vars_ in by_shift.items():
        prob += pulp.lpSum(vars_) <= shifts[(day, slot)], f"MaxRequired_{day}_{slot}"

    # 制約3: 固定割り当て
    for (name, day, slot) in fixed_assignments:
        if (name, day, slot) in x:
            prob += x[(name, day, slot)] == 1, f"Fixed_{name}_{day}_{slot}"

    # 制約4: min/max シフト数
    # by_name は目的関数の公平性計算で構築済み
    for name, c in staff_constraints.items():
        if name not in by_name:
            continue
        if c["min_shifts"] is not None:
            prob += pulp.lpSum(by_name[name]) >= c["min_shifts"], f"MinShifts_{name}"
        if c["max_shifts"] is not None:
            prob += pulp.lpSum(by_name[name]) <= c["max_shifts"], f"MaxShifts_{name}"

    # 制約5: 連続勤務上限
    for name, c in staff_constraints.items():
        max_consec = c.get("max_consecutive")
        if max_consec is None:
            continue
        window = max_consec + 1
        for start in range(len(DAY_ORDER) - max_consec):
            window_days = DAY_ORDER[start: start + window]
            vars_in_window = [
                x[(name, day, slot)]
                for day in window_days
                for slot in SLOT_ORDER
                if (name, day, slot) in x
            ]
            if vars_in_window:
                prob += (
                    pulp.lpSum(vars_in_window) <= max_consec,
                    f"MaxConsec_{name}_{DAY_ORDER[start]}_{DAY_ORDER[start + max_consec]}"
                )

    # 制約6: スキル制約
    # staff_skills と shift_skills が両方揃っている場合のみ有効
    #
    # 【なぜ y 変数が必要か】
    # x だけで「レジ持ち合計 >= 1」を課すと、レジ＆キッチン両方持ちの田中1人が
    # 割り当てられた時点でレジ制約もキッチン制約も同時に満たされてしまう。
    # y[name, day, slot, skill] = 1 で「誰がどのスキルを担当するか」を明示し、
    # 1人が1シフト枠で担当できるスキルは1つまでと制約することで、
    # 複数スキルを持つスタッフが1人で複数スキルをカバーできなくなる。
    if staff_skills and shift_skills:

        # y 変数: name が day/slot において skill 担当として割り当てられる
        y = {
            (name, day, slot, skill): pulp.LpVariable(
                f"y_{name}_{day}_{slot}_{skill}", cat="Binary"
            )
            for (name, day, slot) in x
            if (day, slot) in shift_skills
            for skill in staff_skills.get(name, set())
            if skill in shift_skills[(day, slot)]
        }

        # y=1 ならば x=1 でなければならない（未割り当てはスキル担当になれない）
        for (name, day, slot, skill), yvar in y.items():
            prob += yvar <= x[(name, day, slot)], f"YimpliesX_{name}_{day}_{slot}_{skill}"

        # 各スキルの必要人数を y の合計で満たす
        for (day, slot), skill_reqs in shift_skills.items():
            for skill, required in skill_reqs.items():
                yvars = [
                    y[(name, day, slot, skill)]
                    for name in staff_skills
                    if skill in staff_skills[name]
                    and (name, day, slot, skill) in y
                ]
                if yvars:
                    prob += (
                        pulp.lpSum(yvars) >= required,
                        f"Skill_{skill}_{day}_{slot}"
                    )

        # 1人が1シフト枠で担当できるスキルは1つまで
        for (name, day, slot) in x:
            yvars = [
                y[(name, day, slot, skill)]
                for skill in staff_skills.get(name, set())
                if (name, day, slot, skill) in y
            ]
            if yvars:
                prob += (
                    pulp.lpSum(yvars) <= 1,
                    f"OneSkillPerShift_{name}_{day}_{slot}"
                )

    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    status = pulp.LpStatus[prob.status]
    assigned          = defaultdict(list)
    assigned_by_staff = defaultdict(list)

    if status == "Optimal":
        for (name, day, slot), var in x.items():
            if pulp.value(var) == 1:
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

    # 公平性スコアの計算（表示用）
    shift_counts = [len(v) for v in assigned_by_staff.values()] if assigned_by_staff else [0]
    fairness_gap = max(shift_counts) - min(shift_counts) if len(shift_counts) >= 2 else 0

    return {
        "status":            status,
        "assigned":          dict(assigned),
        "assigned_by_staff": dict(assigned_by_staff),
        "fulfillment":       fulfillment,
        "total_required":    total_required,
        "total_actual":      total_actual,
        "fill_rate":         total_actual / total_required if total_required > 0 else 0.0,
        "fairness_gap":      fairness_gap,
    }


# -----------------------------------------------
# 結果表示（CLI用）
# -----------------------------------------------
def print_results(result: dict) -> None:
    print("\n" + "=" * 50)
    print(f"  求解ステータス : {result['status']}")
    print(f"  充足率         : {result['fill_rate']:.1%}  "
          f"({result['total_actual']} / {result['total_required']} 人)")
    print("=" * 50)

    print("\n【シフト枠別 割り当て結果】")
    for day in DAY_ORDER:
        for slot in SLOT_ORDER:
            if (day, slot) not in result["fulfillment"]:
                continue
            info     = result["fulfillment"][(day, slot)]
            names    = result["assigned"].get((day, slot), [])
            mark     = "✓" if info["satisfied"] else "✗"
            name_str = ", ".join(names) if names else "（未充足）"
            print(f"  {mark} {day} {slot}  {info['actual']}/{info['required']}名  → {name_str}")

    print("\n【スタッフ別 割り当てシフト】")
    for name, shifts_list in sorted(result["assigned_by_staff"].items()):
        shifts_str = "  ".join(f"{d}{s}" for d, s in sorted(shifts_list))
        print(f"  {name} : {shifts_str}")

    unsatisfied = [(d, s) for (d, s), info in result["fulfillment"].items() if not info["satisfied"]]
    if unsatisfied:
        print("\n【未充足のシフト枠】")
        for day, slot in unsatisfied:
            info = result["fulfillment"][(day, slot)]
            print(f"  ! {day} {slot}  {info['actual']}/{info['required']}名")
    else:
        print("\n  全シフト枠が充足されました。")
    print()


# -----------------------------------------------
# CLI エントリポイント
# -----------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="シフト最適化ツール")
    parser.add_argument("--availability",  default="availability.csv")
    parser.add_argument("--shifts",        default="shifts.csv")
    parser.add_argument("--constraints",   default=None)
    parser.add_argument("--fixed",         default=None)
    parser.add_argument("--staff-skills",  default=None)
    parser.add_argument("--shift-skills",  default=None)
    args = parser.parse_args()

    availability      = load_availability(args.availability)
    shifts            = load_shifts(args.shifts)
    staff_constraints = load_staff_constraints(args.constraints) if args.constraints else {}
    fixed_assignments = load_fixed_assignments(args.fixed)       if args.fixed       else set()
    staff_skills      = load_staff_skills(args.staff_skills)     if args.staff_skills else {}
    shift_skills      = load_shift_skills(args.shift_skills)     if args.shift_skills else {}

    warnings = validate_inputs(
        availability, shifts, staff_constraints, fixed_assignments,
        staff_skills, shift_skills
    )
    if warnings:
        print("\n【警告】")
        for w in warnings:
            print(f"  ! {w}")

    result = solve(availability, shifts, staff_constraints, fixed_assignments, staff_skills, shift_skills)

    if result["status"] != "Optimal":
        print(f"\n求解ステータス: {result['status']}")
        print("\n【原因分析】")
        reasons = analyze_infeasible(
            availability, shifts, staff_constraints, fixed_assignments,
            staff_skills, shift_skills
        )
        for r in reasons:
            print(f"  ! {r}")
        return

    print_results(result)


if __name__ == "__main__":
    main()