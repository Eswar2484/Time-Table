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
            # If any component is infeasible, the whole problem is infeasible
            print(f"  Component {idx+1} ({comp_classes[0]['name']}) is INFEASIBLE: {res.get('message')}")
            return res
            
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
