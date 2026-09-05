import os
import sqlite3
import numpy as np

def compute_priority_score(defect_severity, overdue_days, route_class, track_age, 
                           gmt_tonnage, track_criticality, psr_kmh, source_system):
    """
    Computes a multi-factorial AI Priority Score (0-100) based on:
    1. Safety & Defect Severity Risk (Max 30 pts)
    2. Overdue Urgency & Statutory Degradation (Max 25 pts)
    3. Route Classification & Asset Tonnage / Age (Max 20 pts)
    4. Operational Capacity Impact / Speed Restriction Penalty (Max 15 pts)
    5. Statutory Departmental Compliance (Max 10 pts)
    """
    score = 0.0
    breakdown = {}

    # 1. Defect Severity Score
    if defect_severity == "Critical":
        sev_score = 30.0
    elif defect_severity == "High":
        sev_score = 20.0
    elif defect_severity == "Medium":
        sev_score = 12.0
    else:
        sev_score = 5.0
    score += sev_score
    breakdown["severity_risk"] = sev_score

    # 2. Overdue Days Urgency
    if overdue_days > 20:
        overdue_score = 25.0
    elif overdue_days > 10:
        overdue_score = 18.0
    elif overdue_days > 0:
        overdue_score = 10.0 + (overdue_days * 0.7)
    else:
        overdue_score = 4.0
    score += overdue_score
    breakdown["overdue_urgency"] = overdue_score

    # 3. Route & Asset Criticality
    route_score = 0.0
    if "Golden Quadrilateral" in str(route_class):
        route_score += 10.0
    elif "High Density Network" in str(route_class):
        route_score += 8.0
    else:
        route_score += 5.0

    if track_criticality == "Critical":
        route_score += 6.0
    elif track_criticality == "High":
        route_score += 4.0
    else:
        route_score += 2.0

    # High tonnage / track age wear multiplier
    if (gmt_tonnage or 0) > 50:
        route_score += 2.5
    if (track_age or 0) > 15:
        route_score += 1.5
    route_score = min(route_score, 20.0)
    score += route_score
    breakdown["route_criticality"] = route_score

    # 4. Operational Bottleneck / Speed Restriction (PSR)
    psr_score = 0.0
    if psr_kmh and psr_kmh > 0:
        if psr_kmh <= 30:
            psr_score = 15.0  # Severe bottleneck: trains slowed to 30 km/h
        elif psr_kmh <= 45:
            psr_score = 11.0
        else:
            psr_score = 7.0
    else:
        psr_score = 2.0
    score += psr_score
    breakdown["capacity_impact"] = psr_score

    # 5. Departmental Source Compliance
    dept_score = 0.0
    if source_system == "TMS":
        dept_score = 10.0  # Civil/Track structural integrity & derailment prevention
    elif source_system == "TDMS":
        dept_score = 9.0   # 25kV OHE power trip prevention
    elif source_system == "SMMS":
        dept_score = 9.5   # Electronic Interlocking & signal failure prevention
    else:
        dept_score = 7.0
    score += dept_score
    breakdown["compliance"] = dept_score

    final_score = round(min(max(score, 5.0), 100.0), 1)
    return final_score, breakdown


def run_scoring_engine(db_path=None, score_all=False):
    """Calculates and persists AI priority scores for maintenance work orders."""
    print("Waking up the AI Prioritization Engine...\n")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if db_path is None:
        db_path = os.path.join(base_dir, "railway_planning.db")
        if not os.path.exists(db_path):
            db_path = os.path.join(base_dir, "database", "railway_planning.db")

    if not os.path.exists(db_path):
        print(f"Error: Database not found at '{db_path}'")
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = '''
        SELECT
            Jobs.job_id,
            Jobs.defect_severity,
            Jobs.overdue_days,
            Tracks.route_class,
            Tracks.track_age,
            Tracks.gmt_tonnage,
            Tracks.criticality_level,
            Jobs.speed_restriction_imposed,
            Jobs.source_system
        FROM Jobs
        JOIN Tracks ON Jobs.track_id = Tracks.track_id
    '''
    if not score_all:
        query += " WHERE Jobs.ai_score IS NULL"

    cursor.execute(query)
    jobs_to_score = cursor.fetchall()
    print(f"Found {len(jobs_to_score)} jobs to prioritize with AI algorithms.\n")

    scored_count = 0
    for job in jobs_to_score:
        (job_id, defect_sev, overdue, route_cls, age, gmt, 
         track_crit, psr, src) = job

        final_score, breakdown = compute_priority_score(
            defect_sev, overdue, route_cls, age, gmt, track_crit, psr, src
        )

        cursor.execute("UPDATE Jobs SET ai_score = ? WHERE job_id = ?", (final_score, job_id))
        scored_count += 1
        print(f"  [AI SCORE] {job_id} ({src}) -> {final_score}/100 [Sev:{breakdown['severity_risk']}, Overdue:{breakdown['overdue_urgency']}, Cap:{breakdown['capacity_impact']}]")

    conn.commit()
    conn.close()
    print(f"\n[OK] Prioritization complete! {scored_count} jobs scored and prioritized.")
    return scored_count

if __name__ == "__main__":
    run_scoring_engine(score_all=True)