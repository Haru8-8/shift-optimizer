"""
アルゴリズム比較ページ（PuLP 厳密解 vs 遺伝的アルゴリズム）
"""

import io
import time
import streamlit as st
import pandas as pd

from optimizer import (
    load_availability,
    load_shifts,
    load_staff_constraints,
    load_fixed_assignments,
    load_staff_skills,
    load_shift_skills,
    solve,
)
from ga_optimizer import solve_ga

st.set_page_config(page_title="アルゴリズム比較", page_icon="📊", layout="wide")
st.title("📊 アルゴリズム比較：PuLP vs 遺伝的アルゴリズム")
st.caption("同じ問題を2つのアルゴリズムで解いて、解の質・求解時間を比較します。")

# -----------------------------------------------
# サンプルCSV（メインページと共通）
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

# -----------------------------------------------
# サイドバー：CSVアップロード
# -----------------------------------------------
st.sidebar.header("CSVファイルのアップロード")
st.sidebar.markdown("**必須**")
avail_file  = st.sidebar.file_uploader("availability.csv",           type="csv", key="cmp_avail")
shifts_file = st.sidebar.file_uploader("shifts.csv",                 type="csv", key="cmp_shifts")
st.sidebar.markdown("**任意**")
constraints_file  = st.sidebar.file_uploader("staff_constraints.csv（省略可）", type="csv", key="cmp_con")
fixed_file        = st.sidebar.file_uploader("fixed_assignments.csv（省略可）", type="csv", key="cmp_fix")
staff_skills_file = st.sidebar.file_uploader("staff_skills.csv（省略可）",      type="csv", key="cmp_ss")
shift_skills_file = st.sidebar.file_uploader("shift_skills.csv（省略可）",      type="csv", key="cmp_sk")

# -----------------------------------------------
# GAパラメータ設定
# -----------------------------------------------
st.sidebar.divider()
st.sidebar.subheader("GA パラメータ")
pop_size     = st.sidebar.slider("個体数",   min_value=20,  max_value=300, value=100, step=10)
n_generations = st.sidebar.slider("世代数",  min_value=50,  max_value=500, value=300, step=50)
mutation_rate = st.sidebar.slider("突然変異率", min_value=0.01, max_value=0.2, value=0.02, step=0.01)

# 公平性スライダー
fairness_weight = st.sidebar.slider(
    "公平性の重み",
    min_value=0.0, max_value=5.0, value=0.0, step=0.5,
    help="0=充足率優先 / 大きいほど均等割り当て優先",
    key="cmp_fairness"
)

if avail_file is None or shifts_file is None:
    st.info("サイドバーから availability.csv と shifts.csv をアップロードしてください。")
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
        staff_constraints = load_staff_constraints(io.StringIO(constraints_file.read().decode("utf-8")))
    if fixed_file:
        fixed_assignments = load_fixed_assignments(io.StringIO(fixed_file.read().decode("utf-8")))
    if staff_skills_file:
        staff_skills = load_staff_skills(io.StringIO(staff_skills_file.read().decode("utf-8")))
    if shift_skills_file:
        shift_skills = load_shift_skills(io.StringIO(shift_skills_file.read().decode("utf-8")))

except ValueError as e:
    st.error(f"CSVの読み込みエラー: {e}")
    st.stop()

staff_count = len({name for name, _, _ in availability})
shift_count = len(shifts)
st.write(f"スタッフ数: **{staff_count}名**　シフト枠数: **{shift_count}枠**")

# -----------------------------------------------
# 実行ボタン
# -----------------------------------------------
if st.button("⚡ 両アルゴリズムで比較実行", type="primary"):
    col1, col2 = st.columns(2)

    # PuLP
    with col1:
        with st.spinner("PuLP（厳密解）で求解中..."):
            t0 = time.time()
            result_pulp = solve(
                availability, shifts, staff_constraints,
                fixed_assignments, staff_skills, shift_skills,
                fairness_weight=fairness_weight,
            )
            result_pulp["elapsed"] = time.time() - t0

    # GA
    with col2:
        with st.spinner(f"GA（{n_generations}世代）で求解中..."):
            result_ga = solve_ga(
                availability, shifts, staff_constraints,
                fixed_assignments, staff_skills, shift_skills,
                pop_size=pop_size,
                n_generations=n_generations,
                mutation_rate=mutation_rate,
                fairness_weight=fairness_weight,
            )

    st.session_state["cmp_pulp"] = result_pulp
    st.session_state["cmp_ga"]   = result_ga

if "cmp_pulp" not in st.session_state:
    st.stop()

result_pulp = st.session_state["cmp_pulp"]
result_ga   = st.session_state["cmp_ga"]

# -----------------------------------------------
# サマリー比較カード
# -----------------------------------------------
st.divider()
st.subheader("結果サマリー")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### PuLP（厳密解）")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("充足率",         f"{result_pulp['fill_rate']:.1%}")
    m2.metric("求解時間",       f"{result_pulp['elapsed']:.2f} s")
    unsatisfied_pulp = sum(1 for v in result_pulp["fulfillment"].values() if not v["satisfied"])
    m3.metric("未充足枠",       f"{unsatisfied_pulp} 枠")
    m4.metric("シフト数 max-min", f"{result_pulp.get('fairness_gap', '—')}")

with col2:
    st.markdown("#### GA（近似解）")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "充足率",
        f"{result_ga['fill_rate']:.1%}",
        f"{result_ga['fill_rate'] - result_pulp['fill_rate']:+.1%} vs PuLP",
    )
    m2.metric("求解時間",       f"{result_ga['elapsed']:.2f} s")
    unsatisfied_ga = sum(1 for v in result_ga["fulfillment"].values() if not v["satisfied"])
    m3.metric("未充足枠",       f"{unsatisfied_ga} 枠")
    m4.metric("シフト数 max-min", f"{result_ga.get('fairness_gap', '—')}")

# -----------------------------------------------
# 収束曲線
# -----------------------------------------------
st.subheader("GA 収束曲線")
st.caption("世代が進むにつれてスコアがどのように改善されるかを示します。")

if result_ga["history"]:
    df_history = pd.DataFrame({
        "世代":       range(1, len(result_ga["history"]) + 1),
        "ベストスコア": result_ga["history"],
    })
    st.line_chart(df_history.set_index("世代"))

# -----------------------------------------------
# シフト割り当て表の比較
# -----------------------------------------------
st.subheader("シフト割り当て表の比較")

DAY_ORDER  = ["月", "火", "水", "木", "金", "土", "日"]
SLOT_ORDER = ["AM", "PM"]

def build_result_df(result: dict) -> pd.DataFrame:
    rows = []
    for day in DAY_ORDER:
        for slot in SLOT_ORDER:
            if (day, slot) not in result["fulfillment"]:
                continue
            info  = result["fulfillment"][(day, slot)]
            names = result["assigned"].get((day, slot), [])
            rows.append({
                "曜日":   day,
                "時間帯": slot,
                "配置/必要": f"{info['actual']}/{info['required']}",
                "充足":   "✓" if info["satisfied"] else "✗",
                "担当者": ", ".join(names) if names else "—",
            })
    return pd.DataFrame(rows)

def highlight_row(row):
    if row["充足"] == "✗":
        return ["background-color: #fff3cd"] * len(row)
    return [""] * len(row)

ROW_HEIGHT    = 35
HEADER_HEIGHT = 38
PADDING       = 10

col1, col2 = st.columns(2)

with col1:
    st.markdown("**PuLP（厳密解）**")
    df_pulp = build_result_df(result_pulp)
    st.dataframe(
        df_pulp.style.apply(highlight_row, axis=1),
        use_container_width=True,
        hide_index=True,
        height=HEADER_HEIGHT + ROW_HEIGHT * len(df_pulp) + PADDING,
    )

with col2:
    st.markdown("**GA（近似解）**")
    df_ga = build_result_df(result_ga)
    st.dataframe(
        df_ga.style.apply(highlight_row, axis=1),
        use_container_width=True,
        hide_index=True,
        height=HEADER_HEIGHT + ROW_HEIGHT * len(df_ga) + PADDING,
    )

# -----------------------------------------------
# 考察テキスト
# -----------------------------------------------
st.divider()
st.subheader("アルゴリズムの特性比較")

st.markdown("""
| 観点 | PuLP（厳密解） | GA（近似解） |
|---|---|---|
| 解の保証 | 最適解が保証される | 保証なし（良好な近似解） |
| 求解時間 | 問題規模に対して指数的に増加 | パラメータ次第で制御可能 |
| 小規模問題 | 高速・最適 | PuLP より遅くなりやすい |
| 大規模問題 | 時間がかかりすぎる場合がある | 現実的な時間で解が得られる |
| 制約の扱い | 制約を厳密に満たす | ペナルティで軟制約として扱う |
| パラメータ調整 | 不要 | 個体数・世代数・突然変異率の調整が必要 |

**使い分けの目安**
- スタッフ数十名・シフト枠数十程度 → PuLP の厳密解が現実的
- スタッフ数百名・複雑な制約 → GA などの近似解法を検討
""")