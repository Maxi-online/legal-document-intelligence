from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
import json
from io import BytesIO
from datetime import datetime

def export_to_excel(data: list, task_id: str) -> bytes:
    'Export data to Excel'
    wb = Workbook()
    ws = wb.active
    ws.title = 'Search results'
    
    # Headings (conformance of TK of 3.4)
    headers = [
        'Case number',
        'Court',
        'Date of act',
        'Loading date',
        'Type of reference',
        'Classification',
        'Relevance',
        'Context (fragment)',
        'Parties',
        'Reference to act'
    ]
    
    # Headings
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    
    # Record the headlines.
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Record data
    for row_idx, item in enumerate(data, 2):
        ws.cell(row=row_idx, column=1, value=item.get("case_number", ""))
        ws.cell(row=row_idx, column=2, value=item.get("court", ""))
        ws.cell(row=row_idx, column=3, value=item.get("date", ""))
        ws.cell(row=row_idx, column=4, value=item.get("ingested_at", ""))
        ws.cell(row=row_idx, column=5, value=item.get("type_of_mention", "") or item.get("classification", ""))
        ws.cell(row=row_idx, column=6, value=item.get("classification", ""))
        ws.cell(row=row_idx, column=7, value=f"{item.get('relevance_score', 0) * 100:.1f}%" if item.get('relevance_score') else "")
        ws.cell(row=row_idx, column=8, value=item.get("context", "")[:200])  # Limiting length
        ws.cell(row=row_idx, column=9, value=item.get("parties", "")[:200])
        
        # Add hyperlink to act (T3.5 - click links)
        act_url = item.get("act_url", "")
        if act_url:
            cell = ws.cell(row=row_idx, column=10, value='Open')
            cell.hyperlink = act_url
            cell.font = Font(color="0000FF", underline="single")
    
    # Auto-sampling of column width
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + col)].width = 20
    
    # Keep it in bytes.
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output.getvalue()

def export_to_pdf(data: list, task_id: str) -> bytes:
    'Export data to PDF'
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    styles = getSampleStyleSheet()
    story = []
    
    # Heading
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#366092'),
        alignment=1,  # Centralization
        spaceAfter=30,
    )
    
    title = Paragraph(f"DocumentIntelligence<br/> Target: {task_id}", title_style)
    story.append(title)
    story.append(Spacer(1, 12))
    
    # Table (conformance of TK of 3.4)
    table_data = [['Case number', 'Court', 'Date of act', 'Loading date', 'Type of reference', 'Classification', 'Relevance']]
    
    for item in data:
        table_data.append([
            item.get("case_number", ""),
            item.get("court", "")[:30],  # Limiting length
            item.get("date", "")[:10] if item.get("date") else "",
            item.get("ingested_at", "")[:10] if item.get("ingested_at") else "",
            item.get("type_of_mention", "") or item.get("classification", ""),
            item.get("classification", ""),
            f"{item.get('relevance_score', 0) * 100:.1f}%" if item.get('relevance_score') else "",
        ])
    
    table = Table(table_data, colWidths=[1.4*inch, 1.8*inch, 0.9*inch, 0.9*inch, 1.3*inch, 1.3*inch, 0.9*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#366092')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 12))
    
    # Details on each case
    for idx, item in enumerate(data[:10], 1):  # Limit to 10 for PDF
        story.append(Paragraph(f"<b> Case {idx}: {item.get('case_number', '')}</b>", styles['Heading2']))
        story.append(Paragraph(f"<b> Court:</b> {item.get('court', '')}", styles['Normal']))
        story.append(Paragraph(f"<b>Date:</b> {item.get('date', '')}", styles['Normal']))
        story.append(Paragraph(f"<b> Classification:</b> {item.get('classification', '')}", styles['Normal']))
        story.append(Paragraph(f"<b> Context:</b> {item.get('context', '')[:300]}", styles['Normal']))
        if item.get("act_url"):
            story.append(Paragraph(f"<b> Reference:</b> <a href='{item.get('act_url')}'>{item.get('act_url')}</a>", styles['Normal']))
        story.append(Spacer(1, 12))
    
    doc.build(story)
    buffer.seek(0)
    
    return buffer.getvalue()

def export_to_json(data: list, task_id: str) -> bytes:
    'Data Export to JSON'
    export_data = {
        "task_id": task_id,
        "exported_at": datetime.now().isoformat(),
        "total": len(data),
        "results": data
    }
    
    json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
    return json_str.encode('utf-8')
