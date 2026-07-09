import os
import json
import time
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.graphics.shapes import Drawing, String, Rect
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker

from config import db
from models import PumpLog, TDSData, PHData, TemperatureHumidityData, PhotoRecord, SensorLimits

def load_system_config():
    config_path = "system_config.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return json.load(f)
    return {}

def generate_growth_cycle_report(start_date, end_date):
    """
    Generates a professional engineering report.
    start_date and end_date should be datetime objects.
    Returns BytesIO buffer of the PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=30
    )
    subtitle_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=40,
        alignment=1 # Center
    )
    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=15,
        spaceBefore=20
    )
    normal_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#334155'),
        spaceAfter=10,
        leading=16
    )
    alert_style = ParagraphStyle(
        'AlertText',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#b91c1c'),
        spaceAfter=10,
        leading=16,
        fontName='Helvetica-Bold'
    )

    # ---------------- COVER PAGE ----------------
    elements.append(Spacer(1, 100))
    elements.append(Paragraph("HydroAgrix Systems", subtitle_style))
    elements.append(Paragraph("Growth Cycle Engineering Report", title_style))
    elements.append(Paragraph("Automated Dosing & Telemetry Analysis", subtitle_style))
    elements.append(Spacer(1, 50))
    
    cover_data = [
        ["Report Generated:", datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ["Period Start:", start_date.strftime('%Y-%m-%d %H:%M')],
        ["Period End:", end_date.strftime('%Y-%m-%d %H:%M')]
    ]
    t_cover = Table(cover_data, colWidths=[150, 200])
    t_cover.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#334155')),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(t_cover)
    elements.append(PageBreak())

    # Fetch configuration & limits
    config = load_system_config()
    pumps_config = config.get("pumps", {})
    flow_rates = {
        1: float(pumps_config.get("1", {}).get("flow_rate_ml_per_sec", 0.6167)),
        2: float(pumps_config.get("2", {}).get("flow_rate_ml_per_sec", 0.6167)),
        3: float(pumps_config.get("3", {}).get("flow_rate_ml_per_sec", 0.6167)),
        4: float(pumps_config.get("4", {}).get("flow_rate_ml_per_sec", 0.6167))
    }

    l_tds = SensorLimits.query.filter_by(sensor_type="tds").first()
    l_ph = SensorLimits.query.filter_by(sensor_type="ph").first()
    target_tds = (l_tds.min_value + l_tds.max_value) / 2.0 if l_tds else 1.5
    target_ph = (l_ph.min_value + l_ph.max_value) / 2.0 if l_ph else 6.0

    # Process Data
    tds_data = TDSData.query.filter(TDSData.date >= start_date, TDSData.date <= end_date).order_by(TDSData.date).all()
    ph_data = PHData.query.filter(PHData.timestamp >= start_date, PHData.timestamp <= end_date).order_by(PHData.timestamp).all()
    pump_logs = PumpLog.query.filter(PumpLog.timestamp >= start_date, PumpLog.timestamp <= end_date).order_by(PumpLog.timestamp).all()

    tds_within, max_tds_overshoot, max_tds_undershoot = 0, 0.0, 0.0
    for d in tds_data:
        val = d.tds_value
        if l_tds and l_tds.min_value <= val <= l_tds.max_value: tds_within += 1
        if val > target_tds: max_tds_overshoot = max(max_tds_overshoot, val - target_tds)
        if val < target_tds: max_tds_undershoot = max(max_tds_undershoot, target_tds - val)
        
    ph_within, max_ph_overshoot, max_ph_undershoot = 0, 0.0, 0.0
    for d in ph_data:
        val = d.ph_value
        if l_ph and l_ph.min_value <= val <= l_ph.max_value: ph_within += 1
        if val > target_ph: max_ph_overshoot = max(max_ph_overshoot, val - target_ph)
        if val < target_ph: max_ph_undershoot = max(max_ph_undershoot, target_ph - val)

    tds_within_pct = (tds_within / len(tds_data) * 100) if len(tds_data) > 0 else 0
    ph_within_pct = (ph_within / len(ph_data) * 100) if len(ph_data) > 0 else 0

    total_ec_corrections, total_ph_corrections = 0, 0
    nut_a_ml, nut_b_ml, ph_up_ml, ph_down_ml, max_single_dose = 0.0, 0.0, 0.0, 0.0, 0.0
    correction_times, last_correction_time = [], None

    for log in pump_logs:
        vol = log.duration * flow_rates.get(1, 0.6167)
        if "Pump 1" in log.pump_name:
            vol = log.duration * flow_rates[1]
            nut_a_ml += vol
            if log.trigger_type == "Automatic": total_ec_corrections += 1
        elif "Pump 2" in log.pump_name:
            vol = log.duration * flow_rates[2]
            nut_b_ml += vol
        elif "Pump 3" in log.pump_name:
            vol = log.duration * flow_rates[3]
            ph_up_ml += vol
            if log.trigger_type == "Automatic": total_ph_corrections += 1
        elif "Pump 4" in log.pump_name:
            vol = log.duration * flow_rates[4]
            ph_down_ml += vol
            if log.trigger_type == "Automatic": total_ph_corrections += 1
            
        max_single_dose = max(max_single_dose, vol)
        if log.trigger_type == "Automatic":
            if last_correction_time:
                diff = (log.timestamp - last_correction_time).total_seconds()
                if diff > 60: correction_times.append(diff)
            last_correction_time = log.timestamp

    avg_time_between_corrections = "N/A"
    avg_s = 0
    if correction_times:
        avg_s = sum(correction_times) / len(correction_times)
        avg_time_between_corrections = f"{int(avg_s // 3600)} h {int((avg_s % 3600) // 60)} min"

    # ---------------- EXECUTIVE SUMMARY ----------------
    elements.append(Paragraph("1. Executive Summary", h1_style))
    
    summary_text = f"""
    This engineering report encapsulates the operational performance and environmental stability of the HydroAgrix automated dosing unit over the selected period. 
    The system processed {len(tds_data)} EC telemetry points and {len(ph_data)} pH telemetry points. 
    EC remained within the target range for {tds_within_pct:.1f}% of the selected period.
    pH remained within the target range for {ph_within_pct:.1f}% of the selected period.
    The dosing controller executed {total_ec_corrections} autonomous EC corrections and {total_ph_corrections} autonomous pH corrections to maintain the defined setpoints.
    """
    elements.append(Paragraph(summary_text, normal_style))
    elements.append(Spacer(1, 20))

    # ---------------- ENGINEERING ANALYSIS & SYSTEM HEALTH ----------------
    elements.append(Paragraph("2. Engineering Analysis & Diagnostics", h1_style))
    
    if avg_s > 0 and avg_s < 1800: # Less than 30 mins
        elements.append(Paragraph("⚠️ High Frequency Cycling Detected: Average recovery time between corrections is less than 30 minutes. This indicates potential sensor drift, a highly unstable reservoir volume, or a reservoir that is too small for the plant uptake rate.", alert_style))
    
    if max_ph_overshoot > 1.0 or max_ph_undershoot > 1.0:
        elements.append(Paragraph(f"⚠️ Extreme pH Volatility: Maximum pH overshoot observed was {max_ph_overshoot:.2f}. Verify pump flow rate calibrations and consider reducing the automatic dosing duration multiplier to prevent extreme pH swings.", alert_style))
        
    elements.append(Paragraph(f"Maximum pH overshoot observed: {max_ph_overshoot:.2f}", normal_style))
    elements.append(Paragraph(f"Maximum EC overshoot observed: {max_tds_overshoot:.2f} mS/cm", normal_style))
    elements.append(Paragraph(f"Average recovery time: {avg_time_between_corrections}", normal_style))

    elements.append(Spacer(1, 20))

    # ---------------- DOSING STATISTICS ----------------
    elements.append(Paragraph("3. Dosing & Automation Statistics", h1_style))
    
    dosing_data = [
        ["Metric", "Value"],
        ["Total EC Corrections", str(total_ec_corrections)],
        ["Total pH Corrections", str(total_ph_corrections)],
        ["Nutrient A Dispensed", f"{nut_a_ml:.1f} mL"],
        ["Nutrient B Dispensed", f"{nut_b_ml:.1f} mL"],
        ["pH Up Dispensed", f"{ph_up_ml:.1f} mL"],
        ["pH Down Dispensed", f"{ph_down_ml:.1f} mL"],
        ["Maximum Single Dose", f"{max_single_dose:.1f} mL"],
        ["Avg Time Between Corrections", avg_time_between_corrections]
    ]

    t_dose = Table(dosing_data, colWidths=[250, 150])
    t_dose.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f1f5f9')])
    ]))
    elements.append(t_dose)
    elements.append(PageBreak())

    # ---------------- ENVIRONMENTAL ANALYSIS CHARTS ----------------
    elements.append(Paragraph("4. Environmental Telemetry Charts", h1_style))
    
    def decimate(data_list, val_attr):
        if not data_list: return []
        step = max(1, len(data_list) // 100)
        return [(i, getattr(item, val_attr)) for i, item in enumerate(data_list[::step])]

    if tds_data and ph_data:
        drawing = Drawing(450, 250)
        
        # Background rect
        drawing.add(Rect(0, 0, 450, 250, fillColor=colors.HexColor('#f8fafc'), strokeColor=colors.HexColor('#cbd5e1')))
        
        lp = LinePlot()
        lp.x = 40
        lp.y = 40
        lp.height = 180
        lp.width = 380
        
        tds_line = decimate(tds_data, 'tds_value')
        ph_line = decimate(ph_data, 'ph_value')
        
        lp.data = [tds_line, ph_line]
        lp.lines[0].strokeColor = colors.HexColor('#3b82f6') # Blue for EC
        lp.lines[0].strokeWidth = 2
        lp.lines[1].strokeColor = colors.HexColor('#10b981') # Green for pH
        lp.lines[1].strokeWidth = 2
        
        lp.xValueAxis.valueMin = 0
        lp.xValueAxis.valueMax = max(len(tds_line), len(ph_line))
        
        drawing.add(lp)
        drawing.add(String(200, 15, "Time ->", fontSize=10, fillColor=colors.HexColor('#475569')))
        
        # Legend
        drawing.add(Rect(40, 230, 10, 10, fillColor=colors.HexColor('#3b82f6'), strokeColor=None))
        drawing.add(String(55, 230, "EC (mS/cm)", fontSize=10, fillColor=colors.HexColor('#1e293b')))
        drawing.add(Rect(140, 230, 10, 10, fillColor=colors.HexColor('#10b981'), strokeColor=None))
        drawing.add(String(155, 230, "pH Level", fontSize=10, fillColor=colors.HexColor('#1e293b')))
        
        elements.append(drawing)
    else:
        elements.append(Paragraph("Insufficient telemetry data available for charting over this time period.", normal_style))

    elements.append(Spacer(1, 30))

    # ---------------- CROP PROGRESSION ----------------
    elements.append(Paragraph("5. Crop Imaging & Inference", h1_style))
    photos = PhotoRecord.query.filter(PhotoRecord.captured_at >= start_date, PhotoRecord.captured_at <= end_date).order_by(PhotoRecord.captured_at).all()
    
    if photos:
        step = max(1, len(photos) // 4)
        selected_photos = photos[::step][:4]
        
        photo_grid = []
        for p in selected_photos:
            if os.path.exists(p.google_drive_link):
                try:
                    img_raw = Image(p.google_drive_link, width=220, height=165)
                    img_ml_content = Paragraph("No Inference Available", normal_style)
                    
                    try:
                        from ultralytics import YOLO
                        import cv2
                        import tempfile
                        
                        model_path = os.path.join(os.path.dirname(__file__), 'stage_detect.pt')
                        if os.path.exists(model_path):
                            model = YOLO(model_path)
                            frame = cv2.imread(p.google_drive_link)
                            if frame is not None:
                                results = model(frame, verbose=False)
                                annotated_frame = results[0].plot()
                                tmp_path = tempfile.mktemp(suffix='.jpg')
                                cv2.imwrite(tmp_path, annotated_frame)
                                img_ml_content = Image(tmp_path, width=220, height=165)
                    except Exception as e:
                        print(f"ML inference error: {e}")
                    
                    header_raw = Paragraph(f"<b>Raw Image</b> ({p.captured_at.strftime('%m-%d %H:%M')})", normal_style)
                    header_ml = Paragraph("<b>Machine Vision Inference</b>", normal_style)
                    
                    photo_grid.append([header_raw, header_ml])
                    photo_grid.append([img_raw, img_ml_content])
                except Exception as e:
                    print(f"Error drawing image: {e}")

        if photo_grid:
            t_photos = Table(photo_grid, colWidths=[250, 250])
            t_photos.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ]))
            elements.append(t_photos)
        else:
            elements.append(Paragraph("No valid images found on disk for this period.", normal_style))
    else:
        elements.append(Paragraph("No imaging records available for this period.", normal_style))

    # Build PDF
    def add_page_numbers(canvas, doc):
        page_num = canvas.getPageNumber()
        text = f"HydroAgrix Engineering Report - Page {page_num}"
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.HexColor('#94a3b8'))
        canvas.drawRightString(letter[0] - 40, 20, text)

    doc.build(elements, onFirstPage=add_page_numbers, onLaterPages=add_page_numbers)
    buffer.seek(0)
    return buffer
