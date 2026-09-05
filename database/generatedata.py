import os
import sqlite3
import random
from datetime import datetime, timedelta

def calculate_availability_for_corridors(cursor):
    """Calculates non-overlapping free time windows between train schedules for each track and date."""
    # 1. Clear old availability records
    cursor.execute("DELETE FROM Corridor_Availability;")

    # 2. Get all track_id and run_date pairs present in Trains
    cursor.execute("SELECT DISTINCT track_id, run_date FROM Trains ORDER BY run_date, track_id;")
    corridor_days = cursor.fetchall()

    availability_id_counter = 501
    avail_count = 0

    for track_id, run_date in corridor_days:
        day_start = datetime.strptime(f"{run_date} 00:00", "%Y-%m-%d %H:%M")
        day_end = datetime.strptime(f"{run_date} 23:59", "%Y-%m-%d %H:%M")

        # Fetch scheduled train occupancies sorted by arrival time
        cursor.execute("""
            SELECT scheduled_arrival, scheduled_departure, train_type, flexibility_mins
            FROM Trains 
            WHERE track_id = ? AND run_date = ? 
            ORDER BY scheduled_arrival ASC
        """, (track_id, run_date))
        
        train_rows = cursor.fetchall()

        # Merge overlapping train intervals
        merged_intervals = []
        for arr, dep, t_type, flex in train_rows:
            start = datetime.strptime(f"{run_date} {arr}", "%Y-%m-%d %H:%M")
            end = datetime.strptime(f"{run_date} {dep}", "%Y-%m-%d %H:%M")

            if not merged_intervals:
                merged_intervals.append([start, end, t_type])
            else:
                last_start, last_end, _ = merged_intervals[-1]
                if start <= last_end:
                    merged_intervals[-1][1] = max(last_end, end)
                else:
                    merged_intervals.append([start, end, t_type])

        # Find available gaps between merged slots
        current_time = day_start

        for start, end, _ in merged_intervals:
            if start > current_time:
                dur = int((start - current_time).total_seconds() / 60)
                # Only register windows of at least 30 minutes
                if dur >= 30:
                    avl_id = f"AVL-{availability_id_counter}"
                    availability_id_counter += 1
                    w_type = "Goods Regulated Window" if dur >= 180 else "Natural Train Gap"
                    
                    cursor.execute("""
                        INSERT INTO Corridor_Availability (
                            availability_id, track_id, available_date, window_start, window_end,
                            duration_mins, window_type, consumed_mins
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """, (
                        avl_id,
                        track_id,
                        run_date,
                        current_time.strftime("%Y-%m-%d %H:%M"),
                        start.strftime("%Y-%m-%d %H:%M"),
                        dur,
                        w_type
                    ))
                    avail_count += 1

            current_time = max(current_time, end)

        # Remaining window from last train departure to midnight
        if current_time < day_end:
            dur = int((day_end - current_time).total_seconds() / 60)
            if dur >= 30:
                avl_id = f"AVL-{availability_id_counter}"
                availability_id_counter += 1
                w_type = "Night Corridor Gap" if dur >= 180 else "Natural Train Gap"

                cursor.execute("""
                    INSERT INTO Corridor_Availability (
                        availability_id, track_id, available_date, window_start, window_end,
                        duration_mins, window_type, consumed_mins
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    avl_id,
                    track_id,
                    run_date,
                    current_time.strftime("%Y-%m-%d %H:%M"),
                    day_end.strftime("%Y-%m-%d %H:%M"),
                    dur,
                    w_type
                ))
                avail_count += 1

    print(f"-> Calculated {avail_count} non-null corridor availability windows from train schedules.")


def generate_large_dataset(db_path=None):
    """Generates authentic railway data spanning TMS, SMMS, TDMS, COA Passenger & Goods schedules."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if db_path is None:
        db_path = os.path.join(base_dir, "railway_planning.db")

    try:
        from createdata import init_db
    except ImportError:
        try:
            from database.createdata import init_db
        except ImportError:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from createdata import init_db

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # High-density railway corridors
    routes = [
        ("NDLS", "CNB", "Golden Quadrilateral (GQ)", 160, 58.5),
        ("CNB", "PRYJ", "Golden Quadrilateral (GQ)", 160, 54.2),
        ("PRYJ", "DDU", "High Density Network (HDN)", 130, 62.1),
        ("DDU", "GAYA", "High Density Network (HDN)", 130, 48.0),
        ("GAYA", "DHN", "Trunk Route A", 130, 42.0),
        ("DHN", "HWH", "High Density Network (HDN)", 130, 55.4),
        ("CSMT", "KYN", "High Density Network (HDN)", 110, 65.0),
        ("KYN", "IGP", "Trunk Route A", 110, 38.2),
        ("IGP", "BSL", "Golden Quadrilateral (GQ)", 130, 49.8),
        ("BSL", "NGP", "Golden Quadrilateral (GQ)", 130, 52.0),
        ("NGP", "BPQ", "High Density Network (HDN)", 130, 44.5),
        ("BPQ", "KZJ", "High Density Network (HDN)", 130, 47.1),
        ("KZJ", "SC", "Trunk Route A", 130, 41.0),
        ("MAS", "GDR", "Golden Quadrilateral (GQ)", 130, 46.0),
        ("GDR", "BZA", "High Density Network (HDN)", 130, 58.0),
        ("BZA", "VSKP", "High Density Network (HDN)", 130, 51.5),
        ("SBC", "JTJ", "Trunk Route A", 110, 34.0),
        ("BCT", "ST", "Golden Quadrilateral (GQ)", 160, 59.0),
        ("ST", "BRC", "Golden Quadrilateral (GQ)", 160, 56.5),
        ("BRC", "ADI", "Golden Quadrilateral (GQ)", 160, 53.0),
        ("ADI", "ABR", "Trunk Route A", 110, 32.0),
        ("JP", "RE", "Trunk Route A", 110, 28.5),
        ("BPL", "JHS", "High Density Network (HDN)", 130, 48.5),
        ("JHS", "GWL", "Golden Quadrilateral (GQ)", 160, 50.2),
        ("GWL", "AGC", "Golden Quadrilateral (GQ)", 160, 52.8)
    ]

    criticalities = ["Critical", "High", "Medium", "Low"]
    crit_weights = [15, 35, 35, 15]

    base_date = datetime.now().date()
    print("Populating multi-department Indian Railways infrastructure dataset...")

    # 1. Populate Tracks
    track_ids = []
    for i, (st1, st2, r_class, max_spd, gmt) in enumerate(routes, start=1):
        t_id = f"TRK-{100 + i}"
        track_ids.append(t_id)
        sec_name = f"{st1}-{st2} Corridor Main Line-{random.choice(['UP', 'DN'])}"
        age = random.randint(3, 28)
        last_insp_offset = random.randint(3, 90)
        last_insp = (base_date - timedelta(days=last_insp_offset)).strftime("%Y-%m-%d")
        crit = random.choices(criticalities, weights=crit_weights)[0]
        sig_type = "Electronic Interlocking / MSDAC" if r_class.startswith("Golden") else "Panel Interlocking"

        cursor.execute("""
            INSERT OR REPLACE INTO Tracks (
                track_id, section_name, start_station, end_station,
                route_class, track_age, speed_limit_kmh, gmt_tonnage,
                last_inspected_date, criticality_level, electrified, signaling_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (t_id, sec_name, st1, st2, r_class, age, max_spd, gmt, last_insp, crit, sig_type))

    print(f"-> Created {len(track_ids)} corridor track sections with route assets.")

    # 2. Populate Trains (Passenger Timetable & COA Goods Trains Forecast spanning 30 days)
    passenger_trains = [
        ("22436", "Vande Bharat Express", "Passenger Premium", 1, 0),
        ("12301", "Howrah Rajdhani Express", "Passenger Premium", 1, 0),
        ("12004", "Lucknow Shatabdi", "Passenger Premium", 1, 0),
        ("12260", "Sealdah Duronto", "Passenger Express", 2, 15),
        ("12616", "Grand Trunk Express", "Passenger Express", 2, 20),
        ("12724", "Telangana Express", "Passenger Express", 2, 20),
        ("12840", "Howrah Mail", "Passenger Express", 2, 20),
        ("12952", "Mumbai Rajdhani", "Passenger Premium", 1, 0),
        ("20805", "Andhra Pradesh Express", "Passenger Express", 2, 20),
        ("12138", "Punjab Mail", "Passenger Express", 2, 30),
    ]

    goods_trains = [
        ("G-COAL-101", "BOXN Coal Rake (Thermal Plant)", "Goods Forecast - Coal", 3, 90),
        ("G-COAL-102", "BOBRN Hopper Coal (NTPC)", "Goods Forecast - Coal", 3, 90),
        ("G-CONT-201", "BLC Container Freight (CONCOR)", "Goods Forecast - Container", 3, 60),
        ("G-CONT-202", "Double Stack Container", "Goods Forecast - Container", 3, 60),
        ("G-TANK-301", "BTPN Petroleum Rake (IOCL)", "Goods Forecast - POL", 3, 75),
        ("G-STEL-401", "BFNS Steel Coil Rake (SAIL)", "Goods Forecast - Steel", 4, 120),
        ("G-GRAIN-501", "BCN Foodgrain Special (FCI)", "Goods Forecast - General", 4, 120),
        ("G-CEMT-601", "BCX Cement Special", "Goods Forecast - General", 4, 120)
    ]

    train_counter = 1
    total_train_runs = 0

    # 30-day horizon to support both Weekly (days 0-6) and Monthly (days 0-29) planning
    for day_offset in range(30):
        current_run_date = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")

        for t_id in track_ids:
            # 2 to 4 passenger trains per track per day
            p_sample = random.sample(passenger_trains, k=random.randint(2, 3))
            # 1 to 2 goods freight forecast trains per track per day
            g_sample = random.sample(goods_trains, k=random.randint(1, 2))
            daily_trains = p_sample + g_sample

            # Schedule without immediate overlapping collisions
            start_hour = 1
            for t_num, t_name, t_type, tier, flex in daily_trains:
                arr_hour = (start_hour + random.randint(1, 4)) % 22
                arr_min = random.choice([0, 15, 30, 45])
                enter_dt = datetime.strptime(f"{arr_hour:02d}:{arr_min:02d}", "%H:%M")
                dur = random.choice([35, 45, 60, 75])
                leave_dt = enter_dt + timedelta(minutes=dur)

                tr_instance_id = f"TRN-{train_counter}"
                train_counter += 1

                cursor.execute("""
                    INSERT OR REPLACE INTO Trains (
                        train_id, train_number, train_name, train_type,
                        track_id, run_date, scheduled_arrival, scheduled_departure,
                        priority_tier, flexibility_mins
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tr_instance_id, t_num, t_name, t_type,
                    t_id, current_run_date,
                    enter_dt.strftime("%H:%M"), leave_dt.strftime("%H:%M"),
                    tier, flex
                ))
                total_train_runs += 1
                start_hour = (arr_hour + 3) % 22

    print(f"-> Created {total_train_runs} train schedules (Passenger + COA Goods Forecast) across 30 days.")

    # 3. Calculate free corridor windows based on train gaps
    calculate_availability_for_corridors(cursor)

    # 4. Integrated Multi-Department Maintenance Backlog (TMS, SMMS, TDMS)
    # TMS (Engineering / P-Way) tasks
    tms_tasks = [
        ("Rail Grinding by RGM Machine", "Preventive Overhaul", 180, 0, 1, 0),
        ("Ultrasonic Flaw Defect (USFD) Removal", "Defect Rectification", 90, 0, 1, 30),
        ("Turnout Diamond Crossing Sleeper Tamping", "Defect Rectification", 120, 0, 1, 45),
        ("Ballast Cleaning Machine (BCM) Deep Screening", "Preventive Overhaul", 240, 1, 1, 30),
        ("Thermit Weld Peak Defect Rectification", "Defect Rectification", 75, 0, 1, 50),
        ("Track Relaying Machine (TRT) Panel Renewal", "Preventive Overhaul", 210, 1, 1, 30),
        ("Rail Joint Fishplate & Glued Joint Replacement", "Defect Rectification", 60, 0, 1, 0)
    ]

    # TDMS (Traction Distribution / TRD) tasks
    tdms_tasks = [
        ("25kV OHE Cantilever & Insulator Overhaul", "Preventive Overhaul", 120, 1, 0, 0),
        ("OHE Neutral Section Contact Wire Replacement", "Defect Rectification", 150, 1, 1, 0),
        ("OHE Stagger & Height Laser Measurement Checking", "Overdue Cyclic Maintenance", 90, 1, 0, 0),
        ("Traction Sub-Station Isolator Switch Upkeep", "Preventive Overhaul", 60, 1, 0, 0),
        ("OHE Hot Spot Defect Rectification by Tower Wagon", "Defect Rectification", 75, 1, 0, 0),
        ("Mast Bond & Earth Continuity Verification", "Overdue Cyclic Maintenance", 45, 0, 0, 0)
    ]

    # SMMS (Signal & Telecom / S&T) tasks
    smms_tasks = [
        ("Electric Point Machine Detection & Motor Overhaul", "Defect Rectification", 90, 0, 1, 30),
        ("Multi-Section Digital Axle Counter (MSDAC) Reset", "Defect Rectification", 60, 0, 0, 0),
        ("Audio Frequency Track Circuit (AFTC) Tuning", "Overdue Cyclic Maintenance", 75, 0, 0, 0),
        ("Electronic Interlocking (EI) Standby Changeover", "Preventive Overhaul", 60, 0, 0, 0),
        ("Signaling Cable Meggering & Earth Fault Repair", "Defect Rectification", 105, 0, 0, 0),
        ("Interlocked Level Crossing Gate Warning System Test", "Overdue Cyclic Maintenance", 45, 0, 0, 0)
    ]

    severities = ["Critical", "High", "Medium", "Low"]
    sev_weights = [20, 35, 30, 15]

    job_counter = 1001
    all_jobs = []

    # Generate 110 maintenance jobs
    for i in range(110):
        j_id = f"JOB-{job_counter}"
        job_counter += 1
        t_id = random.choice(track_ids)

        dept_choice = random.choices(["Engineering (P-Way)", "Traction Distribution (TRD)", "Signal & Telecom (S&T)"], weights=[40, 30, 30])[0]
        if dept_choice == "Engineering (P-Way)":
            src = "TMS"
            task_info = random.choice(tms_tasks)
        elif dept_choice == "Traction Distribution (TRD)":
            src = "TDMS"
            task_info = random.choice(tdms_tasks)
        else:
            src = "SMMS"
            task_info = random.choice(smms_tasks)

        task_name, m_type, duration, power_req, traffic_req, default_psr = task_info
        sev = random.choices(severities, weights=sev_weights)[0]

        # Critical jobs are more likely overdue and have speed restrictions
        if sev == "Critical":
            overdue_days = random.randint(5, 28)
            psr = default_psr if default_psr > 0 else random.choice([30, 45])
            horizon = "Weekly"
        elif sev == "High":
            overdue_days = random.randint(0, 14)
            psr = default_psr
            horizon = "Weekly" if random.random() < 0.75 else "Monthly"
        else:
            overdue_days = random.randint(0, 7)
            psr = 0
            horizon = "Weekly" if random.random() < 0.4 else "Monthly"

        req_offset = random.randint(1, 10)
        req_date = (base_date - timedelta(days=req_offset)).strftime("%Y-%m-%d")
        
        # Weekly deadlines are within 7 days, monthly up to 30 days
        deadline_offset = random.randint(2, 7) if horizon == "Weekly" else random.randint(8, 28)
        deadline = (base_date + timedelta(days=deadline_offset)).strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT OR REPLACE INTO Jobs (
                job_id, track_id, department, source_system, maintenance_type,
                task, defect_severity, overdue_days, speed_restriction_imposed,
                min_duration_needed, power_block_required, traffic_block_required,
                planning_horizon, request_date, deadline, ai_score,
                scheduled_start, scheduled_end, block_id, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, 'Pending')
        """, (
            j_id, t_id, dept_choice, src, m_type,
            task_name, sev, overdue_days, psr,
            duration, power_req, traffic_req,
            horizon, req_date, deadline
        ))
        all_jobs.append((j_id, t_id, dept_choice, src, duration, horizon))

    print(f"-> Created {len(all_jobs)} integrated maintenance work orders from TMS, SMMS, and TDMS.")

    # 5. Clear old block registers
    cursor.execute("DELETE FROM Block_Jobs;")
    cursor.execute("DELETE FROM Block_Register;")

    conn.commit()
    conn.close()
    print("-> Database population complete: railway_planning.db is primed and ready.")

if __name__ == "__main__":
    generate_large_dataset()