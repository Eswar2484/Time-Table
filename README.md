# 🎓 AI-Powered College Timetable Generator

An enterprise-grade web application using **Google OR-Tools CP-SAT** constraint programming to generate 100% conflict-free university timetables automatically. Features a modern, fully responsive UI with glassmorphism design, dual-semester tracking, staff workload assignments, lab split scheduling, fixed slot pinning, and professional PDF/Excel exports.

---

## ✅ Three Scheduling Modes — All Fully Supported

| Mode | Description | Result |
|------|-------------|--------|
| **Auto Only** | Just add departments, staff, subjects, classes & syllabus → click Generate | ✅ Works |
| **Auto + Fixed Slots** | Pre-lock specific subjects to specific days/periods → Generate fills the rest | ✅ Works |
| **Assignments + Fixed Slots** | Manually assign staff to subjects with hours → Generate respects all assignments | ✅ Works |

> **You only need to set up your data once. The solver handles the rest in under 1 second.**

---

## 💻 Cross-Platform Setup & Run

Runs on **Windows**, **macOS**, **Linux**, and **Mobile** (via Wi-Fi or Termux).

### 1. Pre-requisites
- **Python 3.8+** installed
- `pip` updated to latest version

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Server

**macOS / Linux:**
```bash
python3 app.py
```

**Windows (Command Prompt / PowerShell):**
```cmd
python app.py
```

The server auto-selects an available port (`5000`, `5001`, `5050`, or `8080`).  
Open `http://127.0.0.1:<port>` in any browser.

---

## 📱 Mobile Access (Wi-Fi Sharing)

1. Run `python3 app.py` on your computer (connected to Wi-Fi).
2. Note the IP printed in terminal (e.g. `http://192.168.1.15:5000`).
3. On your **phone** (same Wi-Fi), open Chrome/Safari and enter that IP.
4. Full control — create, edit, assign, pin fixed slots, generate & export from your phone!

**Android standalone:** Install [Termux](https://f-droid.org/packages/com.termux/), run `pkg install python`, `pip install -r requirements.txt`, then `python app.py`.  
**iOS standalone:** Use **a-Shell** from the App Store.

---

## 🌟 Feature Highlights

### 1. Staff Workload Assignments
- Manually assign specific teachers to specific subjects per class with weekly hours.
- Split a subject between multiple teachers (e.g. Tamil 5h → Teacher A 2h + Teacher B 3h).
- Live inline validation: **red border + warning** if hours exceed the subject's curriculum limit.
- Toast error notifications (top-center) for constraint violations.

### 2. Dual-Semester Syllabus (Odd & Even)
- Track both Odd (Sems 1, 3, 5) and Even (Sems 2, 4, 6) syllabi per class.
- 1-click switch between Odd/Even views.

### 3. Fixed Slot Pinning
- Lock any subject to a specific day & period.
- Supports pinning for individual classes or **all sections in bulk** (e.g., all UG CS Year 1).
- Solver always respects pinned slots before filling the rest.

### 4. Dynamic Laboratory Split Scheduling
| Lab Hours | Schedule Pattern |
|-----------|-----------------|
| 2h | 1 block of 2 consecutive hours (1 day) |
| 3h | 1 block of 3 consecutive hours (1 day) |
| 4h | 2+2 consecutive hours (2 different days) |
| 5h | 2+3 consecutive hours (2 different days) |
| 6h | 3+3 consecutive hours (2 different days) |

- At most **1 lab per class per day**.

### 5. Language Subject Capping
- Subjects named **Tamil** or **English** are capped at **max 1 hour/day**.

### 6. University Period Timings
| Period | Time |
|--------|------|
| Period 1 | 09:20 – 10:10 |
| Period 2 | 10:10 – 11:00 |
| Period 3 | 11:00 – 11:50 |
| *(Lunch)* | *11:50 – 12:30* |
| Period 4 | 12:30 – 01:10 |
| Period 5 | 01:10 – 02:00 |

### 7. PDF & Excel Export
- **Class-wise**: Sorted by year (1st → 2nd → 3rd → PG). Class name as big heading.
- **Staff-wise**: Sorted by Staff ID. Staff name as big heading + `Name ( Theory + Lab = Total )` hours.
- Export both as PDF (landscape A4) and Excel (.xlsx).

### 8. Bulk Syllabus Copy
- Copy one class's syllabus to all other sections of the same department & year in 1 click.
- UG and PG are strictly isolated from each other.

### 9. Diagnose Tool
- Pre-flight check before generating: detects staff capacity deficits, missing teacher assignments, fixed slot collisions, and hour limit violations.

### 10. Backup & Restore
- Full JSON backup & 1-click restore.
- Excel import template for bulk data entry (departments, staff, subjects, classes).

---

## 📁 Project Files

| File | Purpose |
|------|---------|
| `app.py` | Flask backend — all API routes |
| `solver.py` | CP-SAT timetable solver engine |
| `exporter.py` | PDF & Excel export functions |
| `templates/index.html` | Full single-page frontend UI |
| `data.json` | Live database (auto-saved) |
| `requirements.txt` | Python dependencies |
| `README.md` | This file |

---

## 📦 Requirements

```
flask
ortools
reportlab
openpyxl
```

Install with: `pip install -r requirements.txt`
