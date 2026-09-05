import sqlite3
import random
from datetime import datetime, date, timedelta
from  zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# DATABASE
# ============================================================
DB_PATH = "database/railway_planning.db"


@st.cache_resource
def get_shared_connection():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def get_connection():
    return get_shared_connection()


# ============================================================
# AI SCHEDULER
# ============================================================
def run_scheduler_pipeline():
    conn = get_connection()
    cursor = conn.cursor()
    blocks_created = 0

    while True:
        cursor.execute(
            """
            SELECT job_id, track_id, min_duration_needed, task, department, ai_score
            FROM Jobs
            WHERE status IS NULL OR status = 'Pending'
            ORDER BY ai_score DESC
            LIMIT 1
            """
        )
        top_job = cursor.fetchone()

        if not top_job:
            break

        main_job_id, target_track, needed_time, task_name, dept, score = top_job

        cursor.execute(
            """
            SELECT availability_id, window_start, window_end
            FROM Corridor_Availability
            WHERE track_id = ?
            LIMIT 1
            """,
            (target_track,),
        )
        window = cursor.fetchone()

        if not window:
            cursor.execute(
                "UPDATE Jobs SET status = 'Delayed' WHERE job_id = ?",
                (main_job_id,),
            )
            conn.commit()
            continue

        avail_id, block_start, block_end = window

        try:
            start_dt = datetime.strptime(block_start, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(block_end, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            start_dt = datetime.strptime(block_start, "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(block_end, "%Y-%m-%d %H:%M")

        available_mins = (end_dt - start_dt).total_seconds() / 60.0

        if needed_time > available_mins:
            cursor.execute(
                "UPDATE Jobs SET status = 'Delayed' WHERE job_id = ?",
                (main_job_id,),
            )
            conn.commit()
            continue

        cursor.execute(
            """
            SELECT job_id, task, department, min_duration_needed
            FROM Jobs
            WHERE track_id = ?
              AND job_id != ?
              AND (status IS NULL OR status = 'Pending')
            """,
            (target_track, main_job_id),
        )
        other_jobs = cursor.fetchall()

        valid_shadow_jobs = [
            job_id
            for job_id, _, _, duration in other_jobs
            if duration <= available_mins
        ]

        new_block_id = f"BLK-AI-{main_job_id[-4:]}"
        total_depts = 1 + len(valid_shadow_jobs)

        try:
            cursor.execute(
                """
                INSERT INTO Block_Register
                    (block_id, track_id, window_start, window_end,
                     total_departments_involved)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_block_id, target_track, block_start, block_end, total_depts),
            )
        except sqlite3.OperationalError:
            try:
                cursor.execute(
                    """
                    INSERT INTO Block_Register
                        (block_id, track_id, window_start, window_end,
                         total_departments)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (new_block_id, target_track, block_start, block_end, total_depts),
                )
            except sqlite3.OperationalError:
                cursor.execute(
                    """
                    INSERT INTO Block_Register
                        (block_id, track_id, window_start, window_end)
                    VALUES (?, ?, ?, ?)
                    """,
                    (new_block_id, target_track, block_start, block_end),
                )

        cursor.execute(
            "INSERT INTO Block_Jobs (block_id, job_id) VALUES (?, ?)",
            (new_block_id, main_job_id),
        )
        cursor.execute(
            "UPDATE Jobs SET status = 'Scheduled' WHERE job_id = ?",
            (main_job_id,),
        )

        for valid_id in valid_shadow_jobs:
            cursor.execute(
                "INSERT INTO Block_Jobs (block_id, job_id) VALUES (?, ?)",
                (new_block_id, valid_id),
            )
            cursor.execute(
                "UPDATE Jobs SET status = 'Scheduled' WHERE job_id = ?",
                (valid_id,),
            )

        conn.commit()
        blocks_created += 1

    return blocks_created


# ============================================================
# RESET DATABASE
# ============================================================
def reset_database():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM Block_Jobs")
    cur.execute("DELETE FROM Block_Register")
    cur.execute("UPDATE Jobs SET status = 'Pending'")
    conn.commit()


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
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded",
)

theme_name = st.session_state.dashboard_theme

# The theme actually used to color Plotly charts and to set an explicit
# color-scheme on inputs. "System" can't be resolved from Python (Streamlit
# has no server-side signal for OS/browser preference), so it renders with
# the Light palette by default while the page CSS still adapts to the
# browser's preference via the prefers-color-scheme media query below.
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
.system-state::before {{ content:"●"; margin-right:5px; }}
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
<div class="brand-sub">OPERATIONS &nbsp;•&nbsp; WAY &amp; WORKS &nbsp;•&nbsp; MAINTENANCE</div>
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
    return int(pd.read_sql_query(sql, conn)["c"].iloc[0])


total_jobs = count_query("SELECT COUNT(*) AS c FROM Jobs")
pending_jobs = count_query(
    "SELECT COUNT(*) AS c FROM Jobs WHERE status IS NULL OR status = 'Pending'"
)
scheduled_jobs = count_query(
    "SELECT COUNT(*) AS c FROM Jobs WHERE status = 'Scheduled'"
)
delayed_jobs = count_query(
    "SELECT COUNT(*) AS c FROM Jobs WHERE status = 'Delayed'"
)
total_blocks = count_query("SELECT COUNT(*) AS c FROM Block_Register")


# ============================================================
# KPI ROW
# ============================================================
k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.metric("Total Jobs", total_jobs)
with k2:
    st.metric("Pending", pending_jobs)
with k3:
    st.metric("Scheduled", scheduled_jobs)
with k4:
    st.metric("Delayed", delayed_jobs)
with k5:
    st.metric("Shadow Blocks", total_blocks)


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## Operations Office")

    # Bound directly to session_state via `key` — Streamlit reruns the
    # app automatically on change, so no manual comparison/rerun needed.
    st.selectbox(
        "Dashboard Theme",
        ["System", "Light", "Dark"],
        key="dashboard_theme",
        help="System follows your browser/OS preference for page colors. Charts use the Light palette while System is selected.",
    )

    st.write("")

    if st.button("▶ Run Maintenance Scheduler", type="primary", use_container_width=True):
        with st.spinner("Checking corridor availability and maintenance conflicts..."):
            count = run_scheduler_pipeline()

        if count > 0:
            st.success(f"Created {count} maintenance block(s)")
        else:
            st.info("No pending jobs fit the available corridor windows.")
        st.rerun()

    if st.button("↺ Reset Demo Database", use_container_width=True):
        reset_database()
        st.success("Database reset successfully.")
        st.rerun()

    st.divider()
    st.markdown("### + New Work Order")

    with st.form("new_job_form", clear_on_submit=True):
        auto_id = f"JOB-{random.randint(5000, 99999)}"

        j_id = st.text_input("Job ID", value=auto_id)
        t_id = st.text_input("Track ID", value="TRK-121")
        dept = st.selectbox("Department", ["Civil", "Electrical", "S&T", "Traffic"])
        task = st.text_input("Task Description", value="Ballast Shoulder Cleaning")
        severity = st.selectbox("Defect Severity", ["Low", "Medium", "High", "Critical"], index=1)
        duration = st.number_input("Duration (min)", min_value=15, max_value=480, value=60)
        req_date = st.date_input("Request Date", value=date.today())
        deadline_date = st.date_input("Deadline", value=date.today() + timedelta(days=7))
        score = st.slider("Priority Score", min_value=1.0, max_value=100.0, value=75.0)

        submitted = st.form_submit_button(
            "Submit Work Order",
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
                            (job_id, track_id, department, task, defect_severity,
                             min_duration_needed, request_date, deadline, status, ai_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
                        """,
                        (
                            j_id,
                            t_id,
                            dept,
                            task,
                            severity,
                            duration,
                            req_date.strftime("%Y-%m-%d"),
                            deadline_date.strftime("%Y-%m-%d"),
                            score,
                        ),
                    )
                    conn.commit()
                    st.success(f"Work order {j_id} added to the maintenance queue.")
                    st.rerun()
                except sqlite3.IntegrityError as err:
                    if "UNIQUE constraint failed" in str(err):
                        st.error(f"Job ID '{j_id}' already exists.")
                    else:
                        st.error(f"Could not save job: {err}")


# ============================================================
# LOAD DATA USED BY MULTIPLE TABS
# ============================================================
blocks_df = pd.read_sql_query(
    """
    SELECT
        b.block_id AS 'Block ID',
        b.track_id AS 'Track',
        b.window_start AS 'Window Start',
        b.window_end AS 'Window End',
        COUNT(bj.job_id) AS 'Bundled Tasks'
    FROM Block_Register b
    LEFT JOIN Block_Jobs bj ON b.block_id = bj.block_id
    GROUP BY b.block_id
    ORDER BY b.window_start ASC
    """,
    conn,
)

jobs_df = pd.read_sql_query(
    """
    SELECT
        job_id AS 'Job ID',
        track_id AS 'Track',
        department AS 'Department',
        task AS 'Task',
        defect_severity AS 'Severity',
        min_duration_needed AS 'Duration (m)',
        request_date AS 'Requested',
        deadline AS 'Deadline',
        ai_score AS 'AI Score',
        COALESCE(status, 'Pending') AS 'Status'
    FROM Jobs
    ORDER BY ai_score DESC
    """,
    conn,
)

avail_df = pd.read_sql_query(
    """
    SELECT
        availability_id AS 'Window ID',
        track_id AS 'Track',
        window_start AS 'Available From',
        window_end AS 'Available Until'
    FROM Corridor_Availability
    ORDER BY window_start ASC
    """,
    conn,
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
# MAIN TABS
# ============================================================
tab1, tab2, tab3, tab4 = st.tabs(
    ["Shadow Blocks", "Job Queue", "Corridor Gaps", "Analytics"]
)


# ============================================================
# TAB 1 - SHADOW BLOCKS
# ============================================================
with tab1:
    st.markdown('<div class="section-head">Consolidated Maintenance Blocks</div>', unsafe_allow_html=True)

    if blocks_df.empty:
        st.markdown(
            '<div class="info-box">No Shadow Blocks registered yet. Use <b>Run Maintenance Scheduler</b> from the Operations Office.</div>',
            unsafe_allow_html=True,
        )
    else:
        render_vintage_table(blocks_df)

        st.markdown('<div class="section-head">Block Task Mapping</div>', unsafe_allow_html=True)
        selected_block = st.selectbox("Select a block", blocks_df["Block ID"].unique())

        details_df = pd.read_sql_query(
            """
            SELECT
                j.job_id AS 'Job ID',
                j.department AS 'Department',
                j.task AS 'Task Details',
                j.min_duration_needed AS 'Duration (m)',
                j.ai_score AS 'Priority Score'
            FROM Block_Jobs bj
            JOIN Jobs j ON bj.job_id = j.job_id
            WHERE bj.block_id = ?
            """,
            conn,
            params=(selected_block,),
        )

        render_vintage_table(details_df, progress_column="Priority Score")


# ============================================================
# TAB 2 - JOB QUEUE
# ============================================================
with tab2:
    st.markdown('<div class="section-head">Job Priority &amp; Scheduling Status</div>', unsafe_allow_html=True)

    status_filter = st.radio(
        "Filter by status",
        ["All", "Pending", "Scheduled", "Delayed"],
        horizontal=True,
        label_visibility="collapsed",
    )

    filtered_jobs = jobs_df.copy()
    if status_filter != "All":
        filtered_jobs = filtered_jobs[filtered_jobs["Status"] == status_filter]

    render_vintage_table(filtered_jobs, progress_column="AI Score")


# ============================================================
# CHART THEME — single helper, no per-chart color duplication
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
# TAB 3 - CORRIDOR GAPS
# ============================================================
with tab3:
    st.markdown('<div class="section-head">Available Corridor Timetables</div>', unsafe_allow_html=True)

    render_vintage_table(avail_df)

    if not avail_df.empty:
        timeline_df = avail_df.copy()
        timeline_df["Available From"] = pd.to_datetime(timeline_df["Available From"])
        timeline_df["Available Until"] = pd.to_datetime(timeline_df["Available Until"])

        fig = px.timeline(
            timeline_df,
            x_start="Available From",
            x_end="Available Until",
            y="Track",
            color="Track",
            hover_data=["Window ID"],
            title="Corridor Availability Timeline",
        )
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig = apply_chart_theme(fig, show_legend=False)
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ============================================================
# TAB 4 - ANALYTICS
# ============================================================
with tab4:
    st.markdown('<div class="section-head">Operations Analytics</div>', unsafe_allow_html=True)

    if jobs_df.empty:
        st.info("No job data available for analytics.")
    else:
        chart1, chart2 = st.columns(2)

        with chart1:
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
                hole=0.68,
                color="Status",
                color_discrete_map=resolved_theme["status_colors"],
                title="Job Status Distribution",
            )
            fig_status = apply_chart_theme(fig_status)
            fig_status.update_layout(legend=dict(orientation="h", y=-0.08))
            st.plotly_chart(fig_status, use_container_width=True, config={"displaylogo": False})

        with chart2:
            dept_data = jobs_df.groupby("Department").size().reset_index(name="Jobs")
            fig_dept = px.bar(
                dept_data,
                x="Department",
                y="Jobs",
                text="Jobs",
                color="Jobs",
                color_continuous_scale=resolved_theme["dept_scale"],
                title="Department Workload",
            )
            fig_dept.update_layout(coloraxis_showscale=False, xaxis=dict(showgrid=False))
            fig_dept = apply_chart_theme(fig_dept)
            st.plotly_chart(fig_dept, use_container_width=True, config={"displaylogo": False})

        chart3, chart4 = st.columns(2)

        with chart3:
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

        with chart4:
            severity_data = jobs_df.groupby("Severity").size().reset_index(name="Jobs")
            severity_order = ["Low", "Medium", "High", "Critical"]
            severity_data["Severity"] = pd.Categorical(
                severity_data["Severity"], categories=severity_order, ordered=True
            )
            severity_data = severity_data.sort_values("Severity")

            fig_severity = px.bar(
                severity_data,
                x="Severity",
                y="Jobs",
                text="Jobs",
                title="Defect Severity Analysis",
                color="Severity",
                color_discrete_map=resolved_theme["severity_colors"],
            )
            fig_severity.update_layout(xaxis=dict(showgrid=False))
            fig_severity = apply_chart_theme(fig_severity, show_legend=False)
            st.plotly_chart(fig_severity, use_container_width=True, config={"displaylogo": False})

        st.markdown('<div class="section-head">Shadow Block Efficiency</div>', unsafe_allow_html=True)

        if not blocks_df.empty:
            efficiency_df = blocks_df[["Block ID", "Track", "Bundled Tasks"]].copy()
            fig_blocks = px.bar(
                efficiency_df,
                x="Block ID",
                y="Bundled Tasks",
                color="Bundled Tasks",
                text="Bundled Tasks",
                title="Tasks Consolidated per Shadow Block",
                hover_data=["Track"],
                color_continuous_scale=resolved_theme["dept_scale"],
            )
            fig_blocks.update_layout(coloraxis_showscale=False, xaxis=dict(showgrid=False))
            fig_blocks = apply_chart_theme(fig_blocks, title_margin=55)
            st.plotly_chart(fig_blocks, use_container_width=True, config={"displaylogo": False})
        else:
            st.info("Run the AI scheduler to generate Shadow Blocks.")


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.markdown(
    """
<div style="text-align:center;color:var(--muted);font-size:12px;padding:10px 0 0 0;">
<b>AI Rail Corridor Scheduler</b> &nbsp;•&nbsp;
Intelligent Maintenance Planning Engine &nbsp;•&nbsp;
AI Shadow Block Optimization
</div>
""",
    unsafe_allow_html=True,
)