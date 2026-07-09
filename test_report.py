import os
import sys
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from config import app
from report_generator import generate_growth_cycle_report

if __name__ == "__main__":
    with app.app_context():
        start_date = datetime.utcnow() - timedelta(days=7)
        end_date = datetime.utcnow()
        
        try:
            print(f"Generating report from {start_date} to {end_date}...")
            buf = generate_growth_cycle_report(start_date, end_date)
            
            with open("test_report.pdf", "wb") as f:
                f.write(buf.getvalue())
            
            print("Successfully generated test_report.pdf")
        except Exception as e:
            import traceback
            traceback.print_exc()
