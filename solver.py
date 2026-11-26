import json
import sys
from ortools.sat.python import cp_model

def solve_timetable(data):
    """
    Solves the university/school timetable problem using OR-Tools CP-SAT.
    
    Format: 6 days (Mon-Sat, index 0-5), 5 periods (index 0-4) per day = 30 slots.
    
    Constraints:
    1. Every class must have all 30 slots filled (no free hours).
    2. No staff member can teach multiple classes in the same slot (day, period).
    3. The total weekly hours for each subject in each class must equal the curriculum hours.
    4. The total weekly hours for each staff member must not exceed their working hour limit.
    5. UG Lab subjects (4 hours total) must be scheduled in 2 blocks of 2 consecutive hours on different days.
    6. PG Lab subjects (6 hours total) must be scheduled in 2 blocks of 3 consecutive hours on different days.
    7. Theory subjects (<= 6 hours total) must be scheduled for at most 1 hour per day.
    """
    model = cp_model.CpModel()
    
    days = list(range(6))
    periods = list(range(5))
    
    classes = data.get('classes', [])
    staffs = data.get('staffs', [])
    subjects = data.get('subjects', [])
    
    # Fast lookups
    staff_by_id = {s['id']: s for s in staffs}
    subject_by_code = {sub['code']: sub for sub in subjects}
    
    # Map subject codes to eligible staff IDs based on subjects list or department match
    subject_staff = {}
    for sub in subjects:
        code = sub['code']
        sub_dept = sub.get('department')
        eligible = [s['id'] for s in staffs if (code in s.get('subjects', []) or s.get('department') == sub_dept)]
        subject_staff[code] = eligible

    # Decision variables: X[class, day, period, subject, staff]
    X = {}
    class_vars = {}
    staff_vars = {}
    # class_subject_staff_vars: keyed by (c_name, sub_code, t_id) to track per-teacher hours
    class_subject_staff_vars = {}
    # class_subject_all_vars: keyed by (c_name, sub_code) for slot coverage - all eligible teachers
    class_subject_all_vars = {}
    split_3_3_vars = []
    class_lab_day_vars = { cl['name']: { d: [] for d in days } for cl in classes }
    staff_day_period_vars = {}
    
    # Build a set of (c_name, sub_code, t_id) tuples from syllabus items
    # so we know which teachers are allowed per subject per class
    syllabus_staff = {}  # (c_name, sub_code) -> list of allowed (t_id, hours) tuples
    for cl in classes:
        c_name = cl['name']
        seen = {}  # sub_code -> list of (t_id, hours)
        for item in cl['syllabus']:
            sub_code = item['subject_code']
            t_id = item.get('staff_id')
            hrs = item.get('hours', 0)
            if sub_code not in seen:
                seen[sub_code] = []
            if t_id and str(t_id) not in ('None', 'null', 'ST_DUMMY', ''):
                seen[sub_code].append((str(t_id), hrs))
            else:
                # Unassigned: use department fallback
                for dep_tid in subject_staff.get(sub_code, []):
                    seen[sub_code].append((dep_tid, hrs))
        syllabus_staff[c_name] = seen
    
    for cl in classes:
        c_name = cl['name']
        class_vars[c_name] = []
        for d in days:
            for p in periods:
                for item in cl['syllabus']:
                    sub_code = item['subject_code']
                    t_assigned = item.get('staff_id')
                    if t_assigned and str(t_assigned) not in ('None', 'null', 'ST_DUMMY', ''):
                        eligible_staff = [str(t_assigned)]
                    else:
                        eligible_staff = subject_staff.get(sub_code, [])
                    for t_id in eligible_staff:
                        # Only create var if it doesn't exist yet for this (class,day,period,sub,teacher)
                        if (c_name, d, p, sub_code, t_id) not in X:
                            var_name = f"x_{c_name}_{d}_{p}_{sub_code}_{t_id}".replace(' ', '_').replace('(', '_').replace(')', '_')
                            v = model.NewBoolVar(var_name)
                            X[(c_name, d, p, sub_code, t_id)] = v
                            class_vars[c_name].append(v)
                        else:
                            v = X[(c_name, d, p, sub_code, t_id)]
                        
                        # Track staff assignments
                        if t_id not in staff_vars:
                            staff_vars[t_id] = []
                        # Only add once per (t_id, d, p, sub_code) combination
                        if (v, d, p) not in staff_vars[t_id]:
                            staff_vars[t_id].append((v, d, p))
                        
                        if t_id != "ST_DUMMY":
                            if t_id not in staff_day_period_vars:
                                staff_day_period_vars[t_id] = { d_idx: { p_idx: [] for p_idx in periods } for d_idx in days }
                            if v not in staff_day_period_vars[t_id][d][p]:
                                staff_day_period_vars[t_id][d][p].append(v)
                        
                        # Track per-teacher hours: key = (c_name, sub_code, t_id)
                        key_cst = (c_name, sub_code, t_id)
                        if key_cst not in class_subject_staff_vars:
                            class_subject_staff_vars[key_cst] = []
                        if v not in class_subject_staff_vars[key_cst]:
                            class_subject_staff_vars[key_cst].append(v)
                        
                        # Track all-staff vars per (c_name, sub_code) for slot coverage
                        key_cs = (c_name, sub_code)
                        if key_cs not in class_subject_all_vars:
                            class_subject_all_vars[key_cs] = []
                        if v not in class_subject_all_vars[key_cs]:
                            class_subject_all_vars[key_cs].append(v)

    # CONSTRAINT 0: Fixed / Locked Slots (Pre-assignments / Pinning)
    fixed_slots = data.get('fixed_slots', [])
    for fs in fixed_slots:
        c_name = fs.get('class_name')
        sub_code = fs.get('subject_code')
        try:
            d = int(fs.get('day', 0))
            p = int(fs.get('period', 0))
        except (ValueError, TypeError):
            continue
            
        if any(cl['name'] == c_name for cl in classes):
            matching_vars = []
            eligible_staff = subject_staff.get(sub_code, [])
            for t_id in eligible_staff:
                if (c_name, d, p, sub_code, t_id) in X:
                    matching_vars.append(X[(c_name, d, p, sub_code, t_id)])
            if matching_vars:
                model.Add(sum(matching_vars) == 1)

    # CONSTRAINT 1: No Free Hours & Exactly 1 Subject + 1 Staff per Class per Period
    for cl in classes:
        c_name = cl['name']
        for d in days:
            for p in periods:
                slot_vars = []
                seen_vars = set()
                for item in cl['syllabus']:
                    sub_code = item['subject_code']
                    t_assigned = item.get('staff_id')
                    if t_assigned and str(t_assigned) not in ('None', 'null', 'ST_DUMMY', ''):
                        t_list = [str(t_assigned)]
                    else:
                        t_list = subject_staff.get(sub_code, [])
                    for t_id in t_list:
                        key = (c_name, d, p, sub_code, t_id)
                        if key in X and id(X[key]) not in seen_vars:
                            slot_vars.append(X[key])
                            seen_vars.add(id(X[key]))
                
                if not slot_vars:
                    return {
                        'status': 'ERROR',
                        'message': f"No eligible staff found for subjects in class: {c_name}"
                    }
                model.Add(sum(slot_vars) == 1)

    # CONSTRAINT 2: No Double Booking of Staff
    for t_id in staff_vars:
        if t_id == "ST_DUMMY":
            continue
        # Group variables for staff member by day and period
        day_period_vars = {}
        for (v, d, p) in staff_vars[t_id]:
            key = (d, p)
            if key not in day_period_vars:
                day_period_vars[key] = []
            day_period_vars[key].append(v)
        
        for (d, p), vars_list in day_period_vars.items():
            model.Add(sum(vars_list) <= 1)

    # CONSTRAINT 3: Subject Weekly Hour Requirements per Teacher (per syllabus row)
    # Each row in syllabus is (sub_code, staff_id, hours) - enforce exactly that many hours for that teacher
    applied_constraints = set()
    for cl in classes:
        c_name = cl['name']
        for item in cl['syllabus']:
            sub_code = item['subject_code']
            req_hours = item['hours']
            t_assigned = item.get('staff_id')
            if t_assigned and str(t_assigned) not in ('None', 'null', 'ST_DUMMY', ''):
                # Explicitly assigned teacher: enforce exact hours for this teacher
                t_id = str(t_assigned)
                key_cst = (c_name, sub_code, t_id)
                if key_cst not in applied_constraints:
                    vars_list = class_subject_staff_vars.get(key_cst, [])
                    if vars_list:
                        model.Add(sum(vars_list) == req_hours)
                    applied_constraints.add(key_cst)
            else:
                # Unassigned: enforce total hours for this subject across all eligible staff
                # Only apply once per (class, sub_code)
                key_cs = (c_name, sub_code)
                if key_cs not in applied_constraints:
                    # Gather all vars for this subject across ALL teachers
                    all_vars = class_subject_all_vars.get(key_cs, [])
                    # Total required is sum of all unassigned rows for this sub_code
                    total_unassigned = sum(
                        it['hours'] for it in cl['syllabus']
                        if it['subject_code'] == sub_code and
                        (not it.get('staff_id') or str(it.get('staff_id')) in ('None', 'null', 'ST_DUMMY', ''))
                    )
                    # Already-assigned teacher hours are fixed by their own constraint above
                    assigned_total = sum(
                        it['hours'] for it in cl['syllabus']
                        if it['subject_code'] == sub_code and
                        it.get('staff_id') and str(it.get('staff_id')) not in ('None', 'null', 'ST_DUMMY', '')
                    )
                    total_req = total_unassigned + assigned_total
                    if all_vars:
                        model.Add(sum(all_vars) == total_req)
                    applied_constraints.add(key_cs)

    # CONSTRAINT 3b: Class Incharge must teach at least 1 period in their class
    for cl in classes:
        c_name = cl['name']
        incharge_id = cl.get('incharge')
        if incharge_id and incharge_id != "ST_DUMMY":
            incharge_vars = []
            for item in cl['syllabus']:
                sub_code = item['subject_code']
                eligible_staff = subject_staff.get(sub_code, [])
                if incharge_id in eligible_staff:
                    for d in days:
                        for p in periods:
                            if (c_name, d, p, sub_code, incharge_id) in X:
                                incharge_vars.append(X[(c_name, d, p, sub_code, incharge_id)])
            if incharge_vars:
                model.Add(sum(incharge_vars) >= 1)

    # CONSTRAINT 4: Staff Weekly Workload Limits
    for t_id, s_info in staff_by_id.items():
        max_h = s_info['max_hours']
        if t_id in staff_vars:
            t_all_vars = [v for (v, d, p) in staff_vars[t_id]]
            model.Add(sum(t_all_vars) <= max_h)

    # CONSTRAINTS 5 & 6: Lab Continuity & Split Constraints
    # Deduplicate by (c_name, sub_code) - only apply once per subject per class
    lab_theory_applied = set()
    for cl in classes:
        c_name = cl['name']
        for item in cl['syllabus']:
            sub_code = item['subject_code']
            key_cs = (c_name, sub_code)
            if key_cs in lab_theory_applied:
                continue  # Skip duplicate sub_code rows (split-staff)
            lab_theory_applied.add(key_cs)
            
            sub_info = subject_by_code.get(sub_code)
            if not sub_info:
                continue
            sub_type = sub_info.get('type')
            
            # Use TOTAL hours for this subject across all rows (split + unassigned)
            req_hours = sum(it['hours'] for it in cl['syllabus'] if it['subject_code'] == sub_code)
            
            # Enforce Lab splits and consecutive hours
            if sub_type == "Lab":
                
                if req_hours == 2:
                    # 2 hours: 1 block of 2 consecutive hours on 1 day
                    for d in days:
                        y_var = model.NewBoolVar(f"y_{c_name}_{sub_code}_{d}".replace(' ', '_').replace('(', '_').replace(')', '_'))
                        class_lab_day_vars[c_name][d].append(y_var)
                        l_vars = [model.NewBoolVar(f"l_{c_name}_{sub_code}_{d}_{p}".replace(' ', '_').replace('(', '_').replace(')', '_')) for p in range(4)]
                        model.Add(sum(l_vars) == y_var)
                        
                        p_active = {}
                        for p in periods:
                            pv = [X[(c_name, d, p, sub_code, t_id)] for t_id in subject_staff.get(sub_code, []) if (c_name, d, p, sub_code, t_id) in X]
                            p_active[p] = sum(pv) if pv else 0
                            
                        model.Add(p_active[0] == l_vars[0])
                        model.Add(p_active[1] == l_vars[0] + l_vars[1])
                        model.Add(p_active[2] == l_vars[1] + l_vars[2])
                        model.Add(p_active[3] == l_vars[2] + l_vars[3])
                        model.Add(p_active[4] == l_vars[3])
                        model.Add(sum(p_active.values()) == 2 * y_var)
                        
                elif req_hours == 3:
                    # 3 hours: 1 block of 3 consecutive hours on 1 day
                    for d in days:
                        y_var = model.NewBoolVar(f"y_{c_name}_{sub_code}_{d}".replace(' ', '_').replace('(', '_').replace(')', '_'))
                        class_lab_day_vars[c_name][d].append(y_var)
                        l_vars = [model.NewBoolVar(f"l_{c_name}_{sub_code}_{d}_{p}".replace(' ', '_').replace('(', '_').replace(')', '_')) for p in range(3)]
                        model.Add(sum(l_vars) == y_var)
                        
                        p_active = {}
                        for p in periods:
                            pv = [X[(c_name, d, p, sub_code, t_id)] for t_id in subject_staff.get(sub_code, []) if (c_name, d, p, sub_code, t_id) in X]
                            p_active[p] = sum(pv) if pv else 0
                            
                        model.Add(p_active[0] == l_vars[0])
                        model.Add(p_active[1] == l_vars[0] + l_vars[1])
                        model.Add(p_active[2] == l_vars[0] + l_vars[1] + l_vars[2])
                        model.Add(p_active[3] == l_vars[1] + l_vars[2])
                        model.Add(p_active[4] == l_vars[2])
                        model.Add(sum(p_active.values()) == 3 * y_var)
                        
                elif req_hours == 4:
                    # 4 hours: 2 blocks of 2 consecutive hours on 2 different days
                    y_days = []
                    for d in days:
                        y_var = model.NewBoolVar(f"y_{c_name}_{sub_code}_{d}".replace(' ', '_').replace('(', '_').replace(')', '_'))
                        class_lab_day_vars[c_name][d].append(y_var)
                        y_days.append(y_var)
                        l_vars = [model.NewBoolVar(f"l_{c_name}_{sub_code}_{d}_{p}".replace(' ', '_').replace('(', '_').replace(')', '_')) for p in range(4)]
                        model.Add(sum(l_vars) == y_var)
                        
                        p_active = {}
                        for p in periods:
                            pv = [X[(c_name, d, p, sub_code, t_id)] for t_id in subject_staff.get(sub_code, []) if (c_name, d, p, sub_code, t_id) in X]
                            p_active[p] = sum(pv) if pv else 0
                            
                        model.Add(p_active[0] == l_vars[0])
                        model.Add(p_active[1] == l_vars[0] + l_vars[1])
                        model.Add(p_active[2] == l_vars[1] + l_vars[2])
                        model.Add(p_active[3] == l_vars[2] + l_vars[3])
                        model.Add(p_active[4] == l_vars[3])
                        model.Add(sum(p_active.values()) == 2 * y_var)
                        
                    model.Add(sum(y_days) == 2)
                    
                elif req_hours == 5:
                    # 5 hours: split into 2 consecutive hours on one day and 3 consecutive hours on another day
                    y_2 = {}
                    y_3 = {}
                    for d in days:
                        y_2[d] = model.NewBoolVar(f"y_2_{c_name}_{sub_code}_{d}".replace(' ', '_').replace('(', '_').replace(')', '_'))
                        y_3[d] = model.NewBoolVar(f"y_3_{c_name}_{sub_code}_{d}".replace(' ', '_').replace('(', '_').replace(')', '_'))
                        class_lab_day_vars[c_name][d].append(y_2[d])
                        class_lab_day_vars[c_name][d].append(y_3[d])
                        
                        model.Add(y_2[d] + y_3[d] <= 1)
                        
                        l_2 = [model.NewBoolVar(f"l_2_{c_name}_{sub_code}_{d}_{p}".replace(' ', '_').replace('(', '_').replace(')', '_')) for p in range(4)]
                        l_3 = [model.NewBoolVar(f"l_3_{c_name}_{sub_code}_{d}_{p}".replace(' ', '_').replace('(', '_').replace(')', '_')) for p in range(3)]
                        
                        model.Add(sum(l_2) == y_2[d])
                        model.Add(sum(l_3) == y_3[d])
                        
                        p_active = {}
                        for p in periods:
                            pv = [X[(c_name, d, p, sub_code, t_id)] for t_id in subject_staff.get(sub_code, []) if (c_name, d, p, sub_code, t_id) in X]
                            p_active[p] = sum(pv) if pv else 0
                            
                        model.Add(p_active[0] == l_2[0] + l_3[0])
                        model.Add(p_active[1] == l_2[0] + l_2[1] + l_3[0] + l_3[1])
                        model.Add(p_active[2] == l_2[1] + l_2[2] + l_3[0] + l_3[1] + l_3[2])
                        model.Add(p_active[3] == l_2[2] + l_2[3] + l_3[1] + l_3[2])
                        model.Add(p_active[4] == l_2[3] + l_3[2])
                        
                        model.Add(sum(p_active.values()) == 2 * y_2[d] + 3 * y_3[d])
                        
                    model.Add(sum(y_2.values()) == 1)
                    model.Add(sum(y_3.values()) == 1)
                    
                elif req_hours == 6:
                    # 6 hours: 2 blocks of 3 hours (mostly), or 3 blocks of 2 hours
                    split_3_3 = model.NewBoolVar(f"split_3_3_{c_name}_{sub_code}".replace(' ', '_').replace('(', '_').replace(')', '_'))
                    split_3_3_vars.append(split_3_3)
                    split_2_2_2 = split_3_3.Not()
                    
                    y_3_3 = {}
                    y_2_2_2 = {}
                    for d in days:
                        y_3_3[d] = model.NewBoolVar(f"y_3_3_{c_name}_{sub_code}_{d}".replace(' ', '_').replace('(', '_').replace(')', '_'))
                        y_2_2_2[d] = model.NewBoolVar(f"y_2_2_2_{c_name}_{sub_code}_{d}".replace(' ', '_').replace('(', '_').replace(')', '_'))
                        class_lab_day_vars[c_name][d].append(y_3_3[d])
                        class_lab_day_vars[c_name][d].append(y_2_2_2[d])
                        
                        model.Add(y_3_3[d] <= split_3_3)
                        model.Add(y_2_2_2[d] <= split_2_2_2)
                        
                        l_3_3 = [model.NewBoolVar(f"l_3_3_{c_name}_{sub_code}_{d}_{p}".replace(' ', '_').replace('(', '_').replace(')', '_')) for p in range(3)]
                        l_2_2_2 = [model.NewBoolVar(f"l_2_2_2_{c_name}_{sub_code}_{d}_{p}".replace(' ', '_').replace('(', '_').replace(')', '_')) for p in range(4)]
                        
                        model.Add(sum(l_3_3) == y_3_3[d])
                        model.Add(sum(l_2_2_2) == y_2_2_2[d])
                        
                        p_active = {}
                        for p in periods:
                            pv = [X[(c_name, d, p, sub_code, t_id)] for t_id in subject_staff.get(sub_code, []) if (c_name, d, p, sub_code, t_id) in X]
                            p_active[p] = sum(pv) if pv else 0
                            
                        model.Add(p_active[0] == l_3_3[0] + l_2_2_2[0])
                        model.Add(p_active[1] == l_3_3[0] + l_3_3[1] + l_2_2_2[0] + l_2_2_2[1])
                        model.Add(p_active[2] == l_3_3[0] + l_3_3[1] + l_3_3[2] + l_2_2_2[1] + l_2_2_2[2])
                        model.Add(p_active[3] == l_3_3[1] + l_3_3[2] + l_2_2_2[2] + l_2_2_2[3])
                        model.Add(p_active[4] == l_3_3[2] + l_2_2_2[3])
                        
                        model.Add(sum(p_active.values()) == 3 * y_3_3[d] + 2 * y_2_2_2[d])
                        
                    model.Add(sum(y_3_3.values()) == 2 * split_3_3)
                    model.Add(sum(y_2_2_2.values()) == 3 * split_2_2_2)
                else:
                    # Default fallback: treat as theory subject
                    pass
                    
            else:
                # CONSTRAINT 7: Theory Distribution
                sub_name_lower = (sub_info.get('name') or '').lower()
                is_language = ('tamil' in sub_name_lower) or ('english' in sub_name_lower)
                
                # If subject name includes 'Tamil' or 'English', allocate max 1 hour per day (1h/day over 6 days)
                # Otherwise, if theory subject has >= 5 hours, allow 2 hours per day; otherwise 1 hour max.
                if is_language:
                    max_daily = 1
                else:
                    max_daily = 2 if req_hours >= 5 else 1
                    
                for d in days:
                    day_vars = []
                    eligible_staff = subject_staff.get(sub_code, [])
                    for t_id in eligible_staff:
                        for p in periods:
                            if (c_name, d, p, sub_code, t_id) in X:
                                day_vars.append(X[(c_name, d, p, sub_code, t_id)])
                    model.Add(sum(day_vars) <= max_daily)

    # CONSTRAINT 7b: At most one Lab subject can be scheduled on any given day for a class
    for cl in classes:
        c_name = cl['name']
        for d in days:
            if class_lab_day_vars[c_name][d]:
                model.Add(sum(class_lab_day_vars[c_name][d]) <= 1)

    # CONSTRAINT 7c: Minimize/Avoid teaching 5 hours continuously on any day for any staff
    staff_continuous_5_vars = []
    for t_id, day_data in staff_day_period_vars.items():
        for d, period_data in day_data.items():
            active_p = {}
            for p in periods:
                active_p[p] = sum(period_data[p])
            
            v_5 = model.NewBoolVar(f"staff_5_{t_id}_{d}".replace(' ', '_').replace('(', '_').replace(')', '_'))
            for p in periods:
                model.Add(v_5 <= active_p[p])
            model.Add(sum(active_p.values()) - 5 * v_5 >= 0)
            staff_continuous_5_vars.append(v_5)

    # CONSTRAINT 8: Prevent Same Staff Teaching Different Subjects Consecutively to the Same Class
    # If a staff member teaches 2+ distinct subjects to the same class, they must not teach
    # those different subjects in adjacent back-to-back periods (p and p+1) on the same day.
    for cl in classes:
        c_name = cl['name']
        staff_class_subjects = {}
        for item in cl['syllabus']:
            sub_code = item['subject_code']
            t_assigned = item.get('staff_id')
            if t_assigned and str(t_assigned) not in ('None', 'null', 'ST_DUMMY', ''):
                t_id = str(t_assigned)
                if t_id not in staff_class_subjects:
                    staff_class_subjects[t_id] = set()
                staff_class_subjects[t_id].add(sub_code)
            else:
                for t_id in subject_staff.get(sub_code, []):
                    if t_id != "ST_DUMMY":
                        if t_id not in staff_class_subjects:
                            staff_class_subjects[t_id] = set()
                        staff_class_subjects[t_id].add(sub_code)

        for t_id, subs in staff_class_subjects.items():
            sub_list = list(subs)
            if len(sub_list) < 2:
                continue
            for i in range(len(sub_list)):
                for j in range(i + 1, len(sub_list)):
                    sub1 = sub_list[i]
                    sub2 = sub_list[j]
                    for d in days:
                        for p in range(len(periods) - 1):
                            v1_p = X.get((c_name, d, p, sub1, t_id))
                            v2_p1 = X.get((c_name, d, p+1, sub2, t_id))
                            if v1_p is not None and v2_p1 is not None:
                                model.Add(v1_p + v2_p1 <= 1)

                            v2_p = X.get((c_name, d, p, sub2, t_id))
                            v1_p1 = X.get((c_name, d, p+1, sub1, t_id))
                            if v2_p is not None and v1_p1 is not None:
                                model.Add(v2_p + v1_p1 <= 1)

    # Combine objective: Maximize 3+3 lab splits (weight 100) and Minimize continuous 5-hour staff days (weight 1)
    obj_terms = []
    if split_3_3_vars:
        obj_terms.append(100 * sum(split_3_3_vars))
    if staff_continuous_5_vars:
        obj_terms.append(-1 * sum(staff_continuous_5_vars))
    
    if obj_terms:
        model.Maximize(sum(obj_terms))

    # Solve — use longer timeout for cloud/slow environments
    import os
    solver = cp_model.CpSolver()
    is_cloud = bool(os.environ.get('RENDER') or os.environ.get('DYNO') or os.environ.get('PORT'))
    solver.parameters.max_time_in_seconds = 90.0 if is_cloud else 20.0
    solver.parameters.num_search_workers = 2  # parallel search threads
    solver.parameters.log_search_progress = False
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Format results
        timetable = {}
        for cl in classes:
            c_name = cl['name']
            timetable[c_name] = {}
            for d in days:
                timetable[c_name][str(d)] = {}
                for p in periods:
                    timetable[c_name][str(d)][str(p)] = None
                    
        for (c_name, d, p, sub_code, t_id), v in X.items():
            if solver.Value(v) == 1:
                timetable[c_name][str(d)][str(p)] = {
                    'subject_code': sub_code,
                    'subject_name': subject_by_code[sub_code]['name'],
                    'subject_type': subject_by_code[sub_code]['type'],
                    'staff_id': t_id,
                    'staff_name': staff_by_id[t_id]['name']
                }
                
        return {
            'status': 'SUCCESS',
            'timetable': timetable,
            'solve_time_seconds': solver.WallTime()
        }
    else:
        return {
            'status': 'INFEASIBLE',
            'message': 'No feasible timetable could be found. Please check constraints, staff availability, or working hours.',
            'solve_time_seconds': solver.WallTime()
        }

def diagnose_component_failure(comp_data, global_data):
    comp_classes = comp_data.get('classes', [])
    comp_staffs = comp_data.get('staffs', [])
    comp_subjects = comp_data.get('subjects', [])
    comp_class_names = [cl['name'] for cl in comp_classes]
    
    # 1. Staff workload limit exceeded in this component
    for s in comp_staffs:
        s_id = str(s['id'])
        s_name = s.get('name', s_id)
        max_h = s.get('max_hours', 30)
        assigned_h = sum(
            it.get('hours', 0)
            for cl in comp_classes
            for it in cl.get('syllabus', [])
            if str(it.get('staff_id')) == s_id
        )
        if assigned_h > max_h:
            faulty_classes = [
                cl['name'] for cl in comp_classes
                if any(str(it.get('staff_id')) == s_id for it in cl.get('syllabus', []))
            ]
            overload = assigned_h - max_h
            return {
                'status': 'INFEASIBLE',
                'error_type': 'STAFF_WORKLOAD_LIMIT_EXCEEDED',
                'faulty_staff': s_name,
                'faulty_classes': faulty_classes,
                'message': f"Workload limit exceeded: Faculty '{s_name}' (ID: {s_id}) is assigned {assigned_h} hours in class syllabi ({', '.join(faulty_classes)}), but their Maximum Limit in Staff Directory is only {max_h} hours! (Overallocated by +{overload}h).",
                'solution': f"Go to Staff Directory and increase max hours for '{s_name}' to at least {assigned_h}h, or reassign {overload}h in Staff Assignments to another faculty member."
            }

    # 2. Class syllabus total hours exceeded (> 30)
    for cl in comp_classes:
        tot = sum(it.get('hours', 0) for it in cl.get('syllabus', []))
        if tot > 30:
            return {
                'status': 'INFEASIBLE',
                'error_type': 'CLASS_HOURS_EXCEEDED',
                'faulty_classes': [cl['name']],
                'message': f"Class syllabus limit exceeded: Class '{cl['name']}' has {tot} hours allocated, exceeding the weekly 30-period limit by +{tot - 30} hours!",
                'solution': f"Edit class '{cl['name']}' in Classes & Syllabus and reduce subject hours so total equals 30."
            }

    # 3. Fixed slot collisions within this component
    raw_fixed = global_data.get('fixed_slots', [])
    fixed_in_comp = [fs for fs in raw_fixed if fs.get('class_name') in comp_class_names]
    days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}

    teacher_time_slots = {}
    for fs in fixed_in_comp:
        sub_code = fs.get('subject_code')
        c_name = fs.get('class_name')
        d = fs.get('day')
        p = fs.get('period')
        target_cl = next((c for c in comp_classes if c['name'] == c_name), None)
        t_id = None
        if target_cl:
            for it in target_cl.get('syllabus', []):
                if it.get('subject_code') == sub_code and it.get('staff_id'):
                    t_id = str(it.get('staff_id'))
                    break
        if t_id and t_id not in ('None', 'null', 'ST_DUMMY', ''):
            key = (t_id, d, p)
            if key in teacher_time_slots:
                prev_c = teacher_time_slots[key]
                t_name = next((s['name'] for s in comp_staffs if str(s['id']) == t_id), t_id)
                return {
                    'status': 'INFEASIBLE',
                    'error_type': 'FIXED_SLOT_TEACHER_COLLISION',
                    'faulty_staff': t_name,
                    'faulty_classes': [prev_c, c_name],
                    'message': f"Fixed slot collision: Faculty '{t_name}' is pinned to teach '{prev_c}' and '{c_name}' at the exact same time ({days_map.get(d, d)} Period {p+1})!",
                    'solution': f"In Fixed Slots tab, unpin or stagger the overlapping slot for '{t_name}'."
                }
            teacher_time_slots[key] = c_name

    # 4. Single-Class Isolated Solvability
    for cl in comp_classes:
        single_comp_data = {
            "classes": [cl],
            "staffs": comp_staffs,
            "subjects": comp_subjects,
            "fixed_slots": [fs for fs in fixed_in_comp if fs.get("class_name") == cl['name']]
        }
        single_res = solve_timetable(single_comp_data)
        if single_res['status'] != 'SUCCESS':
            labs = [it for it in cl.get('syllabus', []) if next((s.get('type') == 'Lab' for s in comp_subjects if s['code'] == it.get('subject_code')), False)]
            lab_codes = [it['subject_code'] for it in labs]
            fs_list = single_comp_data['fixed_slots']
            if labs and fs_list:
                return {
                    'status': 'INFEASIBLE',
                    'error_type': 'LAB_FIXED_SLOT_CONFLICT',
                    'faulty_classes': [cl['name']],
                    'message': f"Lab schedule conflict in class '{cl['name']}': Practical lab(s) ({', '.join(lab_codes)}) require consecutive 2-3 period blocks, but {len(fs_list)} pinned Fixed Slot(s) break up the schedule and block all available consecutive periods.",
                    'solution': f"In Fixed Slots tab, unpin or move slots for class '{cl['name']}' to leave open consecutive morning or afternoon blocks for labs."
                }
            elif labs:
                return {
                    'status': 'INFEASIBLE',
                    'error_type': 'LAB_CONSTRAINTS_CONFLICT',
                    'faulty_classes': [cl['name']],
                    'message': f"Lab allocation conflict in class '{cl['name']}': Practical lab(s) ({', '.join(lab_codes)}) cannot fit into the weekly period layout. Ensure each lab has 2, 3, 4, 5, or 6 hours.",
                    'solution': f"In Classes & Syllabus, adjust lab allocations for '{cl['name']}'."
                }
            else:
                return {
                    'status': 'INFEASIBLE',
                    'error_type': 'CLASS_INTERNAL_CONFLICT',
                    'faulty_classes': [cl['name']],
                    'message': f"Conflict inside class '{cl['name']}': The internal syllabus hours, incharge requirement, or pinned fixed slots cannot form a valid weekly timetable.",
                    'solution': f"In Classes & Syllabus, check subject hours and class incharge for '{cl['name']}'."
                }

    # 5. Shared Staff Contention between classes in component
    teacher_map = {}
    for cl in comp_classes:
        for it in cl.get('syllabus', []):
            tid = str(it.get('staff_id', ''))
            if tid and tid not in ('None', 'null', 'ST_DUMMY', ''):
                teacher_map.setdefault(tid, set()).add(cl['name'])
    shared_teachers = {tid: cls for tid, cls in teacher_map.items() if len(cls) > 1}
    shared_teacher_names = [
        f"{next((s['name'] for s in comp_staffs if str(s['id']) == tid), tid)} (in {', '.join(sorted(cls))})"
        for tid, cls in shared_teachers.items()
    ]
    return {
        'status': 'INFEASIBLE',
        'error_type': 'STAFF_SCHEDULE_CONTENTION',
        'faulty_classes': comp_class_names,
        'message': f"Schedule contention between classes: {', '.join(comp_class_names)}. The shared faculty member(s) [{', '.join(shared_teacher_names)}] cannot be in multiple classrooms simultaneously while satisfying consecutive lab and continuous teaching constraints.",
        'solution': f"In Staff Assignments, reassign one of the shared subjects to an alternate faculty member, or increase available faculty in those departments."
    }

def solve_timetable_scalable(data):
    """
    Splits the global scheduling problem into independent connected components
    based on shared staff allocations, solves each component in parallel/sequence,
    and merges the results. This drastically improves performance on large datasets.
    """
    classes = data.get('classes', [])
    staffs = data.get('staffs', [])
    subjects = data.get('subjects', [])
    
    # 1. Map each subject code to eligible staff IDs
    subject_staff = {}
    for sub in subjects:
        code = sub['code']
        sub_dept = sub.get('department')
        eligible = [s['id'] for s in staffs if (code in s.get('subjects', []) or s.get('department') == sub_dept)]
        subject_staff[code] = eligible
        
    # 2. For each class, find explicitly assigned staff to detect staff conflicts
    class_staffs = {}
    for cl in classes:
        c_name = cl['name']
        s_staffs = set()
        for item in cl['syllabus']:
            t_assigned = item.get('staff_id')
            if t_assigned and str(t_assigned) not in ('None', 'null', 'ST_DUMMY', ''):
                s_staffs.add(str(t_assigned))
        class_staffs[c_name] = s_staffs
        
    # 3. Find connected components of classes
    # Two classes are connected if they share at least one explicitly assigned staff member
    components = []
    visited = set()
    
    for cl in classes:
        c_name = cl['name']
        if c_name in visited:
            continue
            
        # BFS to find component
        comp = []
        queue = [c_name]
        visited.add(c_name)
        
        while queue:
            curr = queue.pop(0)
            comp.append(curr)
            curr_staffs = class_staffs[curr]
            
            # Find all unvisited classes that share explicitly assigned staff with curr
            for other in classes:
                o_name = other['name']
                if o_name not in visited:
                    if curr_staffs and curr_staffs.intersection(class_staffs[o_name]):
                        visited.add(o_name)
                        queue.append(o_name)
        components.append(comp)
        
    print(f"Divided scheduling problem into {len(components)} independent components of classes.")
    
    # 4. Solve each component independently
    combined_timetable = {}
    total_solve_time = 0.0
    
    for idx, comp in enumerate(components):
        # Filter data for this component
        comp_classes = [cl for cl in classes if cl['name'] in comp]
        comp_staffs = staffs
        
        # Get all subject codes involved in this component
        comp_sub_codes = set()
        for cl in comp_classes:
            for item in cl['syllabus']:
                comp_sub_codes.add(item['subject_code'])
                
        comp_subjects = [sub for sub in subjects if sub['code'] in comp_sub_codes]
        
        comp_data = {
            "classes": comp_classes,
            "staffs": comp_staffs,
            "subjects": comp_subjects,
            "fixed_slots": data.get("fixed_slots", [])
        }
        
        # Solve component
        res = solve_timetable(comp_data)
        if res['status'] != 'SUCCESS':
            diag = diagnose_component_failure(comp_data, data)
            print(f"  Component {idx+1} ({comp_classes[0]['name']}) is INFEASIBLE: {diag.get('message')}")
            return diag
            
        combined_timetable.update(res['timetable'])
        total_solve_time += res['solve_time_seconds']
        
    return {
        'status': 'SUCCESS',
        'timetable': combined_timetable,
        'solve_time_seconds': total_solve_time
    }

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        print("Testing solver with data.json...")
        try:
            with open('data.json', 'r') as f:
                data = json.load(f)
            result = solve_timetable(data)
            print(f"Status: {result['status']}")
            if result['status'] == 'SUCCESS':
                print(f"Solve Time: {result['solve_time_seconds']:.3f} seconds")
                # print some sample timetable
                sample_class = list(result['timetable'].keys())[0]
                print(f"\nSample Timetable for: {sample_class}")
                for d in range(6):
                    row = []
                    for p in range(5):
                        slot = result['timetable'][sample_class][str(d)][str(p)]
                        row.append(f"{slot['subject_code']} ({slot['staff_name']})" if slot else "FREE")
                    print(f"Day {d}: {' | '.join(row)}")
            else:
                print(f"Error Message: {result.get('message')}")
        except Exception as e:
            print(f"Error during test: {e}")
            sys.exit(1)
