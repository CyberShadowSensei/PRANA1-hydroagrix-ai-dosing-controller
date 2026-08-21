from main import app, db
from models import SensorLimits, PlantStageStatus

with app.app_context():
    print("--- SensorLimits count:", SensorLimits.query.count())
    limits = SensorLimits.query.all()
    for l in limits:
        print(f"SensorLimits: id={l.id}, sensor_type={l.sensor_type}, min_value={l.min_value}, max_value={l.max_value}, is_active={l.is_active}")
        
    status = PlantStageStatus.query.first()
    if status:
        print(f"PlantStageStatus: plant_name={status.plant_name}, plant_stage={status.plant_stage}, state={status.state}, start_date={status.cycle_start_date}")
    else:
        print("PlantStageStatus is empty!")
