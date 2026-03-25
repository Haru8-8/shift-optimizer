"""
シフト最適化ツール（Streamlit UI）
使い方:
    pip install pulp streamlit
    streamlit run app.py
"""

import io
import streamlit as st
import pandas as pd

from optimizer import (
    load_availability,
    load_shifts,
    load_staff_constraints,
    load_fixed_assignments,
    load_staff_skills,
    load_shift_skills,
    validate_inputs,
    analyze_infeasible,
    solve,
)

st.set_page_config(page_title="シフト最適化ツール", page_icon="📅", layout="wide")
st.title("📅 シフト最適化ツール")
st.caption("CSVをアップロードして最適なシフトを自動生成します。")

# -----------------------------------------------
# サンプルCSV
# -----------------------------------------------
SAMPLE_AVAIL = """\
name,day,slot
田中,月,AM
田中,月,PM
田中,火,AM
田中,水,AM
鈴木,水,AM
鈴木,水,PM
鈴木,木,AM
鈴木,木,PM
鈴木,金,AM
佐藤,月,AM
佐藤,水,AM
佐藤,水,PM
佐藤,金,AM
佐藤,金,PM
高橋,火,AM
高橋,火,PM
高橋,木,PM
高橋,金,PM
高橋,土,AM
高橋,土,PM
伊藤,月,PM
伊藤,火,PM
伊藤,水,PM
伊藤,土,AM
伊藤,日,AM
伊藤,日,PM
"""

SAMPLE_SHIFTS = """\
day,slot,required
月,AM,2
月,PM,1
火,AM,1
火,PM,2
水,AM,2
水,PM,1
木,AM,1
木,PM,1
金,AM,1
金,PM,2
土,AM,1
土,PM,1
日,AM,1
日,PM,1
"""

SAMPLE_CONSTRAINTS = """\
name,min_shifts,max_shifts,max_consecutive
田中,2,4,3
鈴木,1,3,2
佐藤,,3,
高橋,2,,3
伊藤,1,4,
"""

SAMPLE_FIXED = """\
name,day,slot
田中,月,AM
伊藤,日,AM
"""

SAMPLE_STAFF_SKILLS = """\
name,skill
田中,レジ
田中,キッチン
鈴木,レジ
佐藤,キッチン
高橋,レジ
高橋,キッチン
伊藤,レジ
"""

SAMPLE_SHIFT_SKILLS = """\
day,slot,skill,required
月,AM,レジ,1
月,AM,キッチン,1
火,PM,レジ,1
水,AM,キッチン,1
"""

# -----------------------------------------------
# サイドバー
# -----------------------------------------------
st.sidebar.header("CSVファイルのアップロード")
st.sidebar.markdown("**必須**")
avail_file  = st.sidebar.file_uploader("availability.csv",            type="csv")
shifts_file = st.sidebar.file_uploader("shifts.csv",                  type="csv")
st.sidebar.markdown("**任意**")
constraints_file  = st.sidebar.file_uploader("staff_constraints.csv（省略可）",  type="csv")
fixed_file        = st.sidebar.file_uploader("fixed_assignments.csv（省略可）",  type="csv")
staff_skills_file = st.sidebar.file_uploader("staff_skills.csv（省略可）",       type="csv")
shift_skills_file = st.sidebar.file_uploader("shift_skills.csv（省略可）",       type="csv")

st.sidebar.divider()
st.sidebar.subheader("サンプルCSVのダウンロード")
for label, data, fname in [
    ("availability.csv",      SAMPLE_AVAIL,         "availability.csv"),
    ("shifts.csv",            SAMPLE_SHIFTS,        "shifts.csv"),
    ("staff_constraints.csv", SAMPLE_CONSTRAINTS,   "staff_constraints.csv"),
    ("fixed_assignments.csv", SAMPLE_FIXED,         "fixed_assignments.csv"),
    ("staff_skills.csv",      SAMPLE_STAFF_SKILLS,  "staff_skills.csv"),
    ("shift_skills.csv",      SAMPLE_SHIFT_SKILLS,  "shift_skills.csv"),
]:
    st.sidebar.download_button(
        label=f"{label} をダウンロード",
        data=data.encode("utf-8-sig"),
        file_name=fname,
        mime="text/csv",
    )

# -----------------------------------------------
# アップロード前のガイド
# -----------------------------------------------
if avail_file is None or shifts_file is None:
    st.info("サイドバーから availability.csv と shifts.csv をアップロードしてください。")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("availability.csv")
        st.dataframe(pd.read_csv(io.StringIO(SAMPLE_AVAIL)).head(6), use_container_width=True)
    with col2:
        st.subheader("shifts.csv")
        st.dataframe(pd.read_csv(io.StringIO(SAMPLE_SHIFTS)), use_container_width=True)
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("staff_skills.csv（省略可）")
        st.dataframe(pd.read_csv(io.StringIO(SAMPLE_STAFF_SKILLS)), use_container_width=True)
    with col4:
        st.subheader("shift_skills.csv（省略可）")
        st.dataframe(pd.read_csv(io.StringIO(SAMPLE_SHIFT_SKILLS)), use_container_width=True)
        st.caption("両方アップロードした場合のみスキル制約が有効になります。")
    st.stop()

# -----------------------------------------------
# CSV 読み込み
# -----------------------------------------------
try:
    avail_text  = avail_file.read().decode("utf-8")
    shifts_text = shifts_file.read().decode("utf-8")

    availability      = load_availability(io.StringIO(avail_text))
    shifts            = load_shifts(io.StringIO(shifts_text))
    staff_constraints = {}
    fixed_assignments = set()
    staff_skills      = {}
    shift_skills      = {}

    if constraints_file:
        staff_constraints = load_staff_constraints(
            io.StringIO(constraints_file.read().decode("utf-8"))
        )
    if fixed_file:
        fixed_assignments = load_fixed_assignments(
            io.StringIO(fixed_file.read().decode("utf-8"))
        )
    if staff_skills_file:
        staff_skills = load_staff_skills(
            io.StringIO(staff_skills_file.read().decode("utf-8"))
        )
    if shift_skills_file:
        shift_skills = load_shift_skills(
            io.StringIO(shift_skills_file.read().decode("utf-8"))
        )

except ValueError as e:
    st.error(f"CSVの読み込みエラー: {e}")
    st.stop()
except Exception as e:
    st.error(f"予期しないエラーが発生しました: {e}")
    st.stop()

# -----------------------------------------------
# 警告の表示
# -----------------------------------------------
warnings = validate_inputs(
    availability, shifts, staff_constraints, fixed_assignments,
    staff_skills, shift_skills
)
if warnings:
    with st.expander(f"⚠️ 警告 {len(warnings)} 件（クリックして確認）", expanded=True):
        for w in warnings:
            st.warning(w)

# -----------------------------------------------
# プレビュー
# -----------------------------------------------
with st.expander("📂 読み込んだCSVの確認", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        st.caption("availability.csv")
        st.dataframe(pd.read_csv(io.StringIO(avail_text)), use_container_width=True, height=200)
    with col2:
        st.caption("shifts.csv")
        st.dataframe(pd.read_csv(io.StringIO(shifts_text)), use_container_width=True, height=200)

# -----------------------------------------------
# 実行ボタン
# -----------------------------------------------
staff_count = len({name for name, _, _ in availability})
shift_count = len(shifts)
col1, col2, col3, col4 = st.columns(4)
col1.metric("スタッフ数",   f"{staff_count} 名")
col2.metric("シフト枠数",   f"{shift_count} 枠")
col3.metric("固定割り当て", f"{len(fixed_assignments)} 件")
col4.metric("スキル制約",   "有効" if staff_skills and shift_skills else "無効")

# 公平性スライダー
fairness_weight = st.slider(
    "公平性の重み（0=充足率優先 / 大きいほど均等割り当て優先）",
    min_value=0.0, max_value=5.0, value=0.0, step=0.5,
    help="ソフト制約のため、入れる人がいない場合は集中が起こることがあります。"
)

if st.button("🚀 最適化を実行", type="primary"):
    with st.spinner("最適化中..."):
        st.session_state["result"] = solve(
            availability, shifts, staff_constraints, fixed_assignments,
            staff_skills, shift_skills,
            fairness_weight=fairness_weight,
        )
        # infeasible 分析も一緒に保存
        if st.session_state["result"]["status"] != "Optimal":
            st.session_state["infeasible_reasons"] = analyze_infeasible(
                availability, shifts, staff_constraints, fixed_assignments,
                staff_skills, shift_skills
            )
        else:
            st.session_state.pop("infeasible_reasons", None)

if "result" not in st.session_state:
    st.stop()

result = st.session_state["result"]

# -----------------------------------------------
# 求解不能の場合
# -----------------------------------------------
if result["status"] != "Optimal":
    st.error(f"求解ステータス: **{result['status']}**　制約が厳しすぎて解が見つかりませんでした。")
    reasons = st.session_state.get("infeasible_reasons", [])
    if reasons:
        st.subheader("原因分析")
        for r in reasons:
            st.warning(r)
    st.stop()

# -----------------------------------------------
# サマリー
# -----------------------------------------------
st.divider()
st.subheader("結果サマリー")

col1, col2, col3, col4 = st.columns(4)
col1.metric("求解ステータス", result["status"])
col2.metric(
    "充足率",
    f"{result['fill_rate']:.1%}",
    f"{result['total_actual']} / {result['total_required']} 人",
)
unsatisfied_count = sum(1 for v in result["fulfillment"].values() if not v["satisfied"])
col3.metric("未充足の枠数", f"{unsatisfied_count} 枠")
col4.metric("シフト数の最大-最小", f"{result.get('fairness_gap', '—')} 枠",
            help="0に近いほど均等な割り当て")

# -----------------------------------------------
# シフト割り当て表
# -----------------------------------------------
st.subheader("シフト割り当て表")

DAY_ORDER  = ["月", "火", "水", "木", "金", "土", "日"]
SLOT_ORDER = ["AM", "PM"]

rows = []
for day in DAY_ORDER:
    for slot in SLOT_ORDER:
        if (day, slot) not in result["fulfillment"]:
            continue
        info  = result["fulfillment"][(day, slot)]
        names = result["assigned"].get((day, slot), [])

        # スキル充足状況を担当者欄に付記
        skill_note = ""
        if staff_skills and shift_skills and (day, slot) in shift_skills:
            for skill, req in shift_skills[(day, slot)].items():
                actual_skilled = sum(
                    1 for n in names if skill in staff_skills.get(n, set())
                )
                skill_note += f" [{skill}: {actual_skilled}/{req}]"

        rows.append({
            "曜日":   day,
            "時間帯": slot,
            "必要人数": info["required"],
            "配置人数": info["actual"],
            "充足":   "✓" if info["satisfied"] else "✗",
            "担当者": (", ".join(names) if names else "—") + skill_note,
        })

df_result = pd.DataFrame(rows)

def highlight_row(row):
    if row["充足"] == "✗":
        return ["background-color: #fff3cd"] * len(row)
    return [""] * len(row)

ROW_HEIGHT    = 35
HEADER_HEIGHT = 38
PADDING       = 10

st.dataframe(
    df_result.style.apply(highlight_row, axis=1),
    use_container_width=True,
    hide_index=True,
    height=HEADER_HEIGHT + ROW_HEIGHT * len(df_result) + PADDING,
)

# -----------------------------------------------
# スタッフ別シフト一覧
# -----------------------------------------------
st.subheader("スタッフ別シフト一覧")

staff_rows = []
for name, shifts_list in sorted(result["assigned_by_staff"].items()):
    shifts_str = "　".join(f"{d}{s}" for d, s in sorted(shifts_list))
    c = staff_constraints.get(name, {})
    skills_str = ", ".join(sorted(staff_skills.get(name, set()))) if staff_skills else "—"
    staff_rows.append({
        "スタッフ名":     name,
        "割り当てシフト": shifts_str,
        "シフト数":       len(shifts_list),
        "最低":           c.get("min_shifts") or "—",
        "最大":           c.get("max_shifts") or "—",
        "連続上限":       c.get("max_consecutive") or "—",
        "スキル":         skills_str,
    })

df_staff = pd.DataFrame(staff_rows).fillna("—")
st.dataframe(
    df_staff,
    use_container_width=True,
    hide_index=True,
    height=HEADER_HEIGHT + ROW_HEIGHT * len(df_staff) + PADDING,
)

# -----------------------------------------------
# ダウンロード
# -----------------------------------------------
st.divider()
st.subheader("結果のダウンロード")

result_csv = df_result.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="📥 割り当て結果をCSVでダウンロード",
    data=result_csv,
    file_name="shift_result.csv",
    mime="text/csv",
)