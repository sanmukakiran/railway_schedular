
import sqlite3
print("Waking up the Scoring Engine...\n")
conn=sqlite3.connect("database\\railway_planning.db")
cursor=conn.cursor()
cursor.execute('''
    SELECT
        Jobs.job_id,Jobs.defect_severity,
        Tracks.track_age,Tracks.criticality_level
    FROM Jobs
    JOIN Tracks ON Jobs.track_id=Tracks.track_id
    where Jobs.ai_score IS NULL



''')
unscored_jobs=cursor.fetchall()
print(f"Found {len(unscored_jobs)} jobs that need AI scoring.\n")
for job in unscored_jobs:
    job_id=job[0]
    defect_severity=job[1]
    track_age=job[2]
    track_criticality=job[3]

    score=0


    if defect_severity=="Critical":
        score=score+50
    elif defect_severity=="High":
        score=score+35
    elif defect_severity=="Medium":
        score=score+20
    else:
        score=score+10

    if track_age>20:
        score=score+25
    elif track_age>10:
        score=score+15
    else:
        score=score+5

    if track_criticality=="Critical":
        score=score+25
    elif track_criticality=="High":
        score=score+15
    else:
        score=score+5


    final_score=min(score,100)
    cursor.execute("UPDATE Jobs SET ai_score=? WHERE job_id=?",(final_score,job_id))
    print(f"✅ Scored {job_id}: {final_score}/100")
conn.commit()
conn.close()
print("\n All jobs have been successfully scored! The database is ready for scheduling.")
