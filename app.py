import os
import sys
import shutil
import tempfile
import sqlite3
import uuid
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# DATABASE & BACKEND INTEGRATION
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "database"))

BUNDLED_DB = os.path.join(BASE_DIR, "database", "railway_planning.db")
if not os.path.exists(BUNDLED_DB):
    alt_path = os.path.join(BASE_DIR, "railway_planning.db")
    if os.path.exists(alt_path):
        BUNDLED_DB = alt_path

# Streamlit Community Cloud mounts apps at /mount/src/... where SQLite locking
# and rollback journals frequently fail with disk I/O errors.
# If on /mount/src or directory is not writable, we run the database from /tmp.
is_cloud = "/mount/src" in BASE_DIR or os.environ.get("STREAMLIT_SERVER_ENVIRONMENT") == "cloud"
can_write_repo = False
try:
    test_file = os.path.join(os.path.dirname(BUNDLED_DB) if os.path.exists(BUNDLED_DB) else BASE_DIR, ".write_test")
    with open(test_file, "w") as f:
        f.write("ok")
    os.remove(test_file)
    can_write_repo = True
except Exception:
    can_write_repo = False

if is_cloud or not can_write_repo:
    DB_DIR = os.path.join(tempfile.gettempdir(), "railway_ai_data")
    os.makedirs(DB_DIR, exist_ok=True)
    DB_PATH = os.path.join(DB_DIR, "railway_planning.db")
    if os.path.exists(BUNDLED_DB):
        if not os.path.exists(DB_PATH) or (os.path.getsize(DB_PATH) < 50000 and os.path.getsize(BUNDLED_DB) > 50000):
            try:
                shutil.copy2(BUNDLED_DB, DB_PATH)
            except Exception:
                pass
else:
    DB_PATH = BUNDLED_DB

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    try:
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    try:
        conn.execute("PRAGMA journal_mode=DELETE;")
    except Exception:
        pass
    return conn

# Import AI Engine & Data Generation
from ai_scorer import run_scoring_engine
from ai_scheduler import run_scheduler
from generatedata import generate_large_dataset

def run_scheduler_pipeline(horizon="All"):
    """Runs the AI Prioritization and Coordinated Shadow Block Optimizer."""
    return run_scheduler(db_path=DB_PATH, horizon=horizon)

def reset_database():
    """Regenerates the complete authentic Indian Railways dataset and schedules blocks."""
    generate_large_dataset(db_path=DB_PATH)
    run_scoring_engine(db_path=DB_PATH, score_all=True)
    run_scheduler(db_path=DB_PATH, horizon="All")

def ensure_database_ready():
    """Auto-initializes database if running fresh on Streamlit Cloud or container mounts."""
    needed_tables = ["Tracks", "Trains", "Jobs", "Corridor_Availability", "Block_Register", "Block_Jobs"]
    must_reset = False
    try:
        if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) < 10000:
            must_reset = True
        else:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = set(r[0] for r in cur.fetchall())
            for tbl in needed_tables:
                if tbl not in existing_tables:
                    must_reset = True
                    break
            if not must_reset:
                cur.execute("SELECT count(*) FROM Jobs")
                cnt = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM Block_Register")
                b_cnt = cur.fetchone()[0]
                if cnt == 0 or b_cnt == 0:
                    must_reset = True
            conn.close()
    except Exception:
        must_reset = True

    if must_reset:
        try:
            reset_database()
        except Exception as e:
            print(f"Error during auto-initialization: {e}")

ensure_database_ready()

def safe_read_sql(sql, conn, params=None, default_cols=None):
    """Executes SQL query and returns a DataFrame, returning fallback empty DataFrame on error."""
    try:
        if params is not None:
            return pd.read_sql_query(sql, conn, params=params)
        return pd.read_sql_query(sql, conn)
    except Exception as e:
        print(f"safe_read_sql fallback for query: {e}")
        if default_cols:
            return pd.DataFrame(columns=default_cols)
        return pd.DataFrame()


# ============================================================
# THEME REGISTRY
# One source of truth for every color used in CSS *and* in the
# Plotly charts, so the two can never drift apart again.
# ============================================================

THEMES = {
    "Light": {
        "color_scheme": "light",
        "bg": "#f1ecdf", "panel": "#fbf8ef", "panel2": "#f5f0e4",
        "line": "#cfc4ad", "line2": "#ded5c3", "soft": "#e7dfcf",
        "text": "#2d2b27", "muted": "#746d61",
        "input": "#fffdf7", "input_text": "#2d2b27",
        "blue": "#2e5d73", "navy": "#213d4a", "purple": "#684b6f",
        "red": "#7b302b", "brass": "#a67c3c", "green": "#315b4a",
        "amber": "#b38a4e",
        "sidebar": "#29483d", "sidebar2": "#365b4e", "sidebar_text": "#f6f0e3",
        "shadow": "0 1px 2px rgba(64,52,35,.10)",
        "chart_paper": "#fbf8ef", "chart_plot": "#fbf8ef",
        "chart_font": "#2d2b27", "chart_grid": "#ddd4c4",
        "texture_opacity": ".08",
        "status_colors": {"Scheduled": "#557d69", "Pending": "#b38a4e", "Delayed": "#a84f47"},
        "severity_colors": {"Low": "#6b806c", "Medium": "#a67c3c", "High": "#9b5b3f", "Critical": "#7b302b"},
        "dept_scale": [[0, "#c9b58c"], [0.55, "#8d6f42"], [1, "#5b4330"]],
    },
    "Dark": {
        "color_scheme": "dark",
        "bg": "#151816", "panel": "#202521", "panel2": "#292e2a",
        "line": "#485049", "line2": "#383f39", "soft": "#303631",
        "text": "#eee9dc", "muted": "#b8b1a3",
        "input": "#1b211d", "input_text": "#eee9dc",
        "blue": "#88aebc", "navy": "#a9bec6", "purple": "#ad91b3",
        "red": "#c56a60", "brass": "#c9a15f", "green": "#8fbaa0",
        "amber": "#d3ab6e",
        "sidebar": "#1e3930", "sidebar2": "#2c5144", "sidebar_text": "#f3eee2",
        "shadow": "0 1px 4px rgba(0,0,0,.32)",
        "chart_paper": "#202521", "chart_plot": "#202521",
        "chart_font": "#eee9dc", "chart_grid": "#414840",
        "texture_opacity": ".025",
        "status_colors": {"Scheduled": "#7fb497", "Pending": "#d3ab6e", "Delayed": "#c56a60"},
        "severity_colors": {"Low": "#8fbaa0", "Medium": "#c9a15f", "High": "#c98866", "Critical": "#c56a60"},
        "dept_scale": [[0, "#5b4330"], [0.55, "#8d6f42"], [1, "#c9b58c"]],
    },
}


def css_vars_block(theme):
    """Turn a theme dict into a `--name:value;` string for :root."""
    keys = [
        "bg", "panel", "panel2", "line", "line2", "text", "muted", "soft",
        "input", "input_text", "blue", "navy", "purple", "red", "brass",
        "green", "amber", "chart_grid", "chart_paper", "sidebar", "sidebar2",
        "sidebar_text", "shadow",
    ]
    return "".join(f"--{k.replace('_', '-')}:{theme[k]};" for k in keys)


# ============================================================
# PAGE CONFIG
# ============================================================
if "dashboard_theme" not in st.session_state:
    st.session_state.dashboard_theme = "System"

st.set_page_config(
    page_title="AI Rail Corridor Scheduler",
    layout="wide",
    initial_sidebar_state="expanded",
)

theme_name = st.session_state.dashboard_theme

resolved_theme = THEMES["Dark"] if theme_name == "Dark" else THEMES["Light"]

root_css = f":root{{{css_vars_block(resolved_theme)}color-scheme:{resolved_theme['color_scheme']};}}"

if theme_name == "System":
    dark = THEMES["Dark"]
    root_css += (
        "@media (prefers-color-scheme: dark){:root{"
        + css_vars_block(dark)
        + "color-scheme:dark;}}"
    )

st.markdown(f"<style>{root_css}</style>", unsafe_allow_html=True)


# ============================================================
# VINTAGE UI
# ============================================================
st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&family=Source+Sans+3:wght@400;500;600;700&display=swap');
html, body, [class*="css"] {{ font-family:'Source Sans 3',Arial,sans-serif; }}
.stApp {{ background:var(--bg); color:var(--text); }}
.main .block-container {{ max-width:1500px; padding:1rem 1.45rem 2.2rem; }}
.main .block-container::before {{ content:""; position:fixed; inset:0; pointer-events:none; opacity:{resolved_theme['texture_opacity']}; background-image:radial-gradient(rgba(90,70,40,.20) .45px, transparent .45px); background-size:6px 6px; z-index:0; }}
.topbar {{ min-height:66px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; background:var(--panel); border:1px solid var(--line); border-left:5px solid var(--brass); margin:-.2rem 0 16px; padding:10px 18px; box-shadow:var(--shadow); position:relative; z-index:1; }}
.brand {{ display:flex; align-items:center; gap:12px; }}
.brand-logo {{ width:43px;height:36px;background:#fdfbf4;border:1px solid #bdb19a;border-radius:1px;display:flex;align-items:center;justify-content:center;overflow:hidden;flex-shrink:0; }}
.brand-logo img {{ width:100%;height:100%;object-fit:contain;filter:sepia(.25) saturate(.65) contrast(.95); }}
.brand-title {{ font-family:'Libre Baskerville',Georgia,serif; font-size:17px;font-weight:700;color:var(--text); }}
.brand-sub {{ font-size:9px;color:var(--muted);margin-top:2px;text-transform:uppercase;letter-spacing:1px; }}
.topbar-right {{ display:flex; align-items:center; gap:8px; }}
.system-state {{ font-size:10px;color:var(--green);border:1px solid var(--green);background:var(--panel2);padding:5px 9px;border-radius:1px;letter-spacing:.5px;font-weight:600;white-space:nowrap; }}
.system-state::before {{ content:"[ONLINE] "; margin-right:3px; }}
.clock-chip {{ font-size:10px;color:var(--muted);border:1px solid var(--line);background:var(--panel2);padding:5px 9px;border-radius:1px;white-space:nowrap; }}
div[data-testid="stMetric"] {{ min-height:82px;padding:12px 15px;background:var(--panel);border:1px solid var(--line);border-radius:1px;box-shadow:var(--shadow);border-top:3px solid var(--brass); }}
div[data-testid="stMetric"]:hover {{ border-color:var(--brass); }}
div[data-testid="stMetricLabel"] {{ color:var(--muted)!important;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.6px; }}
div[data-testid="stMetricValue"] {{ color:var(--text)!important;font-family:'Libre Baskerville',Georgia,serif;font-size:24px;font-weight:700; }}
.section-head {{ margin:14px 0 7px;padding:10px 12px;background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--red);border-radius:1px;font-family:'Libre Baskerville',Georgia,serif;font-size:12px;font-weight:700;color:var(--text);box-shadow:var(--shadow); }}
.info-box {{ margin:8px 0;padding:9px 11px;background:var(--panel2);border:1px solid var(--brass);border-left:4px solid var(--brass);border-radius:1px;font-size:11px;color:var(--muted); }}
section[data-testid="stSidebar"] {{ background:var(--sidebar); border-right:5px solid var(--brass); }}
section[data-testid="stSidebar"] .block-container {{ padding:.85rem .75rem 1.5rem; }}
section[data-testid="stSidebar"] * {{ color:var(--sidebar-text); }}
section[data-testid="stSidebar"] h2 {{ font-family:'Libre Baskerville',Georgia,serif;font-size:17px;margin:4px 0 8px;font-weight:700; }}
section[data-testid="stSidebar"] h3 {{ font-family:'Libre Baskerville',Georgia,serif;font-size:12px;margin-top:14px;color:var(--sidebar-text); }}
section[data-testid="stSidebar"] hr {{ border-color:rgba(236,224,197,.25)!important; }}
section[data-testid="stSidebar"] .stButton > button {{ background:var(--sidebar2);color:var(--sidebar-text);border:1px solid rgba(236,224,197,.35);border-radius:1px;box-shadow:none;font-weight:600; }}
section[data-testid="stSidebar"] .stButton > button:hover {{ background:var(--brass);border-color:var(--brass);color:#211a0f; }}
section[data-testid="stSidebar"] input,section[data-testid="stSidebar"] textarea,section[data-testid="stSidebar"] [data-baseweb="select"] > div {{ background:rgba(0,0,0,.18)!important;border-color:rgba(236,224,197,.35)!important;color:var(--sidebar-text)!important;border-radius:1px!important; }}
section[data-testid="stSidebar"] label {{ color:var(--sidebar-text)!important;font-size:10px!important; }}
section[data-testid="stSidebar"] [data-baseweb="radio"] label {{ font-size:12px!important; }}
.stButton > button {{ border-radius:1px;border:1px solid var(--line);background:var(--panel);color:var(--text);box-shadow:var(--shadow);font-weight:600; }}
.stButton > button:hover {{ background:var(--panel2);border-color:var(--brass); }}
.stTextInput input,
.stNumberInput input,
.stDateInput input,
.stTextArea textarea,
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea {{
    background-color:var(--input)!important;
    background:var(--input)!important;
    border-color:var(--line)!important;
    color:var(--input-text)!important;
    -webkit-text-fill-color:var(--input-text)!important;
    caret-color:var(--input-text)!important;
    border-radius:1px!important;
}}
.stTextInput [data-baseweb="input"],
.stNumberInput [data-baseweb="input"],
.stDateInput [data-baseweb="input"],
.stTextArea [data-baseweb="textarea"],
section[data-testid="stSidebar"] [data-baseweb="input"],
section[data-testid="stSidebar"] [data-baseweb="textarea"] {{
    background:var(--input)!important;
    border-color:var(--line)!important;
    color:var(--input-text)!important;
}}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {{
    color:var(--muted)!important;
    -webkit-text-fill-color:var(--muted)!important;
}}
section[data-testid="stSidebar"] [data-baseweb="input"] > div,
section[data-testid="stSidebar"] [data-baseweb="textarea"] > div {{
    background:var(--input)!important;
    border-color:var(--line)!important;
}}
section[data-testid="stSidebar"] input:disabled,
section[data-testid="stSidebar"] textarea:disabled {{
    background:var(--input)!important;
    color:var(--muted)!important;
    -webkit-text-fill-color:var(--muted)!important;
    opacity:1!important;
}}
.stRadio label {{ font-size:12px!important;color:var(--text)!important; }}
.stTabs [data-baseweb="tab-list"] {{ gap:0;background:var(--panel);border:1px solid var(--line);border-radius:1px;padding:0;flex-wrap:wrap; }}
.stTabs [data-baseweb="tab"] {{ height:40px;padding:0 18px;color:var(--muted);font-size:12px;border-radius:0;border-right:1px solid var(--line2); }}
.stTabs [data-baseweb="tab"]:hover {{ background:var(--panel2);color:var(--red); }}
.stTabs [aria-selected="true"] {{ color:var(--red)!important;background:var(--panel2)!important;border-bottom:3px solid var(--red)!important;font-weight:600; }}
div[data-testid="stDataFrame"] {{ border:1px solid var(--line);border-radius:1px;overflow:hidden;background:var(--panel);box-shadow:var(--shadow); }}
div[data-testid="stPlotlyChart"] {{ border:1px solid var(--line);border-radius:1px;background:var(--panel);padding:1px;box-shadow:var(--shadow); }}
hr {{ border-color:var(--line)!important; }}
::-webkit-scrollbar {{ width:8px;height:8px; }}
::-webkit-scrollbar-track {{ background:var(--soft); }}
::-webkit-scrollbar-thumb {{ background:var(--muted);border-radius:1px; }}
[data-baseweb="popover"],[data-baseweb="menu"],[role="listbox"] {{ background:var(--panel)!important;color:var(--text)!important;border-color:var(--line)!important; }}
[data-baseweb="menu"] *,[role="option"] {{ color:var(--text)!important; }}
[data-baseweb="menu"] [aria-selected="true"],[role="option"]:hover {{ background:var(--panel2)!important; }}
section[data-testid="stSidebar"] [data-testid="stForm"] input,
section[data-testid="stSidebar"] [data-testid="stForm"] textarea {{
    background-color:var(--input)!important;
    background-image:none!important;
    box-shadow:none!important;
}}
header[data-testid="stHeader"] {{ background:var(--panel)!important; background-color:var(--panel)!important; border-bottom:1px solid var(--line)!important; opacity:1!important; }}
header[data-testid="stHeader"] * {{ color:var(--text)!important; }}
button[data-testid="stBaseButton-header"] {{ color:var(--text)!important; }}
.stRadio > div {{ color:var(--text)!important; }}
.stRadio [data-baseweb="radio"] > div:first-child {{ border-color:var(--muted)!important; background:var(--panel)!important; }}
.vintage-table-wrap {{ width:100%; overflow-x:auto; border:1px solid var(--line); border-radius:1px; background:var(--panel); box-shadow:var(--shadow); }}
.vintage-table {{ width:100%; min-width:520px; border-collapse:collapse; font-family:'Source Sans 3',Arial,sans-serif; font-size:12px; color:var(--text); }}
.vintage-table th {{ background:var(--panel2); color:var(--muted); text-align:left; padding:9px 10px; border-right:1px solid var(--line2); border-bottom:1px solid var(--line); font-weight:600; white-space:nowrap; position:sticky; top:0; }}
.vintage-table td {{ background:var(--panel); color:var(--text); padding:9px 10px; border-right:1px solid var(--line2); border-bottom:1px solid var(--line2); white-space:nowrap; }}
.vintage-table tbody tr:nth-child(even) td {{ background:var(--panel2); }}
.vintage-table tbody tr:hover td {{ background:var(--soft); }}
.vintage-table th:last-child,.vintage-table td:last-child {{ border-right:0; }}
.vintage-table tbody tr:last-child td {{ border-bottom:0; }}
.score-wrap {{ display:flex; align-items:center; gap:8px; min-width:120px; }}
.score-bar {{ height:7px; flex:1; background:var(--soft); border:1px solid var(--line); border-radius:4px; overflow:hidden; }}
.score-fill {{ height:100%; border-radius:4px; }}
.score-value {{ min-width:22px; text-align:right; color:var(--text); font-weight:600; }}
.status-pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:10.5px; font-weight:700; letter-spacing:.3px; border:1px solid transparent; }}
@media (max-width: 700px) {{
    .main .block-container {{ padding:0.75rem 0.6rem 1.5rem; }}
    .topbar {{ flex-direction:column; align-items:flex-start; }}
    .stTabs [data-baseweb="tab"] {{ height:36px; padding:0 12px; font-size:11px; }}
}}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================
st.markdown(
    f"""
<div class="topbar">
<div class="brand">
<div class="brand-logo"><img src="https://png.pngtree.com/png-vector/20230109/ourmid/pngtree-train-on-a-white-background-png-image_6556767.png" alt="Train"></div>
<div>
<div class="brand-title">Railway Corridor Maintenance Management</div>
<div class="brand-sub">OPERATIONS &nbsp;|&nbsp; WAY &amp; WORKS &nbsp;|&nbsp; MAINTENANCE</div>
</div>
</div>
<div class="topbar-right">
<div class="clock-chip">{datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %H:%M")}</div>
<div class="system-state">SYSTEM ONLINE</div>
</div>
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# CONNECTION + KPI DATA
# ============================================================
conn = get_connection()

def count_query(sql):
    try:
        res = safe_read_sql(sql, conn, default_cols=["c"])
        if not res.empty and "c" in res.columns:
            return int(res["c"].iloc[0])
        return 0
    except Exception:
        return 0

total_jobs = count_query("SELECT COUNT(*) AS c FROM Jobs")
pending_jobs = count_query("SELECT COUNT(*) AS c FROM Jobs WHERE status IS NULL OR status = 'Pending'")
scheduled_jobs = count_query("SELECT COUNT(*) AS c FROM Jobs WHERE status = 'Scheduled'")
delayed_jobs = count_query("SELECT COUNT(*) AS c FROM Jobs WHERE status = 'Delayed'")
total_blocks = count_query("SELECT COUNT(*) AS c FROM Block_Register")

res_dt = safe_read_sql("SELECT COALESCE(SUM(corridor_downtime_saved_mins), 0) AS s FROM Block_Register", conn, default_cols=["s"])
total_downtime_saved_mins = int(res_dt["s"].iloc[0]) if not res_dt.empty and "s" in res_dt.columns and pd.notna(res_dt["s"].iloc[0]) else 0

res_mt = safe_read_sql("SELECT COALESCE(SUM(min_duration_needed), 1) AS s FROM Jobs WHERE status = 'Scheduled'", conn, default_cols=["s"])
total_maint_time = int(res_mt["s"].iloc[0]) if not res_mt.empty and "s" in res_mt.columns and pd.notna(res_mt["s"].iloc[0]) else 1
uptime_gain_pct = round((total_downtime_saved_mins / max(total_maint_time, 1)) * 100.0, 1)


# ============================================================
# KPI ROW
# ============================================================
k1, k2, k3, k4, k5, k6 = st.columns(6)

with k1:
    st.metric("Total Jobs", total_jobs)
with k2:
    st.metric("Pending / Delayed", f"{pending_jobs} / {delayed_jobs}")
with k3:
    st.metric("Scheduled Jobs", scheduled_jobs)
with k4:
    st.metric("Shadow Blocks", total_blocks)
with k5:
    st.metric("Downtime Saved", f"{round(total_downtime_saved_mins/60, 1)} hrs")
with k6:
    st.metric("Asset Uptime Gain", f"{uptime_gain_pct}%")


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## Operations Office")

    st.selectbox(
        "Dashboard Theme",
        ["System", "Light", "Dark"],
        key="dashboard_theme",
        help="System follows your browser/OS preference for page colors.",
    )

    selected_horizon = st.selectbox(
        "Planning Horizon",
        ["All Horizons", "Weekly (7-Day Rolling)", "Monthly (30-Day Strategic)"],
        index=0,
        help="Filter optimization and block schedules by operational planning horizon."
    )
    horizon_param = "Weekly" if "Weekly" in selected_horizon else ("Monthly" if "Monthly" in selected_horizon else "All")

    st.write("")

    if st.button("Run Coordinated Optimizer", type="primary", use_container_width=True):
        with st.spinner("Executing AI Prioritization and Coordinated Shadow Block Scheduling..."):
            count = run_scheduler_pipeline(horizon=horizon_param)

        if count > 0:
            st.success(f"Generated {count} Coordinated Block(s) across departments!")
        else:
            st.info("No matching pending jobs fit available corridor windows.")
        st.rerun()

    if st.button("Reset & Regenerate Database", use_container_width=True):
        with st.spinner("Regenerating authentic TMS, SMMS, TDMS & COA dataset..."):
            reset_database()
        st.success("Database cleanly re-initialized with 30-day timetable!")
        st.rerun()

    st.divider()
    st.markdown("### + BDMS Maintenance Request")

    # Fetch track list for dropdown
    track_list = safe_read_sql("SELECT track_id, section_name FROM Tracks ORDER BY track_id", conn, default_cols=["track_id", "section_name"])
    if not track_list.empty and "track_id" in track_list.columns:
        track_choices = [f"{r['track_id']} ({r['section_name'][:24]})" for _, r in track_list.iterrows()]
    else:
        track_choices = ["TRK-101 (NDLS - CNB)", "TRK-102 (CNB - PRYJ)", "TRK-103 (PRYJ - DDU)"]

    with st.form("new_job_form", clear_on_submit=True):
        auto_id = f"JOB-{uuid.uuid4().hex[:6].upper()}"

        j_id = st.text_input("Work Order ID", value=auto_id)
        t_choice = st.selectbox("Corridor Track", track_choices)
        t_id = t_choice.split()[0] if t_choice else "TRK-101"

        dept_choice = st.selectbox("Department & Source", [
            "TMS - Engineering (P-Way)",
            "TDMS - Traction Distribution (TRD)",
            "SMMS - Signal & Telecom (S&T)"
        ])
        if "TMS" in dept_choice:
            dept = "Engineering (P-Way)"
            src = "TMS"
        elif "TDMS" in dept_choice:
            dept = "Traction Distribution (TRD)"
            src = "TDMS"
        else:
            dept = "Signal & Telecom (S&T)"
            src = "SMMS"

        m_type = st.selectbox("Maintenance Type", ["Defect Rectification", "Overdue Cyclic Maintenance", "Preventive Overhaul"])
        task = st.text_input("Task Description", value="Ultrasonic Flaw Defect (USFD) Removal")
        severity = st.selectbox("Defect Severity", ["Critical", "High", "Medium", "Low"], index=1)
        overdue = st.number_input("Overdue Days", min_value=0, max_value=90, value=0)
        psr = st.selectbox("Speed Restriction Imposed (km/h)", [0, 30, 45, 60], index=0)
        duration = st.number_input("Duration Needed (min)", min_value=15, max_value=480, value=90)
        power_req = st.checkbox("Power Block Required (25kV OHE Isolation)", value=("TDMS" in src))
        horizon = st.selectbox("Horizon", ["Weekly", "Monthly"], index=0)
        req_date = st.date_input("Request Date", value=date.today())
        deadline_date = st.date_input("Deadline", value=date.today() + timedelta(days=7))

        submitted = st.form_submit_button(
            "Submit Work Order to BDMS",
            use_container_width=True,
            type="primary",
        )

        if submitted:
            if not j_id:
                st.error("Please enter a valid Job ID.")
            elif deadline_date < req_date:
                st.error("Deadline cannot be before request date.")
            else:
                try:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO Jobs
                            (job_id, track_id, department, source_system, maintenance_type,
                             task, defect_severity, overdue_days, speed_restriction_imposed,
                             min_duration_needed, power_block_required, traffic_block_required,
                             planning_horizon, request_date, deadline, status, ai_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'Pending', NULL)
                        """,
                        (
                            j_id, t_id, dept, src, m_type,
                            task, severity, overdue, psr,
                            duration, 1 if power_req else 0,
                            horizon, req_date.strftime("%Y-%m-%d"),
                            deadline_date.strftime("%Y-%m-%d"),
                        ),
                    )
                    conn.commit()
                    # Trigger scorer for new job
                    run_scoring_engine(db_path=DB_PATH)
                    st.success(f"Work order {j_id} added to {src} queue with AI scoring.")
                    st.rerun()
                except sqlite3.IntegrityError as err:
                    if "UNIQUE constraint failed" in str(err):
                        st.error(f"Job ID '{j_id}' already exists.")
                    else:
                        st.error(f"Could not save job: {err}")


# ============================================================
# LOAD DATA USED BY MULTIPLE TABS
# ============================================================
blocks_df = safe_read_sql(
    """
    SELECT
        b.block_id AS 'Block ID',
        b.track_id AS 'Track',
        t.section_name AS 'Corridor Section',
        b.window_start AS 'Window Start',
        b.window_end AS 'Window End',
        b.duration_mins AS 'Duration (m)',
        b.total_departments_involved AS 'Depts Involved',
        b.departments_list AS 'Consolidated Departments',
        b.tasks_count AS 'Tasks Bundled',
        CASE WHEN b.power_block_granted = 1 THEN 'Yes (OHE Off)' ELSE 'No' END AS 'Power Block',
        b.corridor_downtime_saved_mins AS 'Downtime Saved (m)',
        b.planning_horizon AS 'Horizon',
        b.status AS 'Status'
    FROM Block_Register b
    LEFT JOIN Tracks t ON b.track_id = t.track_id
    ORDER BY b.window_start ASC
    """,
    conn,
    default_cols=[
        'Block ID', 'Track', 'Corridor Section', 'Window Start', 'Window End',
        'Duration (m)', 'Depts Involved', 'Consolidated Departments', 'Tasks Bundled',
        'Power Block', 'Downtime Saved (m)', 'Horizon', 'Status'
    ]
)

jobs_df = safe_read_sql(
    """
    SELECT
        j.job_id AS 'Job ID',
        j.track_id AS 'Track',
        t.section_name AS 'Section',
        j.source_system AS 'Source',
        j.department AS 'Department',
        j.maintenance_type AS 'Type',
        j.task AS 'Task Details',
        j.defect_severity AS 'Severity',
        j.overdue_days AS 'Overdue (d)',
        j.speed_restriction_imposed AS 'PSR (km/h)',
        j.min_duration_needed AS 'Duration (m)',
        CASE WHEN j.power_block_required = 1 THEN 'Yes' ELSE 'No' END AS 'Power Req',
        j.planning_horizon AS 'Horizon',
        j.request_date AS 'Requested',
        j.deadline AS 'Deadline',
        j.ai_score AS 'AI Score',
        COALESCE(j.status, 'Pending') AS 'Status'
    FROM Jobs j
    LEFT JOIN Tracks t ON j.track_id = t.track_id
    ORDER BY j.ai_score DESC
    """,
    conn,
    default_cols=[
        'Job ID', 'Track', 'Section', 'Source', 'Department', 'Type', 'Task Details',
        'Severity', 'Overdue (d)', 'PSR (km/h)', 'Duration (m)', 'Power Req',
        'Horizon', 'Requested', 'Deadline', 'AI Score', 'Status'
    ]
)

avail_df = safe_read_sql(
    """
    SELECT
        a.availability_id AS 'Window ID',
        a.track_id AS 'Track',
        t.section_name AS 'Section',
        a.available_date AS 'Date',
        a.window_start AS 'Available From',
        a.window_end AS 'Available Until',
        a.duration_mins AS 'Duration (m)',
        a.window_type AS 'Window Type'
    FROM Corridor_Availability a
    LEFT JOIN Tracks t ON a.track_id = t.track_id
    ORDER BY a.available_date ASC, a.window_start ASC
    """,
    conn,
    default_cols=[
        'Window ID', 'Track', 'Section', 'Date', 'Available From',
        'Available Until', 'Duration (m)', 'Window Type'
    ]
)

trains_df = safe_read_sql(
    """
    SELECT
        tr.train_id AS 'Instance ID',
        tr.train_number AS 'Train No.',
        tr.train_name AS 'Train Name',
        tr.train_type AS 'Category',
        tr.track_id AS 'Track',
        tr.run_date AS 'Date',
        tr.scheduled_arrival AS 'Arrival',
        tr.scheduled_departure AS 'Departure',
        tr.flexibility_mins AS 'Flexibility (m)'
    FROM Trains tr
    ORDER BY tr.run_date ASC, tr.scheduled_arrival ASC
    """,
    conn,
    default_cols=[
        'Instance ID', 'Train No.', 'Train Name', 'Category', 'Track',
        'Date', 'Arrival', 'Departure', 'Flexibility (m)'
    ]
)


# ============================================================
# THEME-SAFE HTML TABLES
# ============================================================
def _score_color(score):
    """Green for low priority, amber in the middle, red for urgent."""
    if score >= 75:
        return resolved_theme["red"]
    if score >= 45:
        return resolved_theme["amber"]
    return resolved_theme["green"]


def render_vintage_table(df, progress_column=None):
    if df.empty:
        return
    import html
    cols = list(df.columns)
    parts = ['<div class="vintage-table-wrap"><table class="vintage-table"><thead><tr>']
    for col in cols:
        parts.append(f'<th>{html.escape(str(col))}</th>')
    parts.append('</tr></thead><tbody>')
    for _, row in df.iterrows():
        parts.append('<tr>')
        for col in cols:
            value = row[col]
            if pd.isna(value):
                value = ''
            if progress_column and col == progress_column:
                try:
                    score = max(0, min(100, float(value)))
                    fill_color = _score_color(score)
                    cell = (
                        '<div class="score-wrap"><div class="score-bar">'
                        f'<div class="score-fill" style="width:{score:.0f}%;background:{fill_color}"></div>'
                        f'</div><span class="score-value">{score:.0f}</span></div>'
                    )
                except Exception:
                    cell = html.escape(str(value))
            elif col == "Status":
                pill_colors = {
                    "Scheduled": resolved_theme["status_colors"]["Scheduled"],
                    "Pending": resolved_theme["status_colors"]["Pending"],
                    "Delayed": resolved_theme["status_colors"]["Delayed"],
                }
                color = pill_colors.get(str(value), resolved_theme["muted"])
                cell = f'<span class="status-pill" style="background:{color}22;color:{color};border-color:{color}55">{html.escape(str(value))}</span>'
            else:
                cell = html.escape(str(value))
            parts.append(f'<td>{cell}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    st.markdown(''.join(parts), unsafe_allow_html=True)


# ============================================================
# CHART THEME HELPER
# ============================================================
def apply_chart_theme(fig, title_margin=55, show_legend=None):
    fig.update_layout(
        paper_bgcolor=resolved_theme["chart_paper"],
        plot_bgcolor=resolved_theme["chart_plot"],
        font_color=resolved_theme["chart_font"],
        title_font_color=resolved_theme["chart_font"],
        margin=dict(t=title_margin, b=25, l=25, r=20),
        xaxis=dict(gridcolor=resolved_theme["chart_grid"], zerolinecolor=resolved_theme["chart_grid"]),
        yaxis=dict(gridcolor=resolved_theme["chart_grid"], zerolinecolor=resolved_theme["chart_grid"]),
    )
    if show_legend is not None:
        fig.update_layout(showlegend=show_legend)
    return fig


# ============================================================
# MAIN TABS: 5-PILLAR RAILWAY MAINTENANCE SYSTEM
# ============================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Shadow Blocks", 
        "Integrated Backlog (TMS/SMMS/TDMS)", 
        "Corridor Availability (COA)", 
        "Multi-Horizon Planning", 
        "AI Engine & Analytics"
    ]
)


# ============================================================
# TAB 1 - COORDINATED SHADOW BLOCKS
# ============================================================
with tab1:
    st.markdown('<div class="section-head">Coordinated Multi-Department Block Register (Joint Possessions)</div>', unsafe_allow_html=True)
    st.caption("Bundles compatible tasks across Engineering (TMS), Traction Distribution (TDMS), and Signal & Telecom (SMMS) to minimize corridor downtime.")

    if blocks_df.empty:
        st.markdown(
            '<div class="info-box">No Coordinated Blocks registered yet. Use <b>Run Coordinated Optimizer</b> from the Operations Office.</div>',
            unsafe_allow_html=True,
        )
    else:
        # Horizon filter for blocks
        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            blk_horizon_filter = st.selectbox("Filter Block Horizon", ["All", "Weekly", "Monthly"], key="blk_horizon_f")
        with col_f2:
            blk_track_filter = st.selectbox("Filter Track", ["All Tracks"] + sorted(list(blocks_df["Track"].unique())), key="blk_trk_f")

        filtered_blocks = blocks_df.copy()
        if blk_horizon_filter != "All":
            filtered_blocks = filtered_blocks[filtered_blocks["Horizon"] == blk_horizon_filter]
        if blk_track_filter != "All Tracks":
            filtered_blocks = filtered_blocks[filtered_blocks["Track"] == blk_track_filter]

        render_vintage_table(filtered_blocks)

        # Interactive Block Task Drill-Down
        st.markdown('<div class="section-head">Block Task Mapping & Departmental Coordination</div>', unsafe_allow_html=True)
        block_options = filtered_blocks["Block ID"].unique() if not filtered_blocks.empty else blocks_df["Block ID"].unique()
        
        selected_block = st.selectbox("Select Block to inspect bundled tasks", block_options, key="select_block_details")

        if selected_block:
            details_df = safe_read_sql(
                """
                SELECT
                    j.job_id AS 'Job ID',
                    j.source_system AS 'Source',
                    j.department AS 'Department',
                    j.maintenance_type AS 'Type',
                    j.task AS 'Task Details',
                    j.defect_severity AS 'Severity',
                    j.overdue_days AS 'Overdue (d)',
                    j.min_duration_needed AS 'Duration (m)',
                    CASE WHEN j.power_block_required = 1 THEN 'Yes' ELSE 'No' END AS 'OHE Power Off',
                    j.ai_score AS 'AI Priority'
                FROM Block_Jobs bj
                JOIN Jobs j ON bj.job_id = j.job_id
                WHERE bj.block_id = ?
                ORDER BY j.ai_score DESC
                """,
                conn,
                params=(selected_block,),
                default_cols=[
                    'Job ID', 'Source', 'Department', 'Type', 'Task Details',
                    'Severity', 'Overdue (d)', 'Duration (m)', 'OHE Power Off', 'AI Priority'
                ]
            )
        else:
            details_df = pd.DataFrame(columns=[
                'Job ID', 'Source', 'Department', 'Type', 'Task Details',
                'Severity', 'Overdue (d)', 'Duration (m)', 'OHE Power Off', 'AI Priority'
            ])

        render_vintage_table(details_df, progress_column="AI Priority")

        # Visual Gantt of blocks
        if not filtered_blocks.empty:
            st.markdown('<div class="section-head">Corridor Possession Timeline</div>', unsafe_allow_html=True)
            gantt_df = filtered_blocks.head(25).copy()
            gantt_df["Start"] = pd.to_datetime(gantt_df["Window Start"])
            gantt_df["End"] = pd.to_datetime(gantt_df["Window End"])

            fig_blk_gantt = px.timeline(
                gantt_df,
                x_start="Start",
                x_end="End",
                y="Track",
                color="Depts Involved",
                hover_data=["Block ID", "Consolidated Departments", "Downtime Saved (m)"],
                title="Coordinated Possessions Timeline by Track",
                color_continuous_scale=resolved_theme["dept_scale"],
            )
            fig_blk_gantt.update_yaxes(autorange="reversed")
            fig_blk_gantt = apply_chart_theme(fig_blk_gantt, show_legend=True)
            st.plotly_chart(fig_blk_gantt, use_container_width=True, config={"displaylogo": False})


# ============================================================
# TAB 2 - INTEGRATED MAINTENANCE BACKLOG (TMS / SMMS / TDMS)
# ============================================================
with tab2:
    st.markdown('<div class="section-head">Integrated Maintenance Queue across TMS, SMMS &amp; TDMS</div>', unsafe_allow_html=True)

    c_src, c_stat, c_sev, c_hor = st.columns(4)
    with c_src:
        src_filter = st.selectbox("Source System", ["All", "TMS (Engineering)", "TDMS (Electrical/TRD)", "SMMS (Signal & Telecom)"])
    with c_stat:
        status_filter = st.selectbox("Status", ["All", "Scheduled", "Pending", "Delayed"])
    with c_sev:
        sev_filter = st.selectbox("Severity", ["All", "Critical", "High", "Medium", "Low"])
    with c_hor:
        hor_filter = st.selectbox("Horizon", ["All", "Weekly", "Monthly"])

    filtered_jobs = jobs_df.copy()
    if src_filter != "All":
        src_code = src_filter.split()[0]
        filtered_jobs = filtered_jobs[filtered_jobs["Source"] == src_code]
    if status_filter != "All":
        filtered_jobs = filtered_jobs[filtered_jobs["Status"] == status_filter]
    if sev_filter != "All":
        filtered_jobs = filtered_jobs[filtered_jobs["Severity"] == sev_filter]
    if hor_filter != "All":
        filtered_jobs = filtered_jobs[filtered_jobs["Horizon"] == hor_filter]

    st.caption(f"Showing {len(filtered_jobs)} work orders matching filters.")
    render_vintage_table(filtered_jobs, progress_column="AI Score")


# ============================================================
# TAB 3 - CORRIDOR AVAILABILITY & TRAFFIC MANAGEMENT (COA)
# ============================================================
with tab3:
    st.markdown('<div class="section-head">Control Office Application (COA) Corridor Availability &amp; Timetables</div>', unsafe_allow_html=True)

    coa_view = st.radio("COA Data View", ["Candidate Free Corridor Windows", "Passenger Timetables & Goods Trains Forecast"], horizontal=True)

    if coa_view == "Candidate Free Corridor Windows":
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            avail_trk = st.selectbox("Filter Corridor Track", ["All Tracks"] + sorted(list(avail_df["Track"].unique())), key="avail_trk")
        with col_a2:
            avail_wtype = st.selectbox("Window Type", ["All Types", "Natural Train Gap", "Goods Regulated Window", "Night Corridor Gap"])

        filtered_avail = avail_df.copy()
        if avail_trk != "All Tracks":
            filtered_avail = filtered_avail[filtered_avail["Track"] == avail_trk]
        if avail_wtype != "All Types":
            filtered_avail = filtered_avail[filtered_avail["Window Type"] == avail_wtype]

        render_vintage_table(filtered_avail.head(40))

        if not filtered_avail.empty:
            timeline_df = filtered_avail.head(30).copy()
            timeline_df["Available From"] = pd.to_datetime(timeline_df["Available From"])
            timeline_df["Available Until"] = pd.to_datetime(timeline_df["Available Until"])

            fig_avail = px.timeline(
                timeline_df,
                x_start="Available From",
                x_end="Available Until",
                y="Track",
                color="Window Type",
                hover_data=["Window ID", "Duration (m)"],
                title="Free Corridor Maintenance Windows Timeline",
            )
            fig_avail.update_yaxes(autorange="reversed", showgrid=False)
            fig_avail = apply_chart_theme(fig_avail, show_legend=True)
            st.plotly_chart(fig_avail, use_container_width=True, config={"displaylogo": False})

    else:
        st.markdown('<div class="section-head">Passenger Timetable &amp; COA Freight Corridor Forecast</div>', unsafe_allow_html=True)
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            train_cat = st.selectbox("Filter Category", ["All Categories", "Passenger Premium", "Passenger Express", "Goods Forecast - Coal", "Goods Forecast - Container", "Goods Forecast - POL", "Goods Forecast - Steel", "Goods Forecast - General"])
        with col_t2:
            train_trk = st.selectbox("Filter Track Section", ["All Tracks"] + sorted(list(trains_df["Track"].unique())), key="trn_trk")

        filtered_trains = trains_df.copy()
        if train_cat != "All Categories":
            filtered_trains = filtered_trains[filtered_trains["Category"] == train_cat]
        if train_trk != "All Tracks":
            filtered_trains = filtered_trains[filtered_trains["Track"] == train_trk]

        render_vintage_table(filtered_trains.head(45))


# ============================================================
# TAB 4 - MULTI-HORIZON PLANNING (WEEKLY & MONTHLY)
# ============================================================
with tab4:
    st.markdown('<div class="section-head">Multi-Horizon Maintenance Planning (Weekly &amp; Monthly)</div>', unsafe_allow_html=True)
    st.caption("Balances immediate tactical safety repairs (7-day rolling) with heavy machinery strategic overhauls (30-day lookahead).")

    h_choice = st.radio("Select Planning Horizon View", ["Weekly Operational Plan (Days 1 - 7)", "Monthly Strategic Schedule (Days 1 - 30)"], horizontal=True)

    if "Weekly" in h_choice:
        st.markdown('<div class="section-head">Weekly Tactical Plan (Immediate Defect Rectifications &amp; Rolling Possessions)</div>', unsafe_allow_html=True)
        weekly_jobs = jobs_df[jobs_df["Horizon"] == "Weekly"].copy()
        weekly_blocks = blocks_df[blocks_df["Horizon"] == "Weekly"].copy()

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Weekly Active Jobs", len(weekly_jobs))
        with m2:
            st.metric("Weekly Coordinated Blocks", len(weekly_blocks))
        with m3:
            w_downtime = weekly_blocks["Downtime Saved (m)"].sum() if not weekly_blocks.empty else 0
            st.metric("Weekly Corridor Downtime Saved", f"{round(w_downtime/60, 1)} hrs")

        render_vintage_table(weekly_blocks)

        if not weekly_jobs.empty:
            st.markdown('<div class="section-head">Weekly Defect Resolution Queue by Department</div>', unsafe_allow_html=True)
            fig_w = px.histogram(
                weekly_jobs,
                x="Department",
                color="Status",
                barmode="group",
                color_discrete_map=resolved_theme["status_colors"],
                title="Weekly Work Order Execution by Department",
            )
            fig_w = apply_chart_theme(fig_w)
            st.plotly_chart(fig_w, use_container_width=True, config={"displaylogo": False})

    else:
        st.markdown('<div class="section-head">Monthly Strategic Horizon (Heavy Machinery &amp; Track Renewal Cycles)</div>', unsafe_allow_html=True)
        monthly_jobs = jobs_df[jobs_df["Horizon"] == "Monthly"].copy()
        monthly_blocks = blocks_df[blocks_df["Horizon"] == "Monthly"].copy()

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Monthly Strategic Jobs", len(monthly_jobs))
        with m2:
            st.metric("Monthly Coordinated Mega-Blocks", len(monthly_blocks))
        with m3:
            m_downtime = monthly_blocks["Downtime Saved (m)"].sum() if not monthly_blocks.empty else 0
            st.metric("Monthly Corridor Downtime Saved", f"{round(m_downtime/60, 1)} hrs")

        render_vintage_table(monthly_blocks)

        if not monthly_jobs.empty:
            st.markdown('<div class="section-head">30-Day Heavy Maintenance Allocation by Track</div>', unsafe_allow_html=True)
            trk_work = monthly_jobs.groupby(["Track", "Type"]).size().reset_index(name="Count")
            fig_m = px.bar(
                trk_work,
                x="Track",
                y="Count",
                color="Type",
                title="30-Day Maintenance Distribution across Corridors",
            )
            fig_m = apply_chart_theme(fig_m)
            st.plotly_chart(fig_m, use_container_width=True, config={"displaylogo": False})


# ============================================================
# TAB 5 - AI ENGINE & OPERATIONS ANALYTICS
# ============================================================
with tab5:
    st.markdown('<div class="section-head">AI Prioritization &amp; Coordinated Scheduling Analytics</div>', unsafe_allow_html=True)

    if jobs_df.empty:
        st.info("No job data available for analytics.")
    else:
        c1, c2 = st.columns(2)

        with c1:
            status_data = pd.DataFrame(
                {
                    "Status": ["Scheduled", "Pending", "Delayed"],
                    "Count": [scheduled_jobs, pending_jobs, delayed_jobs],
                }
            )
            fig_status = px.pie(
                status_data,
                names="Status",
                values="Count",
                hole=0.65,
                color="Status",
                color_discrete_map=resolved_theme["status_colors"],
                title="Work Order Scheduling Status",
            )
            fig_status = apply_chart_theme(fig_status)
            fig_status.update_layout(legend=dict(orientation="h", y=-0.08))
            st.plotly_chart(fig_status, use_container_width=True, config={"displaylogo": False})

        with c2:
            dept_data = jobs_df.groupby("Source").size().reset_index(name="Jobs")
            dept_map = {"TMS": "TMS (Civil/P-Way)", "TDMS": "TDMS (Electrical/TRD)", "SMMS": "SMMS (Signal & Telecom)"}
            dept_data["System"] = dept_data["Source"].map(lambda s: dept_map.get(s, s))
            fig_dept = px.bar(
                dept_data,
                x="System",
                y="Jobs",
                text="Jobs",
                color="Jobs",
                color_continuous_scale=resolved_theme["dept_scale"],
                title="Departmental Backlog Distribution (TMS vs TDMS vs SMMS)",
            )
            fig_dept.update_layout(coloraxis_showscale=False, xaxis=dict(showgrid=False))
            fig_dept = apply_chart_theme(fig_dept)
            st.plotly_chart(fig_dept, use_container_width=True, config={"displaylogo": False})

        c3, c4 = st.columns(2)

        with c3:
            fig_priority = px.histogram(
                jobs_df,
                x="AI Score",
                nbins=15,
                marginal="box",
                title="AI Priority Score Distribution",
                color_discrete_sequence=[resolved_theme["blue"]],
            )
            fig_priority = apply_chart_theme(fig_priority)
            st.plotly_chart(fig_priority, use_container_width=True, config={"displaylogo": False})

        with c4:
            # AI Factor Contributions Breakdown
            ai_factors_df = pd.DataFrame({
                "Evaluation Factor": [
                    "Safety & Defect Severity Risk",
                    "Statutory Overdue Penalty",
                    "Route Class & Asset Tonnage",
                    "Operational Capacity (PSR Lifting)",
                    "Statutory Departmental Compliance"
                ],
                "Weight (%)": [30, 25, 20, 15, 10]
            })
            fig_factors = px.bar(
                ai_factors_df,
                x="Weight (%)",
                y="Evaluation Factor",
                orientation="h",
                text="Weight (%)",
                color="Weight (%)",
                color_continuous_scale=resolved_theme["dept_scale"],
                title="AI Prioritization Model - Feature Weights",
            )
            fig_factors.update_layout(coloraxis_showscale=False, yaxis=dict(autorange="reversed"))
            fig_factors = apply_chart_theme(fig_factors, show_legend=False)
            st.plotly_chart(fig_factors, use_container_width=True, config={"displaylogo": False})

        st.markdown('<div class="section-head">Shadow Block Consolidation Efficiency</div>', unsafe_allow_html=True)

        if not blocks_df.empty:
            eff_df = blocks_df.head(20).copy()
            fig_blocks = px.bar(
                eff_df,
                x="Block ID",
                y="Downtime Saved (m)",
                color="Tasks Bundled",
                text="Downtime Saved (m)",
                title="Corridor Downtime Saved per Coordinated Shadow Block (Minutes)",
                hover_data=["Track", "Consolidated Departments"],
                color_continuous_scale=resolved_theme["dept_scale"],
            )
            fig_blocks.update_layout(xaxis=dict(showgrid=False))
            fig_blocks = apply_chart_theme(fig_blocks, title_margin=55)
            st.plotly_chart(fig_blocks, use_container_width=True, config={"displaylogo": False})


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.markdown(
    """
<div style="text-align:center;color:var(--muted);font-size:12px;padding:10px 0 0 0;">
<b>Automatic Block Planning System</b> &nbsp;|&nbsp;
Integrated TMS (P-Way), SMMS (S&amp;T), TDMS (TRD) &amp; COA Engine &nbsp;|&nbsp;
Multi-Department AI Shadow Block Optimizer
</div>
""",
    unsafe_allow_html=True,
)