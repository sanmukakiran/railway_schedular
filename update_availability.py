import os
import sqlite3
from datetime import datetime

def calculate_availability_from_train_schedules(db_path=None):
    """Calculates non-overlapping free time windows between train schedules."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    if db_path is None:
        db_path = os.path.join(base_dir, "railway_planning.db")
        if not os.path.exists(db_path):
            db_path = os.path.join(base_dir, "database", "railway_planning.db")

    if not os.path.exists(db_path):
        print(f"Error: Could not find railway_planning.db at '{db_path}'")
        return

    print(f"Connecting to database at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Clear old placeholder availability records
    cursor.execute("DELETE FROM Corridor_Availability;")

    # 2. Get all track and date pairs present in Trains
    cursor.execute("SELECT DISTINCT track_id, run_date FROM Trains ORDER BY run_date, track_id;")
    corridor_days = cursor.fetchall()

    availability_id_counter = 501
    inserted_count = 0

    for track_id, run_date in corridor_days:
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
                if start <= merged_intervals[-1][1]:
                    merged_intervals[-1][1] = max(merged_intervals[-1][1], end)
                else:
                    merged_intervals.append([start, end, t_type])

        # 3. Calculate unreserved time gaps between train slots
        current_pointer = datetime.strptime(f"{run_date} 00:00", "%Y-%m-%d %H:%M")
        day_end = datetime.strptime(f"{run_date} 23:59", "%Y-%m-%d %H:%M")

        for start, end, _ in merged_intervals:
            if start > current_pointer:
                dur = int((start - current_pointer).total_seconds() / 60)
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
                        current_pointer.strftime("%Y-%m-%d %H:%M"),
                        start.strftime("%Y-%m-%d %H:%M"),
                        dur,
                        w_type
                    ))
                    inserted_count += 1

            current_pointer = max(current_pointer, end)

        # Remaining gap from last train departure to midnight
        if current_pointer < day_end:
            dur = int((day_end - current_pointer).total_seconds() / 60)
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
                    current_pointer.strftime("%Y-%m-%d %H:%M"),
                    day_end.strftime("%Y-%m-%d %H:%M"),
                    dur,
                    w_type
                ))
                inserted_count += 1

    conn.commit()
    conn.close()
    print(f"[OK] Successfully calculated {inserted_count} real availability windows from train schedules!")

if __name__ == "__main__":
    calculate_availability_from_train_schedules()