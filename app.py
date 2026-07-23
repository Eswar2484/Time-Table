import os
import json
from flask import Flask, jsonify, request, render_template, send_file, send_from_directory
import solver
import exporter

app = Flask(__name__, static_folder='static')

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

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')

# Full pre-seeded default dataset for resetting
DEFAULT_DATA = {
  "departments": ["Computer Science", "Physics", "Commerce", "Language"],
  "staffs": [
    {
      "id": "ST001",
      "name": "Dr. Ramesh",
      "department": "Computer Science",
      "max_hours": 24,
      "subjects": ["CS101", "CS102", "CS201", "CS202", "CS203", "CS205", "CS307", "CSPG101", "CSPG104", "CS301", "CS302", "CS306", "CSPG301", "CSPG106"]
    },
    {
      "id": "ST002",
      "name": "Dr. Priya",
      "department": "Computer Science",
      "max_hours": 24,
      "subjects": ["CS203", "CS301", "CS305", "CSPG102", "CSPG105", "CS307", "CS308", "CSPG201", "CSPG204", "CSPG302"]
    },
    {
      "id": "ST003",
      "name": "Mr. Karthik",
      "department": "Computer Science",
      "max_hours": 24,
      "subjects": ["CS302", "CS303", "CS304", "CSPG103", "CSPG201", "CS309", "CS310", "CSPG205", "CSPG303"]
    },
    {
      "id": "ST004",
      "name": "Mrs. Devi",
      "department": "Computer Science",
      "max_hours": 20,
      "subjects": ["CS101", "CS102", "CS202", "CSPG202", "CSPG204", "CS204", "CS205", "CSPG202"]
    },
    {
      "id": "ST005",
      "name": "Dr. Anand",
      "department": "Computer Science",
      "max_hours": 20,
      "subjects": ["CS303", "CS304", "CSPG203", "CSPG205", "CS206", "CS304", "CSPG203", "CSPG206"]
    },
    {
      "id": "ST006",
      "name": "Dr. Krishnan",
      "department": "Physics",
      "max_hours": 24,
      "subjects": ["PH101", "PH102", "PHPG101", "PHPG103", "PH201", "PH202"]
    },
    {
      "id": "ST007",
      "name": "Dr. Radha",
      "department": "Physics",
      "max_hours": 24,
      "subjects": ["PHPG102", "PHPG104", "PHPG105", "NME02", "PHPG201", "PHPG202"]
    },
    {
      "id": "ST008",
      "name": "Mr. Vignesh",
      "department": "Physics",
      "max_hours": 20,
      "subjects": ["PH101", "PH102", "PHPG103", "PHPG105", "PH201", "PH202"]
    },
    {
      "id": "ST009",
      "name": "Dr. Raman",
      "department": "Commerce",
      "max_hours": 24,
      "subjects": ["CO101", "CO102", "CO103", "CO104"]
    },
    {
      "id": "ST010",
      "name": "Mrs. Geetha",
      "department": "Commerce",
      "max_hours": 20,
      "subjects": ["CO101", "CO102", "CO103", "CO104"]
    },
    {
      "id": "ST011",
      "name": "Mr. Selvam",
      "department": "Language",
      "max_hours": 24,
      "subjects": ["TAM01", "TAM02", "TAM03", "TAM04"]
    },
    {
      "id": "ST012",
      "name": "Mrs. Kayal",
      "department": "Language",
      "max_hours": 24,
      "subjects": ["TAM01", "TAM02", "TAM03", "TAM04"]
    },
    {
      "id": "ST013",
      "name": "Mr. John",
      "department": "Language",
      "max_hours": 24,
      "subjects": ["ENG01", "ENG02", "ENG03", "ENG04"]
    },
    {
      "id": "ST014",
      "name": "Mrs. Mary",
      "department": "Language",
      "max_hours": 24,
      "subjects": ["ENG01", "ENG02", "ENG03", "ENG04"]
    },
    {
      "id": "ST015",
      "name": "Mr. Balaji",
      "department": "Computer Science",
      "max_hours": 20,
      "subjects": ["NME01", "CS102", "CS202", "CS204", "CS206", "CS305", "NME03"]
    },
    {
      "id": "ST016",
      "name": "Mrs. Sudha",
      "department": "Computer Science",
      "max_hours": 20,
      "subjects": ["CS301", "CS305", "CSPG104", "CSPG204", "CS307", "CS308", "CSPG304", "CSPG305", "CSPG401"]
    },
    {
      "id": "ST017",
      "name": "Dr. Suresh",
      "department": "Physics",
      "max_hours": 20,
      "subjects": ["PHPG101", "PHPG102", "PHPG103", "NME02", "PHPG201", "PHPG202", "NME04"]
    },
    {
      "id": "ST018",
      "name": "Mr. Rahim",
      "department": "Computer Science",
      "max_hours": 20,
      "subjects": ["CS201", "CS203", "CSPG102", "CSPG205", "CS205", "CSPG401", "CSPG402"]
    }
  ],
  "subjects": [
    {"code": "TAM01", "name": "Tamil I", "department": "Language", "type": "Theory"},
    {"code": "TAM02", "name": "Tamil II", "department": "Language", "type": "Theory"},
    {"code": "TAM03", "name": "Tamil III", "department": "Language", "type": "Theory"},
    {"code": "TAM04", "name": "Tamil IV", "department": "Language", "type": "Theory"},
    {"code": "ENG01", "name": "English I", "department": "Language", "type": "Theory"},
    {"code": "ENG02", "name": "English II", "department": "Language", "type": "Theory"},
    {"code": "ENG03", "name": "English III", "department": "Language", "type": "Theory"},
    {"code": "ENG04", "name": "English IV", "department": "Language", "type": "Theory"},
    {"code": "CS101", "name": "Python Programming", "department": "Computer Science", "type": "Theory"},
    {"code": "CS102", "name": "Python Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CS201", "name": "Java Programming", "department": "Computer Science", "type": "Theory"},
    {"code": "CS202", "name": "Java & DS Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CS203", "name": "Data Structures", "department": "Computer Science", "type": "Theory"},
    {"code": "CS204", "name": "Data Structures Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CS205", "name": "Database Management", "department": "Computer Science", "type": "Theory"},
    {"code": "CS206", "name": "DBMS Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CS301", "name": "Web Technology", "department": "Computer Science", "type": "Theory"},
    {"code": "CS302", "name": "Software Engineering", "department": "Computer Science", "type": "Theory"},
    {"code": "CS303", "name": "Database Management Systems", "department": "Computer Science", "type": "Theory"},
    {"code": "CS304", "name": "Computer Networks", "department": "Computer Science", "type": "Theory"},
    {"code": "CS305", "name": "Web & DBMS Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CS306", "name": "Operating Systems", "department": "Computer Science", "type": "Theory"},
    {"code": "CS307", "name": "Cloud Computing", "department": "Computer Science", "type": "Theory"},
    {"code": "CS308", "name": "Data Science", "department": "Computer Science", "type": "Theory"},
    {"code": "CS309", "name": "UG Project Work", "department": "Computer Science", "type": "Theory"},
    {"code": "CS310", "name": "Cyber Security", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG101", "name": "Advanced Algorithms", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG102", "name": "Machine Learning", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG103", "name": "Distributed Systems", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG104", "name": "Data Science Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CSPG105", "name": "ML Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CSPG106", "name": "Advanced OS", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG201", "name": "Deep Learning", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG202", "name": "Cloud Computing", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG203", "name": "Cryptography", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG204", "name": "Deep Learning Lab", "department": "Computer Science", "type": "Lab"},
    {"code": "CSPG205", "name": "PG Project Work", "department": "Computer Science", "type": "Lab"},
    {"code": "CSPG206", "name": "Network Security", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG301", "name": "Big Data Analytics", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG302", "name": "Internet of Things", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG303", "name": "PG Lab 3", "department": "Computer Science", "type": "Lab"},
    {"code": "CSPG304", "name": "Elective I", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG305", "name": "Elective II", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG401", "name": "Research Methodology", "department": "Computer Science", "type": "Theory"},
    {"code": "CSPG402", "name": "Seminar & Viva", "department": "Computer Science", "type": "Theory"},
    {"code": "PH101", "name": "Mechanics", "department": "Physics", "type": "Theory"},
    {"code": "PH102", "name": "Physics Lab I", "department": "Physics", "type": "Lab"},
    {"code": "PH201", "name": "Physics II", "department": "Physics", "type": "Theory"},
    {"code": "PH202", "name": "Physics Lab II", "department": "Physics", "type": "Lab"},
    {"code": "PHPG101", "name": "Classical Mechanics", "department": "Physics", "type": "Theory"},
    {"code": "PHPG102", "name": "Quantum Mechanics", "department": "Physics", "type": "Theory"},
    {"code": "PHPG103", "name": "Advanced Physics Lab", "department": "Physics", "type": "Lab"},
    {"code": "PHPG104", "name": "Electrodynamics", "department": "Physics", "type": "Theory"},
    {"code": "PHPG105", "name": "Electronics Lab", "department": "Physics", "type": "Lab"},
    {"code": "PHPG201", "name": "Classical Electrodynamics", "department": "Physics", "type": "Theory"},
    {"code": "PHPG202", "name": "Advanced Physics Lab II", "department": "Physics", "type": "Lab"},
    {"code": "CO101", "name": "Financial Accounting", "department": "Commerce", "type": "Theory"},
    {"code": "CO102", "name": "Business Management", "department": "Commerce", "type": "Theory"},
    {"code": "CO103", "name": "Commerce Elective", "department": "Commerce", "type": "Theory"},
    {"code": "CO104", "name": "Allied Commerce", "department": "Commerce", "type": "Theory"},
    {"code": "NME01", "name": "Office Automation", "department": "Computer Science", "type": "Theory"},
    {"code": "NME02", "name": "Basic Physics", "department": "Physics", "type": "Theory"},
    {"code": "NME03", "name": "NME 03", "department": "Computer Science", "type": "Theory"},
    {"code": "NME04", "name": "NME 04", "department": "Physics", "type": "Theory"}
  ],
  "classes": [
    {
      "name": "1st UG CS - A (Sem 1)",
      "department": "Computer Science",
      "level": "UG",
      "semester": 1,
      "incharge": "ST001",
      "syllabus": [
        {"subject_code": "CS101", "hours": 5},
        {"subject_code": "CS102", "hours": 4},
        {"subject_code": "TAM01", "hours": 6},
        {"subject_code": "ENG01", "hours": 6},
        {"subject_code": "CO101", "hours": 5},
        {"subject_code": "NME01", "hours": 4}
      ]
    },
    {
      "name": "1st UG CS - A (Sem 2)",
      "department": "Computer Science",
      "level": "UG",
      "semester": 2,
      "incharge": "ST001",
      "syllabus": [
        {"subject_code": "CS201", "hours": 5},
        {"subject_code": "CS202", "hours": 4},
        {"subject_code": "TAM02", "hours": 6},
        {"subject_code": "ENG02", "hours": 6},
        {"subject_code": "CO102", "hours": 5},
        {"subject_code": "NME02", "hours": 4}
      ]
    },
    {
      "name": "2nd UG CS - A (Sem 3)",
      "department": "Computer Science",
      "level": "UG",
      "semester": 3,
      "incharge": "ST001",
      "syllabus": [
        {"subject_code": "CS203", "hours": 5},
        {"subject_code": "CS204", "hours": 4},
        {"subject_code": "TAM03", "hours": 6},
        {"subject_code": "ENG03", "hours": 6},
        {"subject_code": "CO103", "hours": 5},
        {"subject_code": "NME03", "hours": 4}
      ]
    },
    {
      "name": "2nd UG CS - A (Sem 4)",
      "department": "Computer Science",
      "level": "UG",
      "semester": 4,
      "incharge": "ST001",
      "syllabus": [
        {"subject_code": "CS205", "hours": 5},
        {"subject_code": "CS206", "hours": 4},
        {"subject_code": "TAM04", "hours": 6},
        {"subject_code": "ENG04", "hours": 6},
        {"subject_code": "CO104", "hours": 5},
        {"subject_code": "NME04", "hours": 4}
      ]
    },
    {
      "name": "3rd UG CS - A (Sem 5)",
      "department": "Computer Science",
      "level": "UG",
      "semester": 5,
      "incharge": "ST001",
      "syllabus": [
        {"subject_code": "CS301", "hours": 5},
        {"subject_code": "CS302", "hours": 5},
        {"subject_code": "CS303", "hours": 6},
        {"subject_code": "CS304", "hours": 6},
        {"subject_code": "CS305", "hours": 4}
      ]
    },
    {
      "name": "3rd UG CS - A (Sem 6)",
      "department": "Computer Science",
      "level": "UG",
      "semester": 6,
      "incharge": "ST001",
      "syllabus": [
        {"subject_code": "CS307", "hours": 5},
        {"subject_code": "CS308", "hours": 5},
        {"subject_code": "CS309", "hours": 8},
        {"subject_code": "CS310", "hours": 6},
        {"subject_code": "CS305", "hours": 4}
      ]
    },
    {
      "name": "1st PG CS - A (Sem 1)",
      "department": "Computer Science",
      "level": "PG",
      "semester": 1,
      "incharge": "ST016",
      "syllabus": [
        {"subject_code": "CSPG101", "hours": 6},
        {"subject_code": "CSPG102", "hours": 6},
        {"subject_code": "CSPG103", "hours": 6},
        {"subject_code": "CSPG104", "hours": 6},
        {"subject_code": "CSPG105", "hours": 6}
      ]
    },
    {
      "name": "1st PG CS - A (Sem 2)",
      "department": "Computer Science",
      "level": "PG",
      "semester": 2,
      "incharge": "ST016",
      "syllabus": [
        {"subject_code": "CSPG201", "hours": 6},
        {"subject_code": "CSPG202", "hours": 6},
        {"subject_code": "CSPG203", "hours": 6},
        {"subject_code": "CSPG204", "hours": 6},
        {"subject_code": "CSPG106", "hours": 6}
      ]
    },
    {
      "name": "2nd PG CS - A (Sem 3)",
      "department": "Computer Science",
      "level": "PG",
      "semester": 3,
      "incharge": "ST016",
      "syllabus": [
        {"subject_code": "CSPG301", "hours": 5},
        {"subject_code": "CSPG302", "hours": 5},
        {"subject_code": "CSPG303", "hours": 6},
        {"subject_code": "CSPG304", "hours": 5},
        {"subject_code": "CSPG305", "hours": 5}
      ]
    },
    {
      "name": "2nd PG CS - A (Sem 4)",
      "department": "Computer Science",
      "level": "PG",
      "semester": 4,
      "incharge": "ST016",
      "syllabus": [
        {"subject_code": "CSPG205", "hours": 12},
        {"subject_code": "CSPG401", "hours": 5},
        {"subject_code": "CSPG402", "hours": 5}
      ]
    },
    {
      "name": "1st UG Physics - A (Sem 1)",
      "department": "Physics",
      "level": "UG",
      "semester": 1,
      "incharge": "ST006",
      "syllabus": [
        {"subject_code": "PH101", "hours": 5},
        {"subject_code": "PH102", "hours": 4},
        {"subject_code": "TAM01", "hours": 6},
        {"subject_code": "ENG01", "hours": 6},
        {"subject_code": "CS101", "hours": 5},
        {"subject_code": "NME01", "hours": 4}
      ]
    },
    {
      "name": "1st UG Physics - A (Sem 2)",
      "department": "Physics",
      "level": "UG",
      "semester": 2,
      "incharge": "ST006",
      "syllabus": [
        {"subject_code": "PH201", "hours": 5},
        {"subject_code": "PH202", "hours": 4},
        {"subject_code": "TAM02", "hours": 6},
        {"subject_code": "ENG02", "hours": 6},
        {"subject_code": "CS201", "hours": 5},
        {"subject_code": "NME02", "hours": 4}
      ]
    },
    {
      "name": "1st PG Physics - A (Sem 1)",
      "department": "Physics",
      "level": "PG",
      "semester": 1,
      "incharge": "ST007",
      "syllabus": [
        {"subject_code": "PHPG101", "hours": 6},
        {"subject_code": "PHPG102", "hours": 6},
        {"subject_code": "PHPG103", "hours": 6},
        {"subject_code": "PHPG104", "hours": 6},
        {"subject_code": "PHPG105", "hours": 6}
      ]
    },
    {
      "name": "1st PG Physics - A (Sem 2)",
      "department": "Physics",
      "level": "PG",
      "semester": 2,
      "incharge": "ST007",
      "syllabus": [
        {"subject_code": "PHPG201", "hours": 6},
        {"subject_code": "PHPG202", "hours": 6},
        {"subject_code": "PHPG103", "hours": 6},
        {"subject_code": "PHPG104", "hours": 6},
        {"subject_code": "PHPG105", "hours": 6}
      ]
    }
  ]
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
        # Clear cached and saved timetable since inputs changed
        if 'timetable' in new_data:
            new_data['timetable'] = None
        save_data(new_data)
        GENERATED_TIMETABLE = None
        return jsonify({"status": "SUCCESS"})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    global GENERATED_TIMETABLE
    # Clear timetable fromDEFAULT_DATA copies
    data = dict(DEFAULT_DATA)
    if 'timetable' in data:
        data['timetable'] = None
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
                
        save_data(parsed)
        GENERATED_TIMETABLE = parsed.get('timetable')
        return jsonify({"status": "SUCCESS"})
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

def get_timetable_for_term(term):
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

def api_generate_internal():
    # 1. Generate Odd
    res_odd = get_timetable_for_term('odd')
    if res_odd['status'] != 'SUCCESS':
        return res_odd
        
    # 2. Generate Even
    res_even = get_timetable_for_term('even')
    if res_even['status'] != 'SUCCESS':
        return res_even
        
    # Save combined timetables in data.json for persistence
    data = load_data()
    data['timetable_odd'] = res_odd['timetable']
    data['timetable_even'] = res_even['timetable']
    data['timetable'] = res_odd['timetable'] # backward compatibility
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
    result = api_generate_internal()
    if result.get('status') == 'SUCCESS':
        GENERATED_TIMETABLE = result.get('timetable_odd') or result.get('timetable_even') or {}
        result['timetable'] = GENERATED_TIMETABLE
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

@app.route('/api/export/excel', methods=['GET'])
def api_export_excel():
    view_type = request.args.get('type', 'class')
    term = request.args.get('term', 'all')
    dept = request.args.get('dept', 'all')
    data = load_data()
    
    timetable = data.get('timetable_even') if term == 'even' else data.get('timetable_odd')
    if not timetable:
        res = api_generate_internal()
        if res['status'] != 'SUCCESS':
            return f"Error: Cannot export Excel because timetable is infeasible: {res.get('message')}", 400
        timetable = res['timetable_even'] if term == 'even' else res['timetable_odd']

    # Filter by department
    if dept != 'all':
        filtered_timetable = {}
        for cl_name, cl_sched in timetable.items():
            cl_obj = next((c for c in data.get('classes', []) if c['name'] == cl_name), None)
            if cl_obj and cl_obj.get('department') == dept:
                filtered_timetable[cl_name] = cl_sched
        timetable = filtered_timetable

    staffs_to_export = data.get('staffs', [])
    if dept != 'all':
        staffs_to_export = [s for s in staffs_to_export if s.get('department') == dept]

    if view_type == 'class':
        buffer = exporter.export_excel_classes(timetable, data.get('classes', []), staffs_to_export)
        download_name = f"weekly_class_timetables_{term}_{dept}.xlsx"
    else:
        buffer = exporter.export_excel_staffs(timetable, staffs_to_export)
        download_name = f"weekly_staff_timetables_{term}_{dept}.xlsx"
        
    return send_file(
        buffer,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/api/export/pdf', methods=['GET'])
def api_export_pdf():
    view_type = request.args.get('type', 'class')
    term = request.args.get('term', 'all')
    dept = request.args.get('dept', 'all')
    data = load_data()
    
    timetable = data.get('timetable_even') if term == 'even' else data.get('timetable_odd')
    if not timetable:
        res = api_generate_internal()
        if res['status'] != 'SUCCESS':
            return f"Error: Cannot export PDF because timetable is infeasible: {res.get('message')}", 400
        timetable = res['timetable_even'] if term == 'even' else res['timetable_odd']

    # Filter by department
    if dept != 'all':
        filtered_timetable = {}
        for cl_name, cl_sched in timetable.items():
            cl_obj = next((c for c in data.get('classes', []) if c['name'] == cl_name), None)
            if cl_obj and cl_obj.get('department') == dept:
                filtered_timetable[cl_name] = cl_sched
        timetable = filtered_timetable

    staffs_to_export = data.get('staffs', [])
    if dept != 'all':
        staffs_to_export = [s for s in staffs_to_export if s.get('department') == dept]

    if view_type == 'class':
        buffer = exporter.export_pdf_classes(timetable, data.get('classes', []), staffs_to_export)
        download_name = f"weekly_class_timetables_{term}_{dept}.pdf"
    else:
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
    
    # 1. Department-Level Staff Capacity vs Subject Demand Check
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

    # 2. Staff Capacity vs Subject Demand Pool Check
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

    # 3. Fixed Slot Time Collisions Check
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

    # 4. Class Syllabus Total Hours Check
    for cl in classes:
        for term_key, term_label in [('syllabus', 'Odd Sem'), ('even_syllabus', 'Even Sem')]:
            total_h = sum(item.get('hours', 0) for item in cl.get(term_key, []))
            if total_h > 30:
                issues.append({
                    'type': 'CLASS_HOURS_EXCEEDED',
                    'title': f"Class Syllabus Exceeds 30 Hours ({cl['name']} - {term_label})",
                    'details': f"Class '{cl['name']}' has {total_h} total allocated hours in {term_label}, exceeding the 30-period limit!",
                    'solution': f"In Class & Syllabus tab, edit '{cl['name']}' and reduce subject hours so total equals 30."
                })

    # 5. Solver Pre-Flight Verification Check
    if not issues:
        try:
            solver_res = solver.solve_timetable_scalable(data)
            if solver_res.get('status') != 'SUCCESS':
                msg = solver_res.get('message', 'No feasible timetable found.')
                issues.append({
                    'type': 'SOLVER_INFEASIBLE_SCHEDULE',
                    'title': "Solver Constraint Conflict Detected",
                    'details': f"The mathematical solver engine found a scheduling conflict: {msg}",
                    'solution': "Go to Staff Directory and increase staff max working hours, or check if fixed slots block lab time blocks."
                })
        except Exception as e:
            issues.append({
                'type': 'SOLVER_EXCEPTION',
                'title': "Solver Execution Warning",
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
