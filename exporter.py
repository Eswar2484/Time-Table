import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def extract_staff_timetables(timetable, staffs_data):
    """
    Inverts the class-wise timetable to a staff-wise timetable.
    """
    staff_timetables = {}
    for s in staffs_data:
        s_id = s['id']
        staff_timetables[s_id] = {
            'name': s['name'],
            'department': s['department'],
            'schedule': {str(d): {str(p): None for p in range(5)} for d in range(6)}
        }
        
    for class_name, days in timetable.items():
        for d_str, periods in days.items():
            for p_str, slot in periods.items():
                if slot:
                    t_id = slot['staff_id']
                    if t_id in staff_timetables:
                        staff_timetables[t_id]['schedule'][d_str][p_str] = {
                            'class_name': class_name,
                            'subject_code': slot['subject_code'],
                            'subject_name': slot['subject_name'],
                            'subject_type': slot['subject_type']
                        }
    return staff_timetables

# ==============================================================================
# EXCEL EXPORTERS (PROFESSIONAL SLATE/LIGHT THEME)
# ==============================================================================

def export_excel_classes(timetable, classes_data, staffs_data):
    wb = openpyxl.Workbook()
    wb.remove(wb.active) # Remove default sheet
    
    days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
    
    # Custom Professional Slate Palette
    title_font = Font(name="Segoe UI", size=16, bold=True, color="FFFFFF")
    title_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid") # Slate 900
    
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid") # Slate 700
    
    day_font = Font(name="Segoe UI", size=11, bold=True, color="0F172A") # Slate 900 text
    day_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid") # Slate 100
    
    cell_font = Font(name="Segoe UI", size=10, color="1E293B") # Slate 800 text
    cell_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    # Lab Highlights
    lab_font = Font(name="Segoe UI", size=10, bold=True, color="15803D") # Green 700
    lab_fill = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid") # Green 50
    
    border_side = Side(border_style="thin", color="E2E8F0") # Slate 200 border
    thin_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    for class_name, days in timetable.items():
        ws = wb.create_sheet(title=class_name[:30].replace(':', '-').replace('/', '-'))
        ws.views.sheetView[0].showGridLines = True
        
        # Find class incharge name
        cl_obj = next((c for c in classes_data if c['name'] == class_name), None)
        incharge_name = "None"
        if cl_obj:
            inc_id = cl_obj.get('incharge')
            inc_staff = next((s for s in staffs_data if s['id'] == inc_id), None)
            if inc_staff:
                incharge_name = inc_staff['name']

        # Row 1: Big Class Name
        ws.merge_cells("A1:F1")
        name_cell = ws["A1"]
        name_cell.value = class_name.upper()
        name_cell.font = Font(name="Segoe UI", size=20, bold=True, color="FFFFFF")
        name_cell.fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        name_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 45

        # Row 2: Incharge & Department
        ws.merge_cells("A2:F2")
        info_cell = ws["A2"]
        info_cell.value = f"Class Incharge: {incharge_name}    |    Department: {cl_obj.get('department', '') if cl_obj else ''}"
        info_cell.font = Font(name="Segoe UI", size=11, bold=True, color="475569")
        info_cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        info_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 28

        # Row 3: Headers
        headers = ["DAY / PERIOD", "PERIOD 1\n(09:20-10:10)", "PERIOD 2\n(10:10-11:00)", "PERIOD 3\n(11:00-11:50)", "PERIOD 4\n(12:30-01:10)", "PERIOD 5\n(01:10-02:00)"]
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col_idx)
            cell.value = h
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = align_center
            cell.border = thin_border
        ws.row_dimensions[3].height = 35
        
        # Rows 4-9: Days
        for d in range(6):
            r_idx = 4 + d
            ws.row_dimensions[r_idx].height = 55
            
            day_cell = ws.cell(row=r_idx, column=1)
            day_cell.value = days_map[d]
            day_cell.font = day_font
            day_cell.fill = day_fill
            day_cell.alignment = align_center
            day_cell.border = thin_border
            
            for p in range(5):
                c_idx = 2 + p
                cell = ws.cell(row=r_idx, column=c_idx)
                slot = days[str(d)][str(p)]
                
                if slot:
                    cell.value = f"{slot['subject_code']}\n{slot['subject_name']}\n({slot['staff_name']})"
                    if "Lab" in slot['subject_type']:
                        cell.font = lab_font
                        cell.fill = lab_fill
                    else:
                        cell.font = cell_font
                        cell.fill = cell_fill
                else:
                    cell.value = "-"
                    cell.font = cell_font
                    cell.fill = cell_fill
                    
                cell.alignment = align_center
                cell.border = thin_border
                
        ws.column_dimensions['A'].width = 18
        for col in ['B', 'C', 'D', 'E', 'F']:
            ws.column_dimensions[col].width = 25
            
    if not wb.sheetnames:
        ws = wb.create_sheet(title="Notice")
        ws.cell(row=1, column=1, value="No class timetables found for this term.")
        
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

def export_excel_staffs(timetable, staffs_data):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    
    days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
    staff_timetables = extract_staff_timetables(timetable, staffs_data)
    
    # Custom Professional Slate Palette
    title_font = Font(name="Segoe UI", size=16, bold=True, color="FFFFFF")
    title_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid") # Slate 800
    
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid") # Slate 700
    
    day_font = Font(name="Segoe UI", size=11, bold=True, color="0F172A") # Slate 900 text
    day_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid") # Slate 100
    
    cell_font = Font(name="Segoe UI", size=10, color="1E293B")
    cell_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    lab_font = Font(name="Segoe UI", size=10, bold=True, color="15803D") # Green 700
    lab_fill = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid") # Green 50
    
    border_side = Side(border_style="thin", color="E2E8F0")
    thin_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    # Sort staff by ID ascending
    sorted_staff = sorted(staff_timetables.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else x[0])

    for s_id, s_info in sorted_staff:
        # Calculate theory and lab hours
        theory_hours = 0
        lab_hours = 0
        for d in range(6):
            for p in range(5):
                slot = s_info['schedule'][str(d)][str(p)]
                if slot:
                    if 'Lab' in slot.get('subject_type', ''):
                        lab_hours += 1
                    else:
                        theory_hours += 1
        total_hours = theory_hours + lab_hours

        # Sheet name
        sheet_name = f"{s_info['name'][:25]} ({s_id})"
        sheet_name = sheet_name.replace(':', '-').replace('/', '-').replace('?', '-')
        ws = wb.create_sheet(title=sheet_name)
        ws.views.sheetView[0].showGridLines = True

        # Row 1: Big Staff Name
        ws.merge_cells("A1:F1")
        name_cell = ws["A1"]
        name_cell.value = s_info['name'].upper()
        name_cell.font = Font(name="Segoe UI", size=20, bold=True, color="FFFFFF")
        name_cell.fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        name_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 45

        # Row 2: Department | Hours line
        ws.merge_cells("A2:F2")
        hours_cell = ws["A2"]
        hours_cell.value = f"Department: {s_info['department']}    |    {s_info['name']}  ( {theory_hours} + {lab_hours} = {total_hours} )"
        hours_cell.font = Font(name="Segoe UI", size=11, bold=True, color="475569")
        hours_cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        hours_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 28

        # Row 3: Headers
        headers = ["DAY / PERIOD", "PERIOD 1\n(09:20-10:10)", "PERIOD 2\n(10:10-11:00)", "PERIOD 3\n(11:00-11:50)", "PERIOD 4\n(12:30-01:10)", "PERIOD 5\n(01:10-02:00)"]
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col_idx)
            cell.value = h
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = align_center
            cell.border = thin_border
        ws.row_dimensions[3].height = 35

        # Rows 4-9: Days
        for d in range(6):
            r_idx = 4 + d
            ws.row_dimensions[r_idx].height = 55

            day_cell = ws.cell(row=r_idx, column=1)
            day_cell.value = days_map[d]
            day_cell.font = day_font
            day_cell.fill = day_fill
            day_cell.alignment = align_center
            day_cell.border = thin_border

            for p in range(5):
                c_idx = 2 + p
                cell = ws.cell(row=r_idx, column=c_idx)
                slot = s_info['schedule'][str(d)][str(p)]

                if slot:
                    cell.value = f"{slot['class_name']}\n{slot['subject_code']}\n{slot['subject_name']}"
                    if "Lab" in slot['subject_type']:
                        cell.font = lab_font
                        cell.fill = lab_fill
                    else:
                        cell.font = cell_font
                        cell.fill = cell_fill
                else:
                    cell.value = "FREE"
                    cell.font = Font(name="Segoe UI", size=9, color="94A3B8", italic=True)
                    cell.fill = cell_fill

                cell.alignment = align_center
                cell.border = thin_border

        ws.column_dimensions['A'].width = 18
        for col in ['B', 'C', 'D', 'E', 'F']:
            ws.column_dimensions[col].width = 25
            
    if not wb.sheetnames:
        ws = wb.create_sheet(title="Notice")
        ws.cell(row=1, column=1, value="No staff timetables found for this term.")
        
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ==============================================================================
# PDF EXPORTERS (PROFESSIONAL SLATE/LIGHT PRINT THEME)
# ==============================================================================

def export_pdf_classes(timetable, classes_data, staffs_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    story = []
    styles = getSampleStyleSheet()
    
    # Clean professional slate print styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.HexColor('#0F172A'), # Slate 900
        spaceAfter=5
    )
    dept_title_style = ParagraphStyle(
        'DeptTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        textColor=colors.HexColor('#1E293B'), # Slate 800
        spaceAfter=15,
        alignment=1
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#475569'), # Slate 600
        spaceAfter=15,
        alignment=1
    )
    table_cell_style = ParagraphStyle(
        'TableCellStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        textColor=colors.HexColor('#1E293B'), # Slate 800
        alignment=1,
        leading=10
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white,
        alignment=1,
        leading=11
    )
    
    days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
    
    # Group classes by department
    dept_classes = {}
    for class_name, days in timetable.items():
        cl_obj = next((c for c in classes_data if c['name'] == class_name), None)
        dept = cl_obj.get('department', 'General') if cl_obj else 'General'
        if dept not in dept_classes:
            dept_classes[dept] = []
        dept_classes[dept].append((class_name, days))
        
    sorted_depts = sorted(list(dept_classes.keys()))
    
    for dept_name in sorted_depts:
        # Cover page for department
        story.append(Spacer(1, 150))
        story.append(Paragraph(f"DEPARTMENT OF {dept_name.upper()}", dept_title_style))
        story.append(Paragraph("<b>Weekly Class Timetables</b>", meta_style))
        story.append(PageBreak())
        
        # Sort classes in department by year: 1st year, 2nd year, 3rd year, then PG
        def class_sort_key(x):
            name = x[0].lower()
            if '1' in name and 'pg' not in name: return (0, name)
            if '2' in name and 'pg' not in name: return (1, name)
            if '3' in name and 'pg' not in name: return (2, name)
            if 'pg' in name: return (3, name)
            return (4, name)
        classes_in_dept = sorted(dept_classes[dept_name], key=class_sort_key)
        
        for class_name, days in classes_in_dept:
            # Find class incharge name
            cl_obj = next((c for c in classes_data if c['name'] == class_name), None)
            incharge_name = "None"
            if cl_obj:
                inc_id = cl_obj.get('incharge')
                inc_staff = next((s for s in staffs_data if s['id'] == inc_id), None)
                if inc_staff:
                    incharge_name = inc_staff['name']
                    
            # Class name as big heading, incharge on next line
            story.append(Paragraph(class_name, dept_title_style))
            story.append(Paragraph(f"<b>Class Incharge:</b> {incharge_name} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Department:</b> {dept_name}", meta_style))
            
            headers = [
                Paragraph("<b>DAY / PERIOD</b>", table_header_style),
                Paragraph("<b>PERIOD 1</b><br/>09:20 - 10:10", table_header_style),
                Paragraph("<b>PERIOD 2</b><br/>10:10 - 11:00", table_header_style),
                Paragraph("<b>PERIOD 3</b><br/>11:00 - 11:50", table_header_style),
                Paragraph("<b>PERIOD 4</b><br/>12:30 - 01:10", table_header_style),
                Paragraph("<b>PERIOD 5</b><br/>01:10 - 02:00", table_header_style),
            ]
            
            table_data = [headers]
            
            for d in range(6):
                row = [Paragraph(f"<b>{days_map[d]}</b>", table_cell_style)]
                for p in range(5):
                    slot = days[str(d)][str(p)]
                    if slot:
                        is_lab = "Lab" in slot['subject_type']
                        if is_lab:
                            text = f"<b>{slot['subject_code']}</b><br/>{slot['subject_name']}<br/><i>(Lab - {slot['staff_name']})</i>"
                        else:
                            text = f"<b>{slot['subject_code']}</b><br/>{slot['subject_name']}<br/>({slot['staff_name']})"
                    else:
                        text = "-"
                    row.append(Paragraph(text, table_cell_style))
                table_data.append(row)
                
            col_widths = [92, 138, 138, 138, 138, 138]
            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            t_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')), # Slate 800 header
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')), # Slate 200 grid
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]
            
            # Color days column
            for i in range(1, 7):
                t_style.append(('BACKGROUND', (0, i), (0, i), colors.HexColor('#F1F5F9'))) # Slate 100
                
            # Highlight labs
            for d in range(6):
                for p in range(5):
                    slot = days[str(d)][str(p)]
                    if slot and "Lab" in slot['subject_type']:
                        t_style.append(('BACKGROUND', (p + 1, d + 1), (p + 1, d + 1), colors.HexColor('#F0FDF4'))) # Green 50
                    elif not slot:
                        t_style.append(('BACKGROUND', (p + 1, d + 1), (p + 1, d + 1), colors.HexColor('#F8FAFC'))) # Slate 50
                        
            t.setStyle(TableStyle(t_style))
            story.append(t)
            story.append(PageBreak())
            
    if story:
        story.pop() # Remove final PageBreak
    else:
        story.append(Paragraph("No Class Timetables Available for Selected Term", title_style))
        
    doc.build(story)
    buffer.seek(0)
    return buffer

def export_pdf_staffs(timetable, staffs_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.HexColor('#0F172A'), # Slate 900
        spaceAfter=5
    )
    dept_title_style = ParagraphStyle(
        'DeptTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        textColor=colors.HexColor('#1E293B'), # Slate 800
        spaceAfter=15,
        alignment=1
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#475569'), # Slate 600
        spaceAfter=15,
        alignment=1
    )
    table_cell_style = ParagraphStyle(
        'TableCellStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        textColor=colors.HexColor('#1E293B'),
        alignment=1,
        leading=10
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white,
        alignment=1,
        leading=11
    )
    
    days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
    staff_timetables = extract_staff_timetables(timetable, staffs_data)
    
    # Group staff timetables by department
    dept_staffs = {}
    for s_id, s_info in staff_timetables.items():
        dept = s_info.get('department', 'General')
        if dept not in dept_staffs:
            dept_staffs[dept] = []
        dept_staffs[dept].append((s_id, s_info))
        
    sorted_depts = sorted(list(dept_staffs.keys()))
    
    for dept_name in sorted_depts:
        # Cover page for department
        story.append(Spacer(1, 150))
        story.append(Paragraph(f"DEPARTMENT OF {dept_name.upper()}", dept_title_style))
        story.append(Paragraph("<b>Weekly Staff Timetables</b>", meta_style))
        story.append(PageBreak())
        
        # Sort staff in department by staff ID ascending
        staff_in_dept = sorted(dept_staffs[dept_name], key=lambda x: int(x[0]) if str(x[0]).isdigit() else x[0])
        
        for s_id, s_info in staff_in_dept:
            # Calculate theory and lab hours from the schedule
            theory_hours = 0
            lab_hours = 0
            for d in range(6):
                for p in range(5):
                    slot = s_info['schedule'][str(d)][str(p)]
                    if slot:
                        if 'Lab' in slot.get('subject_type', ''):
                            lab_hours += 1
                        else:
                            theory_hours += 1
            total_hours = theory_hours + lab_hours
            hours_str = f"{theory_hours}+{lab_hours}={total_hours}"
            
            # Staff name as big heading, hours on next line
            story.append(Paragraph(s_info['name'], dept_title_style))
            story.append(Paragraph(
                f"<b>Department:</b> {s_info['department']} &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"{s_info['name']} &nbsp;( {theory_hours} + {lab_hours} = {total_hours} )",
                meta_style
            ))
            
            headers = [
                Paragraph("<b>DAY / PERIOD</b>", table_header_style),
                Paragraph("<b>PERIOD 1</b><br/>09:20 - 10:10", table_header_style),
                Paragraph("<b>PERIOD 2</b><br/>10:10 - 11:00", table_header_style),
                Paragraph("<b>PERIOD 3</b><br/>11:00 - 11:50", table_header_style),
                Paragraph("<b>PERIOD 4</b><br/>12:30 - 01:10", table_header_style),
                Paragraph("<b>PERIOD 5</b><br/>01:10 - 02:00", table_header_style),
            ]
            
            table_data = [headers]
            
            for d in range(6):
                row = [Paragraph(f"<b>{days_map[d]}</b>", table_cell_style)]
                for p in range(5):
                    slot = s_info['schedule'][str(d)][str(p)]
                    if slot:
                        is_lab = "Lab" in slot['subject_type']
                        if is_lab:
                            text = f"<b>{slot['class_name']}</b><br/>{slot['subject_code']}<br/><i>(Lab - {slot['subject_name']})</i>"
                        else:
                            text = f"<b>{slot['class_name']}</b><br/>{slot['subject_code']}<br/>{slot['subject_name']}"
                    else:
                        text = "<i>FREE</i>"
                    row.append(Paragraph(text, table_cell_style))
                table_data.append(row)
                
            col_widths = [92, 138, 138, 138, 138, 138]
            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            t_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')), # Slate 800 Header
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]
            
            # Color days column
            for i in range(1, 7):
                t_style.append(('BACKGROUND', (0, i), (0, i), colors.HexColor('#F1F5F9'))) # Slate 100
                
            # Highlight labs and free slots
            for d in range(6):
                for p in range(5):
                    slot = s_info['schedule'][str(d)][str(p)]
                    if slot and "Lab" in slot['subject_type']:
                        t_style.append(('BACKGROUND', (p + 1, d + 1), (p + 1, d + 1), colors.HexColor('#F0FDF4'))) # Green 50
                    elif not slot:
                        t_style.append(('BACKGROUND', (p + 1, d + 1), (p + 1, d + 1), colors.HexColor('#F8FAFC'))) # Slate 50
                        
            t.setStyle(TableStyle(t_style))
            story.append(t)
            story.append(PageBreak())
            
    if story:
        story.pop()
    else:
        story.append(Paragraph("No Staff Timetables Available for Selected Term", title_style))
        
    doc.build(story)
    buffer.seek(0)
    return buffer
