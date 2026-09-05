
import sqlite3
print("Waking up the Scheduler...\n")
conn=sqlite3.connect("database/railway_planning.db")
cursor=conn.cursor()

while True:
    cursor.execute('''
        SELECT job_id, track_id, min_duration_needed, task, department, ai_score
        FROM Jobs
        WHERE status IS NULL OR status = 'Pending'
        ORDER BY ai_score DESC
        LIMIT 1
    ''')
    top_job=cursor.fetchone()

    if not top_job:
        print("All tracks are perfectly maintained! No pending jobs found.")
        break
    else:
        main_job_id,target_track,needed_time,task_name,dept,score=top_job
        print(f"EMERGENCY TARGET ACQUIRED: {main_job_id} ({task_name})")
        print(f"   Track: {target_track} | AI Score: {score}/100 | Dept: {dept}")
        cursor.execute('''
            SELECT availability_id,window_start,window_end
            FROM Corridor_Availability
            WHERE track_id=?
            LIMIT 1
    ''',(target_track,))
        window=cursor.fetchone()
        if not window:
            print(f"No empty gaps found for {target_track}. A train delay is required!")
            cursor.execute("UPDATE Jobs SET status = 'Delayed' WHERE job_id = ?", (main_job_id,))
            conn.commit()
            continue
        else:
            avail_id,block_start,block_end=window
            print(f"Found natural empty window: {block_start} to {block_end}")
            cursor.execute('''
                SELECT job_id, task, department FROM Jobs
                WHERE track_id = ? AND job_id != ? AND (status IS NULL OR status = 'Pending')
            ''', (target_track, main_job_id))
            other_jobs = cursor.fetchall()

            new_block_id = f"BLK-AI-{main_job_id[-4:]}"
            total_depts = 1 + len(other_jobs)
            cursor.execute('''
                INSERT INTO Block_Register (block_id, track_id, window_start, window_end, total_departments_involved)
                VALUES (?, ?, ?, ?, ?)
            ''', (new_block_id, target_track, block_start, block_end, total_depts))
            cursor.execute("INSERT INTO Block_Jobs (block_id, job_id) VALUES (?, ?)", (new_block_id, main_job_id))
            cursor.execute("UPDATE Jobs SET status = 'Scheduled' WHERE job_id = ?", (main_job_id,))

            print(f"Executing Shadow Block... Bundling {len(other_jobs)} additional jobs!")
            for oj in other_jobs:
                oj_id, oj_task, oj_dept = oj
                cursor.execute("INSERT INTO Block_Jobs (block_id, job_id) VALUES (?, ?)", (new_block_id, oj_id))
                cursor.execute("UPDATE Jobs SET status = 'Scheduled' WHERE job_id = ?", (oj_id,))
                print(f"   + Bundled: {oj_id} ({oj_task} - {oj_dept})")


            conn.commit()
            print(f"\n SUCCESS: {new_block_id} permanently saved to the database.")    
conn.close()