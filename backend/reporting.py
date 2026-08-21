import os
import csv
import json
from models import PHData, TDSData, TemperatureHumidityData
from config import db

def generate_cycle_reports():
    ph_data = PHData.query.filter_by(archived=False).all()
    tds_data = TDSData.query.filter_by(archived=False).all()
    th_data = TemperatureHumidityData.query.filter_by(archived=False).all()
    
    csv_path = os.path.abspath('temp_report.csv')
    json_path = os.path.abspath('temp_report.json')
    
    # Write to JSON
    data_dict = {
        "ph_data": [d.to_json() for d in ph_data],
        "tds_data": [d.to_json() for d in tds_data],
        "th_data": [d.to_json() for d in th_data]
    }
    with open(json_path, 'w') as f:
        json.dump(data_dict, f, indent=4)
        
    # Write to CSV
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Type", "ID", "Timestamp", "Value1", "Value2", "Value3"])
        for d in ph_data:
            writer.writerow(["PH", d.id, d.timestamp, d.ph_value, d.water_temp, d.air_temp])
        for d in tds_data:
            writer.writerow(["TDS", d.id, d.date, d.tds_value, d.water_temp, d.air_temp])
        for d in th_data:
            writer.writerow(["TH", d.id, d.date, d.temperature, d.humidity, ""])
            
    return csv_path, json_path

def generate_cycle_report(report_type):
    from models import PlantStageStatus, PHData, TDSData, TemperatureHumidityData
    from sensors import sensor_monitor
    import csv
    import io
    from datetime import datetime
    
    status = PlantStageStatus.query.first()
    if not status or not status.cycle_start_date:
        return False
        
    start_date = status.cycle_start_date
    end_date = datetime.utcnow()
    
    ph_data = PHData.query.filter(PHData.timestamp >= start_date, PHData.timestamp <= end_date).order_by(PHData.timestamp).all()
    tds_data = TDSData.query.filter(TDSData.date >= start_date, TDSData.date <= end_date).order_by(TDSData.date).all()
    th_data = TemperatureHumidityData.query.filter(TemperatureHumidityData.date >= start_date, TemperatureHumidityData.date <= end_date).order_by(TemperatureHumidityData.date).all()
    
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["Type", "Timestamp", "Value 1", "Value 2", "Value 3"])
    for d in ph_data:
        writer.writerow(["pH", d.timestamp.strftime('%Y-%m-%d %H:%M:%S'), d.ph_value, d.water_temp, d.air_temp])
    for d in tds_data:
        writer.writerow(["EC", d.date.strftime('%Y-%m-%d %H:%M:%S'), d.tds_value, d.water_temp, d.air_temp])
    for d in th_data:
        writer.writerow(["Temp/Hum", d.date.strftime('%Y-%m-%d %H:%M:%S'), d.temperature, d.humidity, ""])
        
    csv_bytes = csv_buffer.getvalue().encode('utf-8')
    
    # PDF generation logic
    try:
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import letter
        from io import BytesIO
        
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        elements.append(Paragraph(f"IoT Hydroponic System Status Report ({report_type})", styles['Title']))
        
        ph = ph_data[-1] if ph_data else None
        tds = tds_data[-1] if tds_data else None
        th = th_data[-1] if th_data else None
        
        ph_val = f"{round(ph.ph_value, 2) if ph else 'N/A'}"
        ph_w_temp = f"{round(ph.water_temp, 1) if (ph and ph.water_temp is not None) else 'N/A'} C"
        ph_a_temp = f"{round(ph.air_temp, 1) if (ph and ph.air_temp is not None) else 'N/A'} C"
        
        tds_val = f"{round(tds.tds_value, 2) if tds else 'N/A'} mS/cm"
        tds_w_temp = f"{round(tds.water_temp, 1) if (tds and tds.water_temp is not None) else 'N/A'} C"
        tds_a_temp = f"{round(tds.air_temp, 1) if (tds and tds.air_temp is not None) else 'N/A'} C"
        
        summary_data = [
            ["Sensor", "Value", "Water Temp", "Air Temp"],
            ["pH", ph_val, ph_w_temp, ph_a_temp],
            ["EC", tds_val, tds_w_temp, tds_a_temp],
            ["Climate Temp", f"{th.temperature if th else 'N/A'} C", "-", f"{th.temperature if th else 'N/A'} C"],
            ["Climate Hum", f"{th.humidity if th else 'N/A'} %", "-", "-"]
        ]
        
        t_summary = Table(summary_data, colWidths=[120, 100, 100, 100])
        t_summary.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey), ('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(t_summary)
        doc.build(elements)
        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.read()
    except Exception as e:
        print(f"Failed to generate PDF for report: {e}")
        pdf_bytes = None
    
    subject = f"Grow Cycle Report: {report_type}"
    body = f"The grow cycle for {status.plant_name} was {report_type}.\nStart Date: {start_date}\nEnd Date: {end_date}\n\nThe growth cycle has ended.\n\nPlease find the attached telemetry data CSV and summary PDF."
    attachments = {"cycle_data.csv": csv_bytes}
    if pdf_bytes:
        attachments["cycle_report.pdf"] = pdf_bytes
    
    success, msg = sensor_monitor.send_report(subject, body, attachments)
    if not success:
        print(f"Failed to send {report_type} cycle report: {msg}")
    return success

