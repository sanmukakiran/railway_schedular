import os
import sqlite3
from datetime import datetime, timedelta
from ai_scorer import run_scoring_engine

def run_scheduler(db_path=None, horizon="All"):
    """
    Automatic Coordinated Multi-Department Block Optimizer:
    1. Prioritizes jobs using AI priority scores.
    2. Identifies matching corridor availability windows based on train timetables.
    3. Consolidates compatible tasks from TMS, SMMS, and TDMS into joint 'Shadow Blocks'.
    4. Tracks corridor downtime saved and coordinates OHE power disconnections.
    5. Supports Weekly (7-day) and Monthly (30-day) planning horizons.
    """
    print("=" * 60)
    print("STARTING AI COORDINATED BLOCK OPTIMIZER")
    print(f"Planning Horizon Filter: {horizon}")
    print("=" * 60 + "\n")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if db_path is None:
        db_path = os.path.join(base_dir, "railway_planning.db")
        if not os.path.exists(db_path):
            db_path = os.path.join(base_dir, "database", "railway_planning.db")

    if not os.path.exists(db_path):
        print(f"Error: Could not find database at '{db_path}'")
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ensure all pending jobs have AI scores
    cursor.execute("SELECT COUNT(*) FROM Jobs WHERE (status IS NULL OR status = 'Pending') AND ai_score IS NULL")
    if cursor.fetchone()[0] > 0:
        print("Scoring unscored jobs prior to optimization...")
        run_scoring_engine(db_path=db_path)

    blocks_created = 0
    total_jobs_scheduled = 0
    total_downtime_saved_mins = 0
    block_counter = 1

    # Base date from current database schedules
    cursor.execute("SELECT MIN(available_date) FROM Corridor_Availability")
    min_date_row = cursor.fetchone()
    base_date = datetime.strptime(min_date_row[0], "%Y-%m-%d").date() if min_date_row and min_date_row[0] else datetime.now().date()
    weekly_limit_date = (base_date + timedelta(days=7)).strftime("%Y-%m-%d")

    while True:
        # Fetch highest-priority pending job matching horizon criteria
        query = """
            SELECT job_id, track_id, min_duration_needed, task, department, 
                   source_system, defect_severity, overdue_days, power_block_required,
                   planning_horizon, ai_score
            FROM Jobs
            WHERE status IS NULL OR status = 'Pending'
        """
        params = []
        if horizon in ("Weekly", "Monthly"):
            query += " AND planning_horizon = ?"
            params.append(horizon)

        query += " ORDER BY ai_score DESC LIMIT 1"
        cursor.execute(query, params)
        top_job = cursor.fetchone()

        if not top_job:
            print("[INFO] No further pending jobs match the optimization criteria.")
            break

        (main_job_id, target_track, needed_time, task_name, dept, 
         source_sys, severity, overdue, power_req, job_horizon, score) = top_job

        print(f"\n[TARGET] {main_job_id} | {source_sys} ({dept}) | {task_name}")
        print(f"         Track: {target_track} | AI Priority: {score}/100 | Duration: {needed_time}m | Horizon: {job_horizon}")

        # Fetch candidate availability windows on the target track
        avail_query = """
            SELECT availability_id, available_date, window_start, window_end, duration_mins, window_type
            FROM Corridor_Availability
            WHERE track_id = ?
        """
        avail_params = [target_track]

        if job_horizon == "Weekly" or horizon == "Weekly":
            avail_query += " AND available_date <= ?"
            avail_params.append(weekly_limit_date)

        avail_query += " ORDER BY available_date ASC, window_start ASC"
        cursor.execute(avail_query, avail_params)
        candidate_windows = cursor.fetchall()

        selected_window = None
        for avl_id, avl_date, w_start, w_end, dur_mins, w_type in candidate_windows:
            start_dt = datetime.strptime(w_start, "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(w_end, "%Y-%m-%d %H:%M")
            actual_mins = int((end_dt - start_dt).total_seconds() / 60)

            if actual_mins >= needed_time:
                selected_window = (avl_id, avl_date, w_start, w_end, actual_mins, w_type)
                break

        # Handle shortage of natural window
        if not selected_window:
            print(f"  [REGULATION NEEDED] No open corridor window >= {needed_time}m for {target_track}.")
            print(f"  -> Flagging {main_job_id} as 'Delayed' for COA Freight Regulation.")
            cursor.execute("UPDATE Jobs SET status = 'Delayed' WHERE job_id = ?", (main_job_id,))
            conn.commit()
            continue

        avl_id, avl_date, block_start, block_end, total_window_time, w_type = selected_window
        print(f"  [WINDOW GRANTED] {avl_id} on {avl_date}: {block_start} to {block_end} ({total_window_time}m free, {w_type})")

        # MULTI-DEPARTMENT SHADOW BLOCK BUNDLING
        # Search for pending jobs on the same track across TMS, SMMS, and TDMS
        other_query = """
            SELECT job_id, task, department, source_system, min_duration_needed, power_block_required, ai_score
            FROM Jobs
            WHERE track_id = ? AND job_id != ? AND (status IS NULL OR status = 'Pending')
        """
        other_params = [target_track, main_job_id]
        if job_horizon == "Weekly" or horizon == "Weekly":
            other_query += " AND planning_horizon = 'Weekly'"

        other_query += " ORDER BY ai_score DESC"
        cursor.execute(other_query, other_params)
        candidate_companion_jobs = cursor.fetchall()

        # Group and consolidate: tasks from different departments can run in parallel (overlap)
        # up to the granted block duration, or sequential small tasks that fit
        bundled_jobs = []
        max_duration_used = needed_time
        total_independent_time = needed_time
        departments_set = {f"{source_sys} ({dept})"}
        power_isolation_needed = bool(power_req)

        for c_id, c_task, c_dept, c_src, c_dur, c_power, c_score in candidate_companion_jobs:
            dept_key = f"{c_src} ({c_dept})"

            # If the companion job is from a different department, it can execute concurrently (Shadow Block)!
            if dept_key not in departments_set:
                effective_duration = max(max_duration_used, c_dur)
                if effective_duration <= total_window_time:
                    bundled_jobs.append((c_id, c_task, c_dept, c_src, c_dur, c_power))
                    departments_set.add(dept_key)
                    max_duration_used = effective_duration
                    total_independent_time += c_dur
                    if c_power:
                        power_isolation_needed = True
            else:
                # Same department sequential addition if space permits
                if max_duration_used + c_dur <= total_window_time:
                    bundled_jobs.append((c_id, c_task, c_dept, c_src, c_dur, c_power))
                    max_duration_used += c_dur
                    total_independent_time += c_dur
                    if c_power:
                        power_isolation_needed = True

        # Calculate exact possession start and end times
        start_dt = datetime.strptime(block_start, "%Y-%m-%d %H:%M")
        block_end_dt = datetime.strptime(block_end, "%Y-%m-%d %H:%M")
        actual_end_dt = start_dt + timedelta(minutes=max_duration_used)

        sched_start_str = start_dt.strftime("%Y-%m-%d %H:%M")
        sched_end_str = actual_end_dt.strftime("%Y-%m-%d %H:%M")

        # Downtime saved through multi-department consolidation
        downtime_saved = max(0, total_independent_time - max_duration_used)
        total_downtime_saved_mins += downtime_saved

        new_block_id = f"BLK-{datetime.strptime(avl_date, '%Y-%m-%d').strftime('%y%m%d')}-{block_counter:03d}"
        block_counter += 1
        depts_str = ", ".join(sorted(list(departments_set)))
        total_tasks_in_block = 1 + len(bundled_jobs)

        # Commit to Block_Register
        cursor.execute("""
            INSERT OR REPLACE INTO Block_Register (
                block_id, track_id, window_start, window_end, duration_mins,
                total_departments_involved, departments_list, tasks_count,
                power_block_granted, corridor_downtime_saved_mins, planning_horizon, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Approved')
        """, (
            new_block_id, target_track, sched_start_str, sched_end_str, max_duration_used,
            len(departments_set), depts_str, total_tasks_in_block,
            1 if power_isolation_needed else 0, downtime_saved, job_horizon
        ))

        # Link and schedule primary job
        cursor.execute("INSERT OR REPLACE INTO Block_Jobs (block_id, job_id) VALUES (?, ?)", (new_block_id, main_job_id))
        cursor.execute("""
            UPDATE Jobs 
            SET status = 'Scheduled', scheduled_start = ?, scheduled_end = ?, block_id = ?
            WHERE job_id = ?
        """, (sched_start_str, sched_end_str, new_block_id, main_job_id))
        total_jobs_scheduled += 1

        print(f"  [CONSOLIDATED SHADOW BLOCK] Created {new_block_id}")
        print(f"  -> Departments: {depts_str}")
        print(f"  -> Tasks: {total_tasks_in_block} jobs | Block Time: {max_duration_used}m | Downtime Saved: {downtime_saved}m")

        # Link and schedule bundled companion jobs
        for bj in bundled_jobs:
            bj_id, bj_task, bj_dept, bj_src, bj_dur, bj_power = bj
            cursor.execute("INSERT OR REPLACE INTO Block_Jobs (block_id, job_id) VALUES (?, ?)", (new_block_id, bj_id))
            cursor.execute("""
                UPDATE Jobs 
                SET status = 'Scheduled', scheduled_start = ?, scheduled_end = ?, block_id = ?
                WHERE job_id = ?
            """, (sched_start_str, sched_end_str, new_block_id, bj_id))
            total_jobs_scheduled += 1
            print(f"     + Coordinated: {bj_id} [{bj_src}] {bj_task} ({bj_dur}m)")

        # Update remaining corridor availability
        if actual_end_dt < block_end_dt:
            rem_dur = int((block_end_dt - actual_end_dt).total_seconds() / 60)
            if rem_dur >= 30:
                cursor.execute("""
                    UPDATE Corridor_Availability 
                    SET window_start = ?, duration_mins = ?, consumed_mins = consumed_mins + ?
                    WHERE availability_id = ?
                """, (sched_end_str, rem_dur, max_duration_used, avl_id))
            else:
                cursor.execute("DELETE FROM Corridor_Availability WHERE availability_id = ?", (avl_id,))
        else:
            cursor.execute("DELETE FROM Corridor_Availability WHERE availability_id = ?", (avl_id,))

        conn.commit()
        blocks_created += 1

    conn.close()
    print("\n" + "=" * 60)
    print("COORDINATED OPTIMIZATION SUMMARY:")
    print(f"  Total Coordinated Blocks Created : {blocks_created}")
    print(f"  Total Maintenance Jobs Scheduled : {total_jobs_scheduled}")
    print(f"  Corridor Downtime Saved          : {total_downtime_saved_mins} mins ({round(total_downtime_saved_mins/60, 1)} hours)")
    print("=" * 60 + "\n")
    return blocks_created

if __name__ == "__main__":
    run_scheduler()