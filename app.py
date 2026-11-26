import os
import json
from flask import Flask, jsonify, request, render_template, send_file, send_from_directory, session, redirect
import solver
import exporter

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'eswar_timetable_owner_sec_2026_super_key')

# Serve PWA service worker from root (required by browsers)
@app.route('/sw.js')
def service_worker():
    return send_from_directory(app.static_folder, 'sw.js',
                               mimetype='application/javascript')

# Serve favicon
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.static_folder, 'icons'),
                               'favicon.png', mimetype='image/png')

# Global cache for the generated timetable
GENERATED_TIMETABLE = None

import hashlib
import hmac

# Password "Eswar2004" securely hashed with SHA-256
DEFAULT_ADMIN_PASSWORD_HASH = hashlib.sha256('Eswar2004'.encode('utf-8')).hexdigest()
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH') or DEFAULT_ADMIN_PASSWORD_HASH
if os.environ.get('ADMIN_PASSCODE'):
    ADMIN_PASSWORD_HASH = hashlib.sha256(os.environ['ADMIN_PASSCODE'].strip().encode('utf-8')).hexdigest()

def get_request_passcode():
    passcode = request.args.get('passcode', '')
    if not passcode:
        data = request.get_json(silent=True) or {}
        passcode = data.get('passcode', '')
    if not passcode:
        passcode = request.headers.get('X-Admin-Passcode', '')
    return str(passcode).strip()

def verify_admin_passcode(passcode=None):
    try:
        if session.get('owner_authenticated') is True:
            return True
    except Exception:
        pass
    if passcode is None:
        passcode = get_request_passcode()
    if not passcode:
        return False
    candidate_hash = hashlib.sha256(str(passcode).strip().encode('utf-8')).hexdigest()
    return hmac.compare_digest(candidate_hash, ADMIN_PASSWORD_HASH)

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')

# Full pre-seeded default dataset for resetting
DEFAULT_DATA = {
  "departments": ["Computer Science", "Physics"],
  "staffs": [
    {"id": "ST001", "name": "Dr. Ramesh", "department": "Computer Science", "max_hours": 30, "subjects": ["CS101", "CS102", "CS103"]},
    {"id": "ST002", "name": "Mrs. Devi", "department": "Computer Science", "max_hours": 30, "subjects": ["CS101", "CS102", "CS103"]},
    {"id": "ST003", "name": "Dr. Krishnan", "department": "Physics", "max_hours": 30, "subjects": ["PH101", "PH102", "PH103"]},
    {"id": "ST004", "name": "Mr. Vignesh", "department": "Physics", "max_hours": 30, "subjects": ["PH101", "PH102", "PH103"]}
  ],
  "subjects": [
    {"code": "CS101", "name": "Python Programming", "department": "Computer Science", "type": "Theory"},
    {"code": "CS102", "name": "Python Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CS103", "name": "Data Structures", "department": "Computer Science", "type": "Theory"},
    {"code": "PH101", "name": "Mechanics", "department": "Physics", "type": "Theory"},
    {"code": "PH102", "name": "Physics Lab", "department": "Physics", "type": "Lab"},
    {"code": "PH103", "name": "Optics", "department": "Physics", "type": "Theory"}
  ],
  "classes": [
    {
      "name": "1st UG CS - A (Sem 1)",
      "department": "Computer Science",
      "level": "UG",
      "semester": 1,
      "incharge": "ST001",
      "syllabus": [
        {"subject_code": "CS101", "hours": 5, "staff_id": "ST001"},
        {"subject_code": "CS102", "hours": 4, "staff_id": "ST002"},
        {"subject_code": "CS103", "hours": 5, "staff_id": "ST001"},
        {"subject_code": "CS101", "hours": 5, "staff_id": "ST002"},
        {"subject_code": "CS103", "hours": 5, "staff_id": "ST002"},
        {"subject_code": "CS102", "hours": 6, "staff_id": "ST001"}
      ]
    },
    {
      "name": "1st UG Physics - A (Sem 1)",
      "department": "Physics",
      "level": "UG",
      "semester": 1,
      "incharge": "ST003",
      "syllabus": [
        {"subject_code": "PH101", "hours": 5, "staff_id": "ST003"},
        {"subject_code": "PH102", "hours": 4, "staff_id": "ST004"},
        {"subject_code": "PH103", "hours": 5, "staff_id": "ST003"},
        {"subject_code": "PH101", "hours": 5, "staff_id": "ST004"},
        {"subject_code": "PH103", "hours": 5, "staff_id": "ST004"},
        {"subject_code": "PH102", "hours": 6, "staff_id": "ST003"}
      ]
    }
  ],
  "fixed_slots": [],
  "timetable": None,
  "timetable_odd": None,
  "timetable_even": None
}

def map_subject_semester(code):
    c = code.upper()
    if c.startswith("BSC02"):
        return "UG 2nd year odd"
    elif c.startswith("BSC03"):
        return "UG 3rd year odd"
    elif c.startswith("BSC"):
        return "UG 1st year odd"
    elif c.startswith("MSC02"):
        return "PG 2nd year odd"
    elif c.startswith("MSC"):
        return "PG 1st year odd"
        
    if c.startswith("CSPG") or c.startswith("PHPG"):
        if "1" in c:
            return "PG 1st year odd"
        elif "2" in c:
            return "PG 1st year even"
        elif "3" in c:
            return "PG 2nd year odd"
        else:
            return "PG 2nd year even"
            
    if any(prefix in c for prefix in ["CS", "PH", "CO", "TAM", "ENG"]):
        if "1" in c:
            return "UG 1st year odd"
        elif "2" in c:
            return "UG 2nd year odd"
        elif "3" in c:
            return "UG 3rd year odd"
            
    return "UG 1st year odd"

def load_data():
    if not os.path.exists(DATA_PATH):
        with open(DATA_PATH, 'w') as f:
            json.dump(DEFAULT_DATA, f, indent=2)
    with open(DATA_PATH, 'r') as f:
        data = json.load(f)
    
    modified = False
    for sub in data.get('subjects', []):
        if 'semester' not in sub:
            sub['semester'] = map_subject_semester(sub['code'])
            modified = True

    # Initialize curriculum_hours if missing
    for cl in data.get('classes', []):
        for term_key in ['syllabus', 'even_syllabus']:
            sub_totals = {}
            for item in cl.get(term_key, []):
                code = item['subject_code']
                sub_totals[code] = sub_totals.get(code, 0) + item.get('hours', 0)
                
            for item in cl.get(term_key, []):
                if 'curriculum_hours' not in item:
                    item['curriculum_hours'] = sub_totals.get(item['subject_code'], item.get('hours', 0))
                    modified = True
            
    if modified:
        save_data(data)
    return data

def save_data(data):
    with open(DATA_PATH, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data', methods=['GET', 'POST'])
def api_data():
    global GENERATED_TIMETABLE
    if request.method == 'GET':
        data = load_data()
        return jsonify(data)
    else:
        # Save updated config
        new_data = request.json
        if not new_data:
            return jsonify({"status": "ERROR", "message": "No data received"}), 400
        save_data(new_data)
        GENERATED_TIMETABLE = new_data.get('timetable_odd') or new_data.get('timetable_even') or new_data.get('timetable')
        return jsonify({"status": "SUCCESS"})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    global GENERATED_TIMETABLE
    import copy
    data = copy.deepcopy(DEFAULT_DATA)
    data['timetable'] = None
    data['timetable_odd'] = None
    data['timetable_even'] = None
    save_data(data)
    GENERATED_TIMETABLE = None
    return jsonify({"status": "SUCCESS"})

@app.route('/api/backup', methods=['GET'])
def api_backup():
    return send_file(
        DATA_PATH,
        as_attachment=True,
        download_name="timetable_backup.json",
        mimetype="application/json"
    )

@app.route('/api/restore', methods=['POST'])
def api_restore():
    global GENERATED_TIMETABLE
    if 'file' not in request.files:
        return jsonify({"status": "ERROR", "message": "No file uploaded"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "ERROR", "message": "No selected file"}), 400
        
    mode = request.args.get('mode', 'replace') # 'replace' or 'append'
    
    try:
        content = file.read()
        parsed = json.loads(content)
        required = ['departments', 'staffs', 'subjects', 'classes']
        if not all(k in parsed for k in required):
            return jsonify({"status": "ERROR", "message": "Invalid JSON format: missing required keys"}), 400
        
        # Migrate subjects missing a semester field immediately on restore
        for sub in parsed.get('subjects', []):
            if 'semester' not in sub:
                sub['semester'] = map_subject_semester(sub['code'])
                
        if mode == 'append':
            current = load_data()
            
            # 1. Merge Departments (case-insensitive normalization)
            dept_lookup = {d.lower(): d for d in current.get('departments', [])}
            merged_depts = list(current.get('departments', []))
            for d in parsed.get('departments', []):
                d_lower = d.lower()
                if d_lower not in dept_lookup:
                    new_dept_name = d.title() if d.lower() != 'nme' else 'NME'
                    merged_depts.append(new_dept_name)
                    dept_lookup[d_lower] = new_dept_name
            current['departments'] = merged_depts
            
            # 2. Map Staff IDs to avoid conflicts
            staff_id_map = {}
            merged_staffs = list(current.get('staffs', []))
            existing_staff_ids = {s['id'] for s in merged_staffs}
            
            for s in parsed.get('staffs', []):
                old_id = s['id']
                dept = s.get('department', 'viscom')
                prefix = "".join([c for c in dept.upper() if c.isalnum()])
                if not prefix:
                    prefix = "ST"
                new_id = f"{prefix}_{old_id}"
                
                counter = 1
                temp_id = new_id
                while temp_id in existing_staff_ids:
                    temp_id = f"{new_id}_{counter}"
                    counter += 1
                new_id = temp_id
                
                staff_id_map[old_id] = new_id
                existing_staff_ids.add(new_id)
                
                s_copy = dict(s)
                s_copy['id'] = new_id
                s_dept = s.get('department') or ''
                s_copy['department'] = dept_lookup.get(s_dept.lower(), s_dept)
                merged_staffs.append(s_copy)
                
            current['staffs'] = merged_staffs
            
            # 3. Merge Subjects (skip duplicates)
            merged_subjects = list(current.get('subjects', []))
            existing_subject_codes = {sub['code'] for sub in merged_subjects}
            
            for sub in parsed.get('subjects', []):
                code = sub['code']
                if code not in existing_subject_codes:
                    sub_copy = dict(sub)
                    sub_dept = sub.get('department') or ''
                    sub_copy['department'] = dept_lookup.get(sub_dept.lower(), sub_dept)
                    merged_subjects.append(sub_copy)
                    existing_subject_codes.add(code)
            current['subjects'] = merged_subjects
            
            # 4. Merge Classes
            merged_classes = list(current.get('classes', []))
            existing_class_names = {cl['name'] for cl in merged_classes}
            
            for cl in parsed.get('classes', []):
                name = cl['name']
                if name in existing_class_names:
                    new_name = f"{name} (Restore)"
                    counter = 1
                    while new_name in existing_class_names:
                        new_name = f"{name} (Restore) {counter}"
                        counter += 1
                    name = new_name
                    
                cl_copy = dict(cl)
                cl_copy['name'] = name
                cl_dept = cl.get('department') or ''
                cl_copy['department'] = dept_lookup.get(cl_dept.lower(), cl_dept)
                
                old_incharge = cl.get('incharge')
                if old_incharge in staff_id_map:
                    cl_copy['incharge'] = staff_id_map[old_incharge]
                    
                # Map staff assignments in syllabus
                if 'syllabus' in cl_copy:
                    new_syllabus = []
                    for item in cl_copy['syllabus']:
                        item_copy = dict(item)
                        old_staff_id = item_copy.get('staff_id')
                        if old_staff_id in staff_id_map:
                            item_copy['staff_id'] = staff_id_map[old_staff_id]
                        new_syllabus.append(item_copy)
                    cl_copy['syllabus'] = new_syllabus
                    
                # Map staff assignments in even_syllabus
                if 'even_syllabus' in cl_copy:
                    new_even_syllabus = []
                    for item in cl_copy['even_syllabus']:
                        item_copy = dict(item)
                        old_staff_id = item_copy.get('staff_id')
                        if old_staff_id in staff_id_map:
                            item_copy['staff_id'] = staff_id_map[old_staff_id]
                        new_even_syllabus.append(item_copy)
                    cl_copy['even_syllabus'] = new_even_syllabus
                    
                merged_classes.append(cl_copy)
                existing_class_names.add(name)
            current['classes'] = merged_classes
            
            # 5. Merge Fixed Slots
            merged_fixed_slots = list(current.get('fixed_slots', []))
            for fs in parsed.get('fixed_slots', []):
                fs_copy = dict(fs)
                merged_fixed_slots.append(fs_copy)
            current['fixed_slots'] = merged_fixed_slots
            
            save_data(current)
            GENERATED_TIMETABLE = None
            return jsonify({"status": "SUCCESS", "mode": "append"})
        else:
            save_data(parsed)
            GENERATED_TIMETABLE = parsed.get('timetable')
            return jsonify({"status": "SUCCESS", "mode": "replace"})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 400

def generate_excel_template():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    import io
    
    wb = openpyxl.Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)
    
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    cell_alignment = Alignment(horizontal="left", vertical="center")
    border_side = Side(border_style="thin", color="CBD5E1")
    thin_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
    
    # 1. Departments Sheet
    ws_depts = wb.create_sheet(title="Departments")
    ws_depts.append(["Department Name"])
    ws_depts.append(["Computer Science"])
    ws_depts.append(["Physics"])
    ws_depts.append(["Commerce"])
    ws_depts.append(["Language"])
    
    # 2. Subjects Sheet
    ws_subs = wb.create_sheet(title="Subjects")
    ws_subs.append(["Subject Code", "Subject Name", "Subject Type", "Semester"])
    ws_subs.append(["CS101", "Programming in C", "Theory", "UG 1st year odd"])
    ws_subs.append(["CS102", "Digital Electronics", "Theory", "UG 1st year odd"])
    ws_subs.append(["PH101", "Properties of Matter", "Theory", "UG 1st year odd"])
    ws_subs.append(["PHL01", "Physics Lab", "Lab", "UG 1st year odd"])
    ws_subs.append(["CSPG101", "Advanced Algorithms", "Theory", "PG 1st year odd"])
    ws_subs.append(["CSPGL01", "Algorithms Lab", "Lab", "PG 1st year odd"])
    ws_subs.append(["TAM01", "Tamil 01", "Theory", "UG 1st year odd"])
    ws_subs.append(["ENG01", "English 01", "Theory", "UG 1st year odd"])
    
    # 3. Staffs Sheet
    ws_staff = wb.create_sheet(title="Staffs")
    ws_staff.append(["Staff ID", "Staff Name", "Department", "Max Hours", "Eligible Subjects"])
    ws_staff.append(["ST001", "Dr. Ramesh", "Computer Science", 18, "CS101, CS102, CSPG101, CSPGL01"])
    ws_staff.append(["ST002", "Dr. Priya", "Computer Science", 18, "CS102, CSPG101"])
    ws_staff.append(["ST003", "Dr. Krishnan", "Physics", 18, "PH101, PHL01"])
    ws_staff.append(["ST004", "Mr. Selvam", "Language", 24, "TAM01"])
    ws_staff.append(["ST005", "Mr. John", "Language", 24, "ENG01"])
    
    # 4. Classes Sheet
    ws_classes = wb.create_sheet(title="Classes")
    ws_classes.append(["Class Name", "Department", "Semester", "Class Incharge", "Syllabus"])
    ws_classes.append(["1st UG CS - A (Sem 1)", "Computer Science", 1, "ST001", "CS101:5, CS102:5, TAM01:6, ENG01:6, PH101:4, PHL01:4"])
    ws_classes.append(["1st PG CS - A (Sem 1)", "Computer Science", 1, "ST002", "CSPG101:6, CSPGL01:6"])
    
    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = cell_alignment
        
        for row in sheet.iter_rows(min_row=1):
            for cell in row:
                if cell.row > 1:
                    cell.alignment = cell_alignment
                    cell.border = thin_border
        
        for col in sheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 15)
            
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

@app.route('/api/import/template', methods=['GET'])
def api_import_template():
    try:
        buffer = generate_excel_template()
        return send_file(
            buffer,
            as_attachment=True,
            download_name="timetable_excel_template.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        return f"Error generating template: {str(e)}", 500

@app.route('/api/import/upload', methods=['POST'])
def api_import_upload():
    global GENERATED_TIMETABLE
    if 'file' not in request.files:
        return jsonify({"status": "ERROR", "message": "No file uploaded"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "ERROR", "message": "No selected file"}), 400
        
    try:
        import openpyxl
        import io
        wb = openpyxl.load_workbook(io.BytesIO(file.read()), data_only=True)
        
        required_sheets = ["Departments", "Staffs", "Subjects", "Classes"]
        for s in required_sheets:
            if s not in wb.sheetnames:
                return jsonify({"status": "ERROR", "message": f"Missing required Excel sheet: '{s}'"}), 400
                
        errors = []
        
        # 1. Parse Departments
        ws_depts = wb["Departments"]
        departments = []
        for r_idx in range(2, ws_depts.max_row + 1):
            val = ws_depts.cell(row=r_idx, column=1).value
            if val is not None:
                dept_name = str(val).strip()
                if dept_name and dept_name not in departments:
                    departments.append(dept_name)
                    
        if not departments:
            errors.append("Departments sheet: No departments found.")
            
        # 2. Parse Subjects
        ws_subs = wb["Subjects"]
        subjects = []
        subject_codes = set()
        for r_idx in range(2, ws_subs.max_row + 1):
            row_vals = [ws_subs.cell(row=r_idx, column=c).value for c in range(1, 5)]
            if all(v is None for v in row_vals):
                continue
            # Pad row if less than 4 columns (for backwards compatibility)
            while len(row_vals) < 4:
                row_vals.append(None)
            code, name, s_type, semester = row_vals
            if not code:
                errors.append(f"Subjects sheet Row {r_idx}: Subject Code cannot be empty.")
                continue
            code_str = str(code).strip()
            name_str = str(name).strip() if name else code_str
            type_str = str(s_type).strip() if s_type else "Theory"
            
            # Mapped default semester logic if missing
            if semester:
                sem_str = str(semester).strip()
            else:
                if code_str in ["CS101", "CS102", "TAM01", "ENG01", "PH101", "PHL01"]:
                    sem_str = "UG 1st year odd"
                elif code_str in ["CSPG101", "CSPGL01"]:
                    sem_str = "PG 1st year odd"
                elif "PG" in code_str:
                    if "1" in code_str:
                        sem_str = "PG 1st year odd"
                    elif "2" in code_str:
                        sem_str = "PG 1st year even"
                    elif "3" in code_str:
                        sem_str = "PG 2nd year odd"
                    else:
                        sem_str = "PG 2nd year even"
                else:
                    if "1" in code_str:
                        sem_str = "UG 1st year odd"
                    elif "2" in code_str:
                        sem_str = "UG 2nd year odd"
                    elif "3" in code_str:
                        sem_str = "UG 3rd year odd"
                    else:
                        sem_str = "UG 1st year odd"
            
            if type_str not in ["Theory", "Lab", "Project"]:
                errors.append(f"Subjects sheet Row {r_idx}: Invalid type '{type_str}' for subject '{code_str}'. Must be Theory, Lab, or Project.")
                
            if code_str in subject_codes:
                errors.append(f"Subjects sheet Row {r_idx}: Duplicate subject code '{code_str}'.")
            else:
                subject_codes.add(code_str)
                subjects.append({
                    "code": code_str,
                    "name": name_str,
                    "type": type_str,
                    "semester": sem_str
                })
                
        # 3. Parse Staffs
        ws_staff = wb["Staffs"]
        staffs = []
        staff_ids = set()
        for r_idx in range(2, ws_staff.max_row + 1):
            row_vals = [ws_staff.cell(row=r_idx, column=c).value for c in range(1, 6)]
            if all(v is None for v in row_vals):
                continue
            s_id, name, dept, max_h, subjs = row_vals
            if not s_id:
                errors.append(f"Staffs sheet Row {r_idx}: Staff ID cannot be empty.")
                continue
            id_str = str(s_id).strip()
            name_str = str(name).strip() if name else id_str
            dept_str = str(dept).strip() if dept else ""
            
            try:
                max_hours = int(max_h) if max_h is not None else 18
            except ValueError:
                errors.append(f"Staffs sheet Row {r_idx}: Max Hours must be a valid number.")
                max_hours = 18
                
            subjs_list = []
            if subjs:
                subjs_list = [s.strip() for s in str(subjs).split(",") if s.strip()]
                
            if id_str in staff_ids:
                errors.append(f"Staffs sheet Row {r_idx}: Duplicate Staff ID '{id_str}'.")
            else:
                staff_ids.add(id_str)
                
            if dept_str not in departments:
                errors.append(f"Staffs sheet Row {r_idx}: Department '{dept_str}' for staff '{id_str}' does not exist in Departments sheet.")
                
            for code in subjs_list:
                if code not in subject_codes:
                    errors.append(f"Staffs sheet Row {r_idx}: Subject code '{code}' for staff '{id_str}' does not exist in Subjects sheet.")
                    
            staffs.append({
                "id": id_str,
                "name": name_str,
                "department": dept_str,
                "max_hours": max_hours,
                "subjects": subjs_list
            })
            
        # 4. Parse Classes
        ws_classes = wb["Classes"]
        classes = []
        class_names = set()
        for r_idx in range(2, ws_classes.max_row + 1):
            row_vals = [ws_classes.cell(row=r_idx, column=c).value for c in range(1, 6)]
            if all(v is None for v in row_vals):
                continue
            name, dept, sem, incharge, syllabus_str = row_vals
            if not name:
                errors.append(f"Classes sheet Row {r_idx}: Class Name cannot be empty.")
                continue
            name_str = str(name).strip()
            dept_str = str(dept).strip() if dept else ""
            
            try:
                sem_val = int(sem) if sem is not None else 1
            except ValueError:
                errors.append(f"Classes sheet Row {r_idx}: Semester must be a number.")
                sem_val = 1
                
            incharge_str = str(incharge).strip() if incharge else ""
            
            if sem_val < 1 or sem_val > 6:
                errors.append(f"Classes sheet Row {r_idx}: Semester must be between 1 and 6.")
                
            if dept_str not in departments:
                errors.append(f"Classes sheet Row {r_idx}: Department '{dept_str}' for class '{name_str}' does not exist in Departments sheet.")
                
            if incharge_str and incharge_str not in staff_ids:
                errors.append(f"Classes sheet Row {r_idx}: Class Incharge staff ID '{incharge_str}' does not exist in Staffs list.")
                
            syllabus = []
            if syllabus_str:
                items = [it.strip() for it in str(syllabus_str).split(",") if it.strip()]
                for it in items:
                    if ":" not in it:
                        errors.append(f"Classes sheet Row {r_idx}: Invalid syllabus entry '{it}'. Format must be 'SubjectCode:Hours'.")
                        continue
                    parts = it.split(":")
                    sub_code = parts[0].strip()
                    try:
                        hours_val = int(parts[1].strip())
                    except (ValueError, IndexError):
                        errors.append(f"Classes sheet Row {r_idx}: Invalid hours value in '{it}'.")
                        continue
                        
                    if sub_code not in subject_codes:
                        errors.append(f"Classes sheet Row {r_idx}: Subject code '{sub_code}' in syllabus does not exist in Subjects sheet.")
                        
                    syllabus.append({
                        "subject_code": sub_code,
                        "hours": hours_val
                    })
                    
            if name_str in class_names:
                errors.append(f"Classes sheet Row {r_idx}: Duplicate class name '{name_str}'.")
            else:
                class_names.add(name_str)
                
            classes.append({
                "name": name_str,
                "department": dept_str,
                "semester": sem_val,
                "incharge": incharge_str,
                "syllabus": syllabus
            })
            
        if errors:
            return jsonify({
                "status": "ERROR",
                "message": "Validation errors found in Excel sheet. Please correct them and try again.",
                "errors": errors
            }), 400
            
        new_data = {
            "departments": departments,
            "staffs": staffs,
            "subjects": subjects,
            "classes": classes,
            "timetable": None
        }
        
        save_data(new_data)
        GENERATED_TIMETABLE = None
        return jsonify({"status": "SUCCESS"})
        
    except Exception as e:
        return jsonify({"status": "ERROR", "message": f"Server error parsing file: {str(e)}"}), 500

def get_timetable_for_term(term, input_data=None):
    if input_data is not None:
        import copy
        data = copy.deepcopy(input_data)
    else:
        data = load_data()
    
    # Filter classes by semester term
    is_odd_term = (term == 'odd')
    filtered_classes = []
    for cl in data.get('classes', []):
        if is_odd_term:
            cl_copy = dict(cl)
            cl_copy['syllabus'] = cl.get('syllabus', [])
            if cl_copy['syllabus']:
                filtered_classes.append(cl_copy)
        else:
            cl_copy = dict(cl)
            cl_copy['semester'] = cl.get('semester', 1) + 1
            cl_copy['syllabus'] = cl.get('even_syllabus', [])
            if cl_copy['syllabus']:
                filtered_classes.append(cl_copy)
                
    if not filtered_classes:
        return {'status': 'SUCCESS', 'timetable': {}, 'solve_time_seconds': 0.0}
        
    data['classes'] = filtered_classes
    
    # Filter fixed_slots for current term
    raw_fixed = data.get('fixed_slots', [])
    data['fixed_slots'] = [
        fs for fs in raw_fixed
        if fs.get('term', 'all') in ['all', term]
    ]
    
    # Inject dummy subjects & staff
    dummy_subjects = [
        {"code": "DUMMY_SS", "name": "Self-Study", "department": "All", "type": "Theory"},
        {"code": "DUMMY_LB", "name": "Library", "department": "All", "type": "Theory"},
        {"code": "DUMMY_SM", "name": "Seminar", "department": "All", "type": "Theory"}
    ]
    dummy_staff = {
        "id": "ST_DUMMY",
        "name": "N/A",
        "department": "All",
        "max_hours": 9999,
        "subjects": ["DUMMY_SS", "DUMMY_LB", "DUMMY_SM"]
    }
    
    # Avoid mutating global/original list multiple times on load
    data['subjects'] = list(data.get('subjects', [])) + dummy_subjects
    data['staffs'] = list(data.get('staffs', [])) + [dummy_staff]
    
    for cl in data['classes']:
        cl['syllabus'] = [item for item in cl['syllabus'] if item['subject_code'] not in ["DUMMY_SS", "DUMMY_LB", "DUMMY_SM"]]
        total_hours = sum(item['hours'] for item in cl['syllabus'])
        if total_hours < 30:
            needed = 30 - total_hours
            ss_hours = (needed + 2) // 3
            lb_hours = (needed + 1) // 3
            sm_hours = needed // 3
            
            if ss_hours > 0:
                cl['syllabus'].append({"subject_code": "DUMMY_SS", "hours": ss_hours})
            if lb_hours > 0:
                cl['syllabus'].append({"subject_code": "DUMMY_LB", "hours": lb_hours})
            if sm_hours > 0:
                cl['syllabus'].append({"subject_code": "DUMMY_SM", "hours": sm_hours})
                
    result = solver.solve_timetable_scalable(data)
    return result

import datetime

ACTIVITY_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'activity_logs.jsonl')

@app.route('/api/default_data', methods=['GET'])
def api_default_data():
    return jsonify(DEFAULT_DATA)

@app.route('/api/log_activity', methods=['POST'])
def api_log_activity():
    try:
        payload = request.json or {}
        user_name = payload.get('user_name', 'Unknown Guest')
        action = payload.get('action', 'UNKNOWN_ACTION')
        details = payload.get('details', '')
        
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
            
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        log_entry = {
            "timestamp": timestamp,
            "ip": ip,
            "user_name": user_name,
            "action": action,
            "details": details
        }
        
        # Read existing logs to keep max 500 latest entries
        lines = []
        if os.path.exists(ACTIVITY_LOG_PATH):
            with open(ACTIVITY_LOG_PATH, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
                
        lines.append(json.dumps(log_entry, ensure_ascii=False))
        if len(lines) > 500:
            lines = lines[-500:]  # Keep last 500 entries
            
        with open(ACTIVITY_LOG_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
            
        return jsonify({"status": "SUCCESS"})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/admin/logs')
def admin_logs_view():
    passcode = get_request_passcode()
    if passcode:
        candidate_hash = hashlib.sha256(str(passcode).strip().encode('utf-8')).hexdigest()
        if hmac.compare_digest(candidate_hash, ADMIN_PASSWORD_HASH):
            session['owner_authenticated'] = True
            # Redirect to clean URL so password NEVER stays in the address bar!
            return redirect('/admin/logs')
            
    if not session.get('owner_authenticated'):
        return f"Unauthorized: Access restricted to app owner. Please unlock via the Owner Logs Panel in the dashboard.", 401
    return render_template('admin_logs.html')

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    payload = request.get_json(silent=True) or {}
    password = payload.get('password', '')
    candidate_hash = hashlib.sha256(str(password).strip().encode('utf-8')).hexdigest()
    if hmac.compare_digest(candidate_hash, ADMIN_PASSWORD_HASH):
        session['owner_authenticated'] = True
        return jsonify({"status": "SUCCESS", "message": "Authenticated"})
    return jsonify({"status": "ERROR", "message": "Incorrect passcode"}), 401

@app.route('/api/admin/logout', methods=['GET', 'POST'])
def api_admin_logout():
    session.pop('owner_authenticated', None)
    if request.method == 'GET':
        return redirect('/')
    return jsonify({"status": "SUCCESS"})

@app.route('/api/admin/verify', methods=['GET', 'POST'])
def api_admin_verify():
    valid = verify_admin_passcode()
    if valid:
        return jsonify({"status": "SUCCESS", "message": "Authorized"})
    return jsonify({"status": "ERROR", "message": "Invalid passcode"}), 401

@app.route('/api/admin/logs')
def api_admin_logs():
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
        
    logs = []
    if os.path.exists(ACTIVITY_LOG_PATH):
        with open(ACTIVITY_LOG_PATH, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if 'id' not in entry:
                            entry['id'] = idx
                        logs.append(entry)
                    except Exception:
                        pass
                        
    user_filter = request.args.get('user', '').strip()
    if user_filter and user_filter.lower() != 'all':
        logs = [l for l in logs if l.get('user_name', '').lower() == user_filter.lower()]
        
    return jsonify(list(reversed(logs)))

@app.route('/api/admin/edit_log', methods=['POST'])
def api_admin_edit_log():
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    log_id = payload.get('log_id')
    new_user = payload.get('user_name')
    new_action = payload.get('action')
    new_details = payload.get('details')
    new_time = payload.get('timestamp')
    
    if log_id is None:
        return jsonify({"status": "ERROR", "message": "log_id is required"}), 400
        
    try:
        lines = []
        if os.path.exists(ACTIVITY_LOG_PATH):
            with open(ACTIVITY_LOG_PATH, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
                
        updated = False
        new_lines = []
        for idx, line in enumerate(lines):
            try:
                entry = json.loads(line)
                entry_id = entry.get('id', idx)
                if str(entry_id) == str(log_id) or str(idx) == str(log_id):
                    if new_user is not None: entry['user_name'] = str(new_user).strip()
                    if new_action is not None: entry['action'] = str(new_action).strip()
                    if new_details is not None: entry['details'] = str(new_details).strip()
                    if new_time is not None: entry['timestamp'] = str(new_time).strip()
                    entry['id'] = entry_id
                    new_lines.append(json.dumps(entry, ensure_ascii=False))
                    updated = True
                else:
                    new_lines.append(line)
            except Exception:
                new_lines.append(line)
                
        if not updated:
            return jsonify({"status": "ERROR", "message": "Log entry not found"}), 404
            
        with open(ACTIVITY_LOG_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines) + '\n')
            
        return jsonify({"status": "SUCCESS"})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/api/admin/delete_log', methods=['POST'])
def api_admin_delete_log():
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    log_id = payload.get('log_id')
    
    if log_id is None:
        return jsonify({"status": "ERROR", "message": "log_id is required"}), 400
        
    try:
        lines = []
        if os.path.exists(ACTIVITY_LOG_PATH):
            with open(ACTIVITY_LOG_PATH, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
                
        new_lines = []
        deleted = False
        for idx, line in enumerate(lines):
            try:
                entry = json.loads(line)
                entry_id = entry.get('id', idx)
                if str(entry_id) == str(log_id) or str(idx) == str(log_id):
                    deleted = True
                    continue
                new_lines.append(line)
            except Exception:
                new_lines.append(line)
                
        with open(ACTIVITY_LOG_PATH, 'w', encoding='utf-8') as f:
            if new_lines:
                f.write('\n'.join(new_lines) + '\n')
            else:
                f.write('')
                
        return jsonify({"status": "SUCCESS", "deleted": deleted})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/api/admin/delete_user_logs', methods=['POST'])
def api_admin_delete_user_logs():
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    user_name = payload.get('user_name', '').strip()
    
    if not user_name:
        return jsonify({"status": "ERROR", "message": "user_name is required"}), 400
        
    try:
        lines = []
        if os.path.exists(ACTIVITY_LOG_PATH):
            with open(ACTIVITY_LOG_PATH, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
                
        new_lines = []
        del_count = 0
        for line in lines:
            try:
                entry = json.loads(line)
                if entry.get('user_name', '').strip().lower() == user_name.lower():
                    del_count += 1
                    continue
                new_lines.append(line)
            except Exception:
                new_lines.append(line)
                
        with open(ACTIVITY_LOG_PATH, 'w', encoding='utf-8') as f:
            if new_lines:
                f.write('\n'.join(new_lines) + '\n')
            else:
                f.write('')
                
        return jsonify({"status": "SUCCESS", "deleted_count": del_count})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/api/admin/download_logs')
def api_admin_download_logs():
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
    if not os.path.exists(ACTIVITY_LOG_PATH):
        with open(ACTIVITY_LOG_PATH, 'w', encoding='utf-8') as f:
            f.write('')
    return send_file(
        ACTIVITY_LOG_PATH,
        as_attachment=True,
        download_name="activity_logs.jsonl",
        mimetype="application/x-jsonlines"
    )

@app.route('/api/admin/clear_logs', methods=['POST'])
def api_admin_clear_logs():
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
    try:
        if os.path.exists(ACTIVITY_LOG_PATH):
            with open(ACTIVITY_LOG_PATH, 'w', encoding='utf-8') as f:
                f.write('')
        return jsonify({"status": "SUCCESS"})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

# -------------------------------------------------------------
# OWNER LIVE COLLEGE DATA MANAGEMENT (VIEW, EDIT, DELETE OTHERS' DATA)
# -------------------------------------------------------------
@app.route('/api/admin/data', methods=['GET'])
def api_admin_get_data():
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
    data = load_data()
    return jsonify({"status": "SUCCESS", "data": data})

@app.route('/api/admin/update_data', methods=['POST'])
def api_admin_update_data():
    global GENERATED_TIMETABLE
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    new_data = payload.get('data')
    if not new_data or not isinstance(new_data, dict):
        return jsonify({"status": "ERROR", "message": "Invalid data payload"}), 400
    save_data(new_data)
    GENERATED_TIMETABLE = new_data.get('timetable_odd') or new_data.get('timetable_even') or new_data.get('timetable')
    return jsonify({"status": "SUCCESS"})

@app.route('/api/admin/delete_item', methods=['POST'])
def api_admin_delete_item():
    global GENERATED_TIMETABLE
    if not verify_admin_passcode():
        return jsonify({"status": "ERROR", "message": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    item_type = payload.get('item_type')
    item_id = str(payload.get('item_id', ''))
    
    if not item_type or not item_id:
        return jsonify({"status": "ERROR", "message": "item_type and item_id are required"}), 400
        
    data = load_data()
    deleted = False
    
    if item_type == 'class':
        initial_len = len(data.get('classes', []))
        data['classes'] = [c for c in data.get('classes', []) if c.get('name') != item_id]
        deleted = (len(data['classes']) < initial_len)
        data['fixed_slots'] = [fs for fs in data.get('fixed_slots', []) if fs.get('class_name') != item_id]
        
    elif item_type == 'staff':
        initial_len = len(data.get('staffs', []))
        data['staffs'] = [s for s in data.get('staffs', []) if str(s.get('id')) != item_id]
        deleted = (len(data['staffs']) < initial_len)
        for c in data.get('classes', []):
            for t_k in ['syllabus', 'even_syllabus']:
                for it in c.get(t_k, []):
                    if str(it.get('staff_id')) == item_id:
                        it['staff_id'] = None
                        
    elif item_type == 'subject':
        initial_len = len(data.get('subjects', []))
        data['subjects'] = [s for s in data.get('subjects', []) if s.get('code') != item_id]
        deleted = (len(data['subjects']) < initial_len)
        for c in data.get('classes', []):
            for t_k in ['syllabus', 'even_syllabus']:
                c[t_k] = [it for it in c.get(t_k, []) if it.get('subject_code') != item_id]
        for s in data.get('staffs', []):
            s['subjects'] = [code for code in s.get('subjects', []) if code != item_id]
        data['fixed_slots'] = [fs for fs in data.get('fixed_slots', []) if fs.get('subject_code') != item_id]
        
    elif item_type == 'fixed_slot':
        initial_len = len(data.get('fixed_slots', []))
        try:
            slot_idx = int(item_id)
            if 0 <= slot_idx < len(data.get('fixed_slots', [])):
                data['fixed_slots'].pop(slot_idx)
                deleted = True
        except ValueError:
            data['fixed_slots'] = [fs for fs in data.get('fixed_slots', []) if f"{fs.get('class_name')}_{fs.get('subject_code')}_{fs.get('day')}_{fs.get('period')}" != item_id]
            deleted = (len(data['fixed_slots']) < initial_len)
            
    if deleted:
        data['timetable'] = None
        data['timetable_odd'] = None
        data['timetable_even'] = None
        GENERATED_TIMETABLE = None
        save_data(data)
        return jsonify({"status": "SUCCESS"})
    else:
        return jsonify({"status": "ERROR", "message": f"{item_type} '{item_id}' not found"}), 404

def api_generate_internal(input_data=None):
    res_odd = get_timetable_for_term('odd', input_data=input_data)
    if res_odd['status'] != 'SUCCESS':
        return res_odd
        
    res_even = get_timetable_for_term('even', input_data=input_data)
    if res_even['status'] != 'SUCCESS':
        return res_even
        
    if input_data is not None:
        return {
            "status": "SUCCESS",
            "timetable_odd": res_odd['timetable'],
            "timetable_even": res_even['timetable'],
            "solve_time_seconds": res_odd.get('solve_time_seconds', 0.0) + res_even.get('solve_time_seconds', 0.0)
        }
        
    data = load_data()
    data['timetable_odd'] = res_odd['timetable']
    data['timetable_even'] = res_even['timetable']
    data['timetable'] = res_odd['timetable']
    save_data(data)
    
    return {
        "status": "SUCCESS",
        "timetable_odd": res_odd['timetable'],
        "timetable_even": res_even['timetable'],
        "solve_time_seconds": res_odd.get('solve_time_seconds', 0.0) + res_even.get('solve_time_seconds', 0.0)
    }

@app.route('/api/generate', methods=['POST'])
def api_generate():
    global GENERATED_TIMETABLE
    GENERATED_TIMETABLE = None
    input_data = request.json
    result = api_generate_internal(input_data=input_data)
    if result.get('status') == 'SUCCESS':
        GENERATED_TIMETABLE = result.get('timetable_odd') or result.get('timetable_even') or {}
        result['timetable'] = GENERATED_TIMETABLE
        if input_data:
            input_data['timetable_odd'] = result.get('timetable_odd')
            input_data['timetable_even'] = result.get('timetable_even')
            input_data['timetable'] = GENERATED_TIMETABLE
            save_data(input_data)
    return jsonify(result)

@app.route('/api/clear', methods=['POST'])
def api_clear():
    global GENERATED_TIMETABLE
    GENERATED_TIMETABLE = None
    data = load_data()
    data['timetable'] = None
    data['timetable_odd'] = None
    data['timetable_even'] = None
    save_data(data)
    return jsonify({"status": "SUCCESS"})

@app.route('/api/clear_all', methods=['POST'])
def api_clear_all():
    global GENERATED_TIMETABLE
    GENERATED_TIMETABLE = None
    empty_db = {
        "departments": [],
        "staffs": [],
        "subjects": [],
        "classes": [],
        "timetable": None,
        "timetable_odd": None,
        "timetable_even": None
    }
    save_data(empty_db)
    return jsonify({"status": "SUCCESS"})

@app.route('/api/export/excel', methods=['GET', 'POST'])
def api_export_excel():
    view_type = request.args.get('type', 'class')
    term = request.args.get('term', 'all')
    dept = request.args.get('dept', 'all')
    item_id = request.args.get('item', 'all')
    
    if request.method == 'POST':
        payload = request.json or {}
        data = payload.get('data', {})
        timetable = payload.get('timetable')
    else:
        data = load_data()
        timetable = data.get('timetable_even') if term == 'even' else data.get('timetable_odd')
        
    if not timetable:
        res = api_generate_internal(input_data=data if request.method == 'POST' else None)
        if res['status'] != 'SUCCESS':
            return f"Error: Cannot export Excel because timetable is infeasible: {res.get('message')}", 400
        timetable = res['timetable_even'] if term == 'even' else res['timetable_odd']

    staffs_to_export = data.get('staffs', [])
    if dept != 'all':
        staffs_to_export = [s for s in staffs_to_export if s.get('department') == dept]

    if item_id != 'all':
        staffs_to_export = [s for s in staffs_to_export if str(s.get('id')) == str(item_id)]

    if view_type == 'class':
        # Filter classes by department for class-wise export
        if dept != 'all':
            filtered_timetable = {}
            for cl_name, cl_sched in timetable.items():
                cl_obj = next((c for c in data.get('classes', []) if c['name'] == cl_name), None)
                if cl_obj and cl_obj.get('department') == dept:
                    filtered_timetable[cl_name] = cl_sched
            timetable = filtered_timetable

        if item_id != 'all':
            timetable = {cl_name: cl_sched for cl_name, cl_sched in timetable.items() if cl_name == item_id}

        buffer = exporter.export_excel_classes(timetable, data.get('classes', []), staffs_to_export)
        download_name = f"weekly_class_timetables_{term}_{dept}.xlsx"
    else:
        # For staff-wise view, keep ALL classes in timetable so cross-department teaching is preserved!
        buffer = exporter.export_excel_staffs(timetable, staffs_to_export)
        download_name = f"weekly_staff_timetables_{term}_{dept}.xlsx"
        
    return send_file(
        buffer,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/api/export/pdf', methods=['GET', 'POST'])
def api_export_pdf():
    view_type = request.args.get('type', 'class')
    term = request.args.get('term', 'all')
    dept = request.args.get('dept', 'all')
    item_id = request.args.get('item', 'all')
    
    if request.method == 'POST':
        payload = request.json or {}
        data = payload.get('data', {})
        timetable = payload.get('timetable')
    else:
        data = load_data()
        timetable = data.get('timetable_even') if term == 'even' else data.get('timetable_odd')
        
    if not timetable:
        res = api_generate_internal(input_data=data if request.method == 'POST' else None)
        if res['status'] != 'SUCCESS':
            return f"Error: Cannot export PDF because timetable is infeasible: {res.get('message')}", 400
        timetable = res['timetable_even'] if term == 'even' else res['timetable_odd']

    staffs_to_export = data.get('staffs', [])
    if dept != 'all':
        staffs_to_export = [s for s in staffs_to_export if s.get('department') == dept]

    if item_id != 'all':
        staffs_to_export = [s for s in staffs_to_export if str(s.get('id')) == str(item_id)]

    if view_type == 'class':
        # Filter classes by department for class-wise export
        if dept != 'all':
            filtered_timetable = {}
            for cl_name, cl_sched in timetable.items():
                cl_obj = next((c for c in data.get('classes', []) if c['name'] == cl_name), None)
                if cl_obj and cl_obj.get('department') == dept:
                    filtered_timetable[cl_name] = cl_sched
            timetable = filtered_timetable

        if item_id != 'all':
            timetable = {cl_name: cl_sched for cl_name, cl_sched in timetable.items() if cl_name == item_id}

        buffer = exporter.export_pdf_classes(timetable, data.get('classes', []), staffs_to_export)
        download_name = f"weekly_class_timetables_{term}_{dept}.pdf"
    else:
        # For staff-wise view, keep ALL classes in timetable so cross-department teaching is preserved!
        buffer = exporter.export_pdf_staffs(timetable, staffs_to_export)
        download_name = f"weekly_staff_timetables_{term}_{dept}.pdf"
        
    return send_file(
        buffer,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf"
    )

def diagnose_data_internal(data):
    issues = []
    warnings = []
    
    staffs = data.get('staffs', [])
    classes = data.get('classes', [])
    subjects = {s['code']: s for s in data.get('subjects', [])}
    fixed_slots = data.get('fixed_slots', [])
    departments = data.get('departments', [])
    
    # 1. Individual Staff Workload Limit Check (Direct Assignments)
    for term_key, term_name in [('syllabus', 'Odd Sem'), ('even_syllabus', 'Even Sem')]:
        for s in staffs:
            s_id = str(s.get('id', ''))
            s_name = s.get('name', s_id)
            max_h = s.get('max_hours', 30)
            assigned_classes = []
            assigned_h = 0
            for cl in classes:
                cl_h = sum(it.get('hours', 0) for it in cl.get(term_key, []) if str(it.get('staff_id')) == s_id)
                if cl_h > 0:
                    assigned_h += cl_h
                    assigned_classes.append(f"{cl.get('name')} ({cl_h}h)")
            if assigned_h > max_h:
                overload = assigned_h - max_h
                issues.append({
                    'type': 'STAFF_WORKLOAD_EXCEEDED',
                    'title': f"Faculty Workload Exceeded: {s_name} ({term_name})",
                    'details': f"Faculty member '{s_name}' (ID: {s_id}) is explicitly assigned {assigned_h} hours in {term_name} across classes [{', '.join(assigned_classes)}], but their maximum limit is set to {max_h} hours in Staff Directory! (Overallocated by +{overload}h).",
                    'solution': f"Go to Staff Directory and increase '{s_name}' working hours to at least {assigned_h}h, or reassign {overload}h to another faculty member in Staff Assignments."
                })

    # 2. Lab Subject Duration Validation
    for term_key, term_name in [('syllabus', 'Odd Sem'), ('even_syllabus', 'Even Sem')]:
        for cl in classes:
            for it in cl.get(term_key, []):
                code = it.get('subject_code')
                sub_obj = subjects.get(code)
                if sub_obj and sub_obj.get('type') == 'Lab':
                    hrs = it.get('hours', 0)
                    if hrs < 2:
                        issues.append({
                            'type': 'INVALID_LAB_HOURS',
                            'title': f"Invalid Lab Duration: {sub_obj.get('name', code)} ({cl.get('name')} - {term_name})",
                            'details': f"Practical lab '{sub_obj.get('name', code)}' ({code}) in class '{cl.get('name')}' is allocated only {hrs} hour. Practical labs must be allocated at least 2 consecutive periods (e.g. 2, 3, 4, 5, or 6 hours).",
                            'solution': f"In Classes & Syllabus tab, edit '{cl.get('name')}' and allocate at least 2 consecutive hours for '{sub_obj.get('name', code)}'."
                        })

    # 3. Class Incharge Teaching Requirement Check
    for cl in classes:
        incharge_id = str(cl.get('incharge', ''))
        if incharge_id and incharge_id not in ('', 'None', 'null', 'ST_DUMMY'):
            inch_staff = next((s for s in staffs if str(s.get('id')) == incharge_id), None)
            inch_name = inch_staff.get('name', incharge_id) if inch_staff else incharge_id
            for term_key, term_name in [('syllabus', 'Odd Sem'), ('even_syllabus', 'Even Sem')]:
                syllabus = cl.get(term_key, [])
                if not syllabus:
                    continue
                can_teach = any(
                    it.get('subject_code') in (inch_staff.get('subjects', []) if inch_staff else []) or
                    str(it.get('staff_id')) == incharge_id
                    for it in syllabus
                ) if inch_staff else False
                if not can_teach:
                    issues.append({
                        'type': 'INCHARGE_CANNOT_TEACH',
                        'title': f"Class Incharge Cannot Teach ({cl.get('name')} - {term_name})",
                        'details': f"Faculty '{inch_name}' (ID: {incharge_id}) is designated as Class Incharge for '{cl.get('name')}', but is not eligible to teach ANY subject in this class's {term_name} syllabus! Each class incharge must teach at least 1 hour in their class.",
                        'solution': f"In Staff Directory, edit '{inch_name}' and enable at least one subject taught in '{cl.get('name')}', or change the class incharge in Classes & Syllabus."
                    })

    # 4. Department-Level Staff Capacity vs Subject Demand Check
    dept_capacity = {}
    dept_staff_names = {}
    for d in departments:
        d_staffs = [s for s in staffs if s.get('department') == d]
        dept_capacity[d] = sum(s.get('max_hours', 0) for s in d_staffs)
        dept_staff_names[d] = ", ".join([s['name'] for s in d_staffs])

    for term_key, term_name in [('syllabus', 'Odd Sem'), ('even_syllabus', 'Even Sem')]:
        dept_demand = {d: 0 for d in departments}
        for cl in classes:
            for item in cl.get(term_key, []):
                sub_code = item.get('subject_code')
                hrs = item.get('hours', 0)
                eligible_staffs = [s for s in staffs if sub_code in s.get('subjects', [])]
                if eligible_staffs:
                    primary_dept = eligible_staffs[0].get('department')
                    if primary_dept in dept_demand:
                        dept_demand[primary_dept] += hrs

        for d in departments:
            cap = dept_capacity.get(d, 0)
            dem = dept_demand.get(d, 0)
            if dem > cap:
                deficit = dem - cap
                issues.append({
                    'type': 'DEPARTMENT_CAPACITY_DEFICIT',
                    'title': f"Department Capacity Deficit ({d} - {term_name})",
                    'details': f"Department '{d}' staff pool has a total capacity of {cap}h, but your classes require {dem}h in {term_name}. Short by -{deficit} hours!",
                    'solution': f"Go to Staff Directory and increase working hours for staff in '{d}' (e.g. increase Dr. V. Upendran or other {d} staff by +{deficit}h)."
                })

    # 5. Staff Capacity vs Subject Demand Pool Check
    pool_demand = {}
    for cl in classes:
        for term_key, term_name in [('syllabus', 'Odd Sem'), ('even_syllabus', 'Even Sem')]:
            syllabus = cl.get(term_key, [])
            for item in syllabus:
                sub_code = item.get('subject_code')
                hrs = item.get('hours', 0)
                eligible_staff_ids = tuple(sorted([s['id'] for s in staffs if sub_code in s.get('subjects', [])]))
                
                if not eligible_staff_ids:
                    issues.append({
                        'type': 'NO_STAFF_ASSIGNED',
                        'title': f"Missing Teacher for Subject '{sub_code}'",
                        'details': f"Class '{cl['name']}' requires '{sub_code}', but no teacher in Staff Directory has '{sub_code}' assigned in their eligible subjects!",
                        'solution': f"Go to Staff Directory and edit at least one teacher to enable '{sub_code}'."
                    })
                    continue
                
                pool_key = (eligible_staff_ids, term_key)
                if pool_key not in pool_demand:
                    pool_demand[pool_key] = {
                        'staff_names': [next((s['name'] for s in staffs if s['id'] == sid), str(sid)) for sid in eligible_staff_ids],
                        'max_capacity': sum(next((s['max_hours'] for s in staffs if s['id'] == sid), 0) for sid in eligible_staff_ids),
                        'term_name': term_name,
                        'total_demand': 0,
                        'classes': set()
                    }
                pool_demand[pool_key]['total_demand'] += hrs
                pool_demand[pool_key]['classes'].add(cl['name'])

    for (pool, term_key), info in pool_demand.items():
        capacity = info['max_capacity']
        demand = info['total_demand']
        if demand > capacity:
            overload = demand - capacity
            staff_list = ", ".join(info['staff_names'])
            term_name = info['term_name']
            classes_list = ", ".join(sorted(list(info['classes'])))
            issues.append({
                'type': 'STAFF_CAPACITY_OVERLOAD',
                'title': f"Staff Pool Overload ({term_name})",
                'details': f"Staff Pool [{staff_list}] has a total capacity of {capacity}h, but your classes ({classes_list}) require {demand}h in {term_name}. Overloaded by +{overload} hours!",
                'solution': f"Go to Staff Directory and increase max hours for [{staff_list}] by +{overload}h, or assign an additional teacher to teach those subjects."
            })

    # 6. Fixed Slot Time Collisions Check
    fixed_by_teacher_time = {}
    for fs in fixed_slots:
        c_name = fs.get('class_name')
        sub_code = fs.get('subject_code')
        day = fs.get('day')
        period = fs.get('period')
        term = fs.get('term', 'all')
        
        eligible_staff_ids = [s['id'] for s in staffs if sub_code in s.get('subjects', [])]
        if len(eligible_staff_ids) == 1:
            teacher_id = eligible_staff_ids[0]
            t_name = next((s['name'] for s in staffs if s['id'] == teacher_id), str(teacher_id))
            key = (teacher_id, day, period, term)
            if key not in fixed_by_teacher_time:
                fixed_by_teacher_time[key] = []
            fixed_by_teacher_time[key].append((c_name, sub_code, t_name))

    days_map_name = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
    period_map_name = {0: "Period 1 (09:20-10:10)", 1: "Period 2 (10:10-11:00)", 2: "Period 3 (11:00-11:50)", 3: "Period 4 (12:30-01:10)", 4: "Period 5 (01:10-02:00)"}

    for (t_id, d, p, term), entries in fixed_by_teacher_time.items():
        if len(entries) > 1:
            t_name = entries[0][2]
            class_list = ", ".join([e[0] for e in entries])
            d_name = days_map_name.get(d, f"Day {d}")
            p_name = period_map_name.get(p, f"Period {p+1}")
            issues.append({
                'type': 'FIXED_SLOT_TEACHER_COLLISION',
                'title': f"Fixed Slot Teacher Time Collision",
                'details': f"Teacher '{t_name}' is locked to teach multiple classes ({class_list}) at the EXACT SAME TIME ({d_name} {p_name})!",
                'solution': f"In Fixed Slots tab, unpin the overlapping slot or stagger the period slots across different times (e.g. Mon P1 for A, Mon P2 for B)."
            })

    # 7. Class Syllabus Total Hours Check
    for cl in classes:
        for term_key, term_label in [('syllabus', 'Odd Sem'), ('even_syllabus', 'Even Sem')]:
            total_h = sum(item.get('hours', 0) for item in cl.get(term_key, []))
            if total_h > 30:
                issues.append({
                    'type': 'CLASS_HOURS_EXCEEDED',
                    'title': f"Class Syllabus Exceeds 30 Hours ({cl['name']} - {term_label})",
                    'details': f"Class '{cl['name']}' has {total_h} total allocated hours in {term_label}, exceeding the 30-period limit by +{total_h - 30} hours!",
                    'solution': f"In Class & Syllabus tab, edit '{cl['name']}' and reduce subject hours so total equals exactly 30."
                })

    # 8. Solver Pre-Flight Verification Check
    if not issues:
        for term_key, term_label in [('odd', 'Odd Sem'), ('even', 'Even Sem')]:
            try:
                res = get_timetable_for_term(term_key, input_data=data)
                if res.get('status') != 'SUCCESS':
                    msg = res.get('message', 'No feasible timetable found.')
                    sol = res.get('solution') or "Check staff max working hours, lab durations, and fixed slot timings."
                    err_type = res.get('error_type', 'SOLVER_CONSTRAINT_CONFLICT')
                    issues.append({
                        'type': err_type,
                        'title': f"Scheduling Conflict ({term_label})",
                        'details': f"{msg}",
                        'solution': sol
                    })
            except Exception as e:
                issues.append({
                    'type': 'SOLVER_EXCEPTION',
                    'title': f"Solver Execution Error ({term_label})",
                    'details': str(e),
                    'solution': "Please check your class syllabus allocations and staff max hours."
                })

    return {
        'status': 'FAIL' if len(issues) > 0 else 'PASS',
        'issue_count': len(issues),
        'warning_count': len(warnings),
        'issues': issues,
        'warnings': warnings
    }

@app.route('/api/diagnose', methods=['GET', 'POST'])
def api_diagnose():
    if request.method == 'POST':
        data = request.json
    else:
        data = load_data()
    
    report = diagnose_data_internal(data)
    return jsonify(report)

if __name__ == '__main__':
    import socket
    load_data()
    # Use PORT env variable if set (Render.com sets this automatically)
    env_port = os.environ.get('PORT')
    if env_port:
        selected_port = int(env_port)
    else:
        ports_to_try = [5000, 5001, 5050, 8080]
        selected_port = 5000
        for p in ports_to_try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', p)) != 0:
                    selected_port = p
                    break
    print(f"Starting Flask server on http://127.0.0.1:{selected_port} ...")
    is_production = bool(os.environ.get('RENDER') or os.environ.get('PORT'))
    app.run(debug=not is_production, host='0.0.0.0', port=selected_port)
