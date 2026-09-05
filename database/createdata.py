import os
import sqlite3

def init_db(db_path=None, drop_existing=False):
    """Initializes the relational SQLite database for the Automatic Block Planning System."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if db_path is None:
        db_path = os.path.join(base_dir, "railway_planning.db")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enforce foreign key constraints and universal DELETE journal mode
    cursor.execute("PRAGMA foreign_keys = ON;")
    try:
        cursor.execute("PRAGMA journal_mode = DELETE;")
    except Exception:
        pass

    # Check if existing Jobs table needs schema migration
    needs_recreate = drop_existing
    if not needs_recreate:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Jobs'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(Jobs)")
            col_names = [row[1] for row in cursor.fetchall()]
            if "source_system" not in col_names:
                needs_recreate = True

    if needs_recreate:
        cursor.execute("DROP TABLE IF EXISTS Block_Jobs;")
        cursor.execute("DROP TABLE IF EXISTS Block_Register;")
        cursor.execute("DROP TABLE IF EXISTS Corridor_Availability;")
        cursor.execute("DROP TABLE IF EXISTS Jobs;")
        cursor.execute("DROP TABLE IF EXISTS Trains;")
        cursor.execute("DROP TABLE IF EXISTS Tracks;")

    # 1. Tracks Table (Physical asset info, route class, line speed, GMT)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Tracks (
            track_id            TEXT PRIMARY KEY,
            section_name        TEXT NOT NULL,
            start_station       TEXT NOT NULL,
            end_station         TEXT NOT NULL,
            route_class         TEXT NOT NULL DEFAULT 'Trunk Route A',
            track_age           INTEGER NOT NULL,
            speed_limit_kmh     INTEGER NOT NULL DEFAULT 130,
            gmt_tonnage         REAL NOT NULL DEFAULT 35.0,
            last_inspected_date TEXT NOT NULL,
            criticality_level   TEXT NOT NULL,
            electrified         INTEGER NOT NULL DEFAULT 1,
            signaling_type      TEXT NOT NULL DEFAULT 'Electronic Interlocking'
        )
    """)

    # 2. Trains Table (Passenger timetable + COA Goods train forecast)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Trains (
            train_id            TEXT PRIMARY KEY,
            train_number        TEXT NOT NULL,
            train_name          TEXT NOT NULL,
            train_type          TEXT NOT NULL,
            track_id            TEXT NOT NULL,
            run_date            TEXT NOT NULL,
            scheduled_arrival   TEXT NOT NULL,
            scheduled_departure TEXT NOT NULL,
            priority_tier       INTEGER NOT NULL DEFAULT 2,
            flexibility_mins    INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (track_id) REFERENCES Tracks (track_id) ON DELETE CASCADE
        )
    """)

    # 3. Jobs Table (Integrated Maintenance Backlog from TMS, SMMS, TDMS)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Jobs (
            job_id                     TEXT PRIMARY KEY,
            track_id                   TEXT NOT NULL,
            department                 TEXT NOT NULL,
            source_system              TEXT NOT NULL,
            maintenance_type           TEXT NOT NULL DEFAULT 'Defect Rectification',
            task                       TEXT NOT NULL,
            defect_severity            TEXT NOT NULL,
            overdue_days               INTEGER NOT NULL DEFAULT 0,
            speed_restriction_imposed  INTEGER NOT NULL DEFAULT 0,
            min_duration_needed        INTEGER NOT NULL,
            power_block_required       INTEGER NOT NULL DEFAULT 0,
            traffic_block_required     INTEGER NOT NULL DEFAULT 1,
            planning_horizon           TEXT NOT NULL DEFAULT 'Weekly',
            request_date               TEXT NOT NULL,
            deadline                   TEXT NOT NULL,
            ai_score                   REAL,
            scheduled_start            TEXT,
            scheduled_end              TEXT,
            block_id                   TEXT,
            status                     TEXT NOT NULL DEFAULT 'Pending',
            FOREIGN KEY (track_id) REFERENCES Tracks (track_id) ON DELETE CASCADE
        )
    """)

    # 4. Corridor_Availability Table (Computed free windows from passenger & goods train slots)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Corridor_Availability (
            availability_id     TEXT PRIMARY KEY,
            track_id            TEXT NOT NULL,
            available_date      TEXT NOT NULL,
            window_start        TEXT NOT NULL,
            window_end          TEXT NOT NULL,
            duration_mins       INTEGER NOT NULL,
            window_type         TEXT NOT NULL DEFAULT 'Natural Train Gap',
            consumed_mins       INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (track_id) REFERENCES Tracks (track_id) ON DELETE CASCADE
        )
    """)

    # 5. Block_Register Table (Coordinated multi-department possessions / Shadow Blocks)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Block_Register (
            block_id                    TEXT PRIMARY KEY,
            track_id                    TEXT NOT NULL,
            window_start                TEXT NOT NULL,
            window_end                  TEXT NOT NULL,
            duration_mins               INTEGER NOT NULL,
            total_departments_involved INTEGER NOT NULL DEFAULT 1,
            departments_list            TEXT NOT NULL,
            tasks_count                 INTEGER NOT NULL DEFAULT 1,
            power_block_granted         INTEGER NOT NULL DEFAULT 0,
            corridor_downtime_saved_mins INTEGER NOT NULL DEFAULT 0,
            planning_horizon            TEXT NOT NULL DEFAULT 'Weekly',
            status                      TEXT NOT NULL DEFAULT 'Approved',
            FOREIGN KEY (track_id) REFERENCES Tracks (track_id) ON DELETE CASCADE
        )
    """)

    # 6. Block_Jobs Table (Junction linking consolidated jobs to a single coordinated block)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Block_Jobs (
            block_id TEXT NOT NULL,
            job_id   TEXT NOT NULL,
            PRIMARY KEY (block_id, job_id),
            FOREIGN KEY (block_id) REFERENCES Block_Register (block_id) ON DELETE CASCADE,
            FOREIGN KEY (job_id)   REFERENCES Jobs (job_id) ON DELETE CASCADE
        )
    """)

    # Indexing for high-performance scheduling and queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_crit ON Tracks (criticality_level);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trains_corridor ON Trains (track_id, run_date, scheduled_arrival);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_schedule ON Jobs (track_id, status, planning_horizon, ai_score);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source ON Jobs (source_system, department);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_avail_window ON Corridor_Availability (track_id, available_date, window_start);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_block_timeline ON Block_Register (track_id, window_start, planning_horizon);")

    conn.commit()
    conn.close()
    print(f"6-table relational schema successfully initialized at: {db_path}")

if __name__ == "__main__":
    init_db()