import os
import sqlite3
import random
from datetime import datetime, timedelta

def generate_large_dataset():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "railway_planning.db")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    stations = [
        "NDLS", "CNB", "PRYJ", "DDU", "BSB", "PNBE", "HWH", 
        "BCT", "CSMT", "PUNE", "NGP", "BPQ", "SC", "HYB", 
        "MAS", "SBC", "GHY", "ADI", "JP", "BPL", "JHS"
    ]
    criticalities = ["Low", "Medium", "High", "Critical"]
    severities = ["Low", "Medium", "High", "Critical"]
    departments = ["Engineering", "Electrical", "S&T", "Traffic"]

    dept_tasks = {
        "Engineering": [
            "Rail Grinding", "Sleeper Replacement", "Ballast Cleaning", 
            "Track Relaying", "Deep Screening", "Weld Inspection"
        ],
        "Electrical": [
            "OHE Inspection", "Cantilever Adjustment", "Traction Feeder Upkeep", 
            "Neutral Section Check", "Contact Wire Replacement"
        ],
        "S&T": [
            "Track Circuit Testing", "Point Machine Replacement", 
            "Axle Counter Calibration", "Signaling Cable Relaying", "Interlocking Test"
        ],
        "Traffic": [
            "Level Crossing Repair", "Platform Line Re-gauging", 
            "Yard Marshalling Line Upkeep"
        ]
    }

    train_names = [
        "Vande Bharat Express", "Rajdhani Express", "Shatabdi Express",
        "Duronto Express", "Garib Rath Express", "Sampark Kranti",
        "Telangana Express", "Karnataka Express", "Tamil Nadu Express",
        "Grand Trunk Express", "Coromandel Express", "Gitanjali Express",
        "Howrah Mail", "Netaji Express", "Deccan Queen", "Goa Express",
        "Konark Express", "Ganga Kaveri Express", "Charminar Express"
    ]

    day_patterns = [
        "Daily", "Daily", "Daily", 
        "Mon,Wed,Fri", "Tue,Thu,Sat", 
        "Sat,Sun", "Mon,Fri"
    ]

    base_date = datetime.now().date()

    print("Populating extended railway dataset...")


    track_ids = []
    for i in range(1, 26):
        t_id = f"TRK-{100 + i}"
        track_ids.append(t_id)
        st1, st2 = random.sample(stations, 2)
        sec_name = f"{st1}-{st2} Corridor Line-{random.choice(['UP', 'DOWN', 'SL'])}"
        age = random.randint(2, 35)
        last_insp_offset = random.randint(5, 180)
        last_insp = (base_date - timedelta(days=last_insp_offset)).strftime("%Y-%m-%d")
        crit = random.choices(criticalities, weights=[20, 40, 30, 10])[0]

        cursor.execute("""
            INSERT OR REPLACE INTO Tracks (
                track_id, section_name, start_station, end_station,
                track_age, last_inspected_date, criticality_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (t_id, sec_name, st1, st2, age, last_insp, crit))

    print(f"-> Created {len(track_ids)} tracks.")

    train_counter = 12001
    train_entries = 0
    for day_offset in range(7):
        current_run_date = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")

        for t_id in track_ids:
            # 1 to 4 trains passing per track on each calendar date
            trains_on_track = random.randint(1, 4)
            for _ in range(trains_on_track):
                tr_id = str(train_counter)
                train_counter += 1
                tr_name = random.choice(train_names)
                ops_days = random.choice(day_patterns)

                # Generate non-overlapping realistic entry/leave windows
                arr_hour = random.randint(0, 21)
                arr_min = random.choice([0, 15, 30, 45])
                enter_dt = datetime.strptime(f"{arr_hour:02d}:{arr_min:02d}", "%H:%M")
                duration = random.choice([30, 45, 60, 90, 120])
                leave_dt = enter_dt + timedelta(minutes=duration)

                cursor.execute("""
                    INSERT OR REPLACE INTO Trains (
                        train_id, train_name, track_id, days_of_operation,
                        run_date, scheduled_arrival, scheduled_departure
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    tr_id, tr_name, t_id, ops_days,
                    current_run_date,
                    enter_dt.strftime("%H:%M"),
                    leave_dt.strftime("%H:%M")
                ))
                train_entries += 1

    print(f"-> Created {train_entries} train operations across a 7-day planning window.")

    job_ids = []
    for i in range(1, 66):
        j_id = f"JOB-{1000 + i}"
        job_ids.append(j_id)
        t_id = random.choice(track_ids)
        dept = random.choice(departments)
        task = random.choice(dept_tasks[dept])
        min_dur = random.choice([30, 45, 60, 90, 120, 150])
        sev = random.choices(severities, weights=[25, 35, 25, 15])[0]
        
        req_offset = random.randint(0, 3)
        req_date = (base_date - timedelta(days=req_offset)).strftime("%Y-%m-%d")
        deadline_offset = random.randint(1, 7)
        deadline = (base_date + timedelta(days=deadline_offset)).strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT OR REPLACE INTO Jobs (
                job_id, track_id, department, task, min_duration_needed,
                defect_severity, request_date, deadline, ai_score,
                scheduled_start, scheduled_end, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 'Pending')
        """, (j_id, t_id, dept, task, min_dur, sev, req_date, deadline))

    print(f"-> Created {len(job_ids)} maintenance jobs in 'Pending' status.")

    avail_count = 0
    for i in range(1, 41):
        avl_id = f"AVL-{500 + i}"
        t_id = random.choice(track_ids)
        avl_date = (base_date + timedelta(days=random.randint(0, 4))).strftime("%Y-%m-%d")
        
        start_hour = random.choice([1, 10, 13, 23])
        end_hour = start_hour + random.randint(2, 4)
        
        win_start = f"{avl_date} {start_hour:02d}:00"
        win_end = f"{avl_date} {min(end_hour, 23):02d}:45"

        cursor.execute("""
            INSERT OR REPLACE INTO Corridor_Availability (
                availability_id, track_id, available_date, window_start, window_end
            ) VALUES (?, ?, ?, ?, ?)
        """, (avl_id, t_id, avl_date, win_start, win_end))
        avail_count += 1

    print(f"-> Created {avail_count} candidate free corridor availability windows.")


    for i in range(1, 6):
        b_id = f"BLK-{8000 + i}"
        t_id = track_ids[i]
        b_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        b_start = f"{b_date} 11:30"
        b_end = f"{b_date} 14:00"

        
        linked_jobs = job_ids[(i - 1) * 2 : (i - 1) * 2 + 2]

        cursor.execute("""
            INSERT OR REPLACE INTO Block_Register (
                block_id, track_id, window_start, window_end, total_departments_involved
            ) VALUES (?, ?, ?, ?, ?)
        """, (b_id, t_id, b_start, b_end, 2))

        for j in linked_jobs:
            cursor.execute("""
                INSERT OR REPLACE INTO Block_Jobs (block_id, job_id)
                VALUES (?, ?)
            """, (b_id, j))

            
            cursor.execute("""
                UPDATE Jobs 
                SET scheduled_start = ?, scheduled_end = ?, status = 'Scheduled', ai_score = ?
                WHERE job_id = ?
            """, (b_start, b_end, round(random.uniform(55.0, 88.0), 1), j))

    print("-> Created 5 committed blocks linked with 10 consolidated jobs in Block_Jobs.")

    conn.commit()
    conn.close()
    print("\nDatabase population finished successfully: railway_planning.db is ready.")

if __name__ == "__main__":
    generate_large_dataset()