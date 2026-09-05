import os
import sqlite3

def init_db():
    # Dynamically resolve DB path inside the database folder
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "railway_planning.db")

    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enforce foreign key constraints
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Tracks Table (Physical asset info and inspection recency for AI scoring)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Tracks (
            track_id            TEXT PRIMARY KEY,
            section_name        TEXT NOT NULL,
            start_station       TEXT NOT NULL,
            end_station         TEXT NOT NULL,
            track_age           INTEGER NOT NULL,
            last_inspected_date TEXT NOT NULL,
            criticality_level   TEXT NOT NULL
        )
    """)

    # 2. Trains Table (Date-based corridor occupancy schedules)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Trains (
            train_id            TEXT PRIMARY KEY,
            train_name          TEXT NOT NULL,
            track_id            TEXT NOT NULL,
            days_of_operation   TEXT NOT NULL,
            run_date            TEXT NOT NULL,
            scheduled_arrival   TEXT NOT NULL,
            scheduled_departure TEXT NOT NULL,
            FOREIGN KEY (track_id) REFERENCES Tracks (track_id) ON DELETE CASCADE
        )
    """)

    # 3. Jobs Table (Maintenance requests, urgency parameters, and scheduling output)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Jobs (
            job_id              TEXT PRIMARY KEY,
            track_id            TEXT NOT NULL,
            department          TEXT NOT NULL,
            task                TEXT NOT NULL,
            min_duration_needed INTEGER NOT NULL,
            defect_severity     TEXT NOT NULL,
            request_date        TEXT NOT NULL,
            deadline            TEXT NOT NULL,
            ai_score            REAL,
            scheduled_start     TEXT,
            scheduled_end       TEXT,
            status              TEXT NOT NULL DEFAULT 'Pending',
            FOREIGN KEY (track_id) REFERENCES Tracks (track_id) ON DELETE CASCADE
        )
    """)

    # 4. Corridor_Availability Table (Dynamic candidate free windows cache)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Corridor_Availability (
            availability_id     TEXT PRIMARY KEY,
            track_id            TEXT NOT NULL,
            available_date      TEXT NOT NULL,
            window_start        TEXT NOT NULL,
            window_end          TEXT NOT NULL,
            FOREIGN KEY (track_id) REFERENCES Tracks (track_id) ON DELETE CASCADE
        )
    """)

    # 5. Block_Register Table (Committed maintenance possessions granted by scheduler)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Block_Register (
            block_id                    TEXT PRIMARY KEY,
            track_id                    TEXT NOT NULL,
            window_start                TEXT NOT NULL,
            window_end                  TEXT NOT NULL,
            total_departments_involved INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (track_id) REFERENCES Tracks (track_id) ON DELETE CASCADE
        )
    """)

    # 6. Block_Jobs Table (Junction table linking multiple consolidated jobs into one block)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Block_Jobs (
            block_id TEXT NOT NULL,
            job_id   TEXT NOT NULL,
            PRIMARY KEY (block_id, job_id),
            FOREIGN KEY (block_id) REFERENCES Block_Register (block_id) ON DELETE CASCADE,
            FOREIGN KEY (job_id)   REFERENCES Jobs (job_id) ON DELETE CASCADE
        )
    """)

    # Indexing for conflict checks and date-range queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trains_corridor ON Trains (track_id, run_date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_schedule   ON Jobs (track_id, status, deadline);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_avail_window    ON Corridor_Availability (track_id, available_date);")

    conn.commit()
    conn.close()
    print(f"6-table database successfully created at: {db_path}")

if __name__ == "__main__":
    init_db()