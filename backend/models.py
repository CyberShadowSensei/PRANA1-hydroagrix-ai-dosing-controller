from datetime import datetime
import pytz
from config import db

# Configure timezone - replace with your specific timezone as needed
DEFAULT_TIMEZONE = pytz.timezone('Asia/Kolkata')  # Change to your timezone, e.g., 'America/New_York'

class LightBulb(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(80), unique=False, nullable=False)
    date = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def to_json(self):
        localized_date = self.date.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id,
            "status": self.status,
            "date": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z'),
        }

class MoistureSensorData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moisture_level = db.Column(db.Integer, nullable=False)
    state = db.Column(db.String(50), nullable=False)
    date = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def to_json(self):
        localized_date = self.date.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id,
            "moisture_level": self.moisture_level,
            "state": self.state,
            "date": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

class TemperatureHumidityData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def to_json(self):
        localized_date = self.date.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "date": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

class PhotoRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    google_drive_link = db.Column(db.String(500), nullable=False)
    captured_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_json(self):
        localized_date = self.captured_at.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id,
            "filename": self.filename,
            "google_drive_link": self.google_drive_link,  # Fixed attribute name
            "captured_at": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

class TDSData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tds_value = db.Column(db.Float, nullable=False)
    water_temp = db.Column(db.Float, nullable=True)
    air_temp = db.Column(db.Float, nullable=True)
    date = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def to_json(self):
        date_obj = self.date or datetime.utcnow()
        localized_date = date_obj.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id,
            "tds_value": self.tds_value,
            "water_temp": self.water_temp,
            "air_temp": self.air_temp,
            "date": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

class PHData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ph_value = db.Column(db.Float, nullable=False)
    water_temp = db.Column(db.Float, nullable=True)
    air_temp = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def to_json(self):
        ts_obj = self.timestamp or datetime.utcnow()
        localized_date = ts_obj.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id, 
            "ph_value": self.ph_value,
            "water_temp": self.water_temp,
            "air_temp": self.air_temp,
            "timestamp": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

class SensorLimits(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor_type = db.Column(db.String(10), nullable=False)
    min_value = db.Column(db.Float, nullable=False)
    max_value = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_json(self):
        localized_date = self.updated_at.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id,
            "sensor_type": self.sensor_type,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "is_active": self.is_active,
            "updated_at": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

class PlantStageStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plant_name = db.Column(db.String(255), nullable=False)
    plant_stage = db.Column(db.String(255), nullable=False)
    state = db.Column(db.Boolean, default=True)

    def to_json(self):
        return {
            "id": self.id,
            "plant_name": self.plant_name,
            "plant_stage": self.plant_stage,
            "state": self.state
        }

class PlantPreset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    stages_json = db.Column(db.Text, nullable=False) # JSON literal representation
    
    def to_json(self):
        import json
        return {
            "id": self.id,
            "name": self.name,
            "image": self.image_url,
            "stages": json.loads(self.stages_json)
        }

class PresetAuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False) # Added, Modified, Deleted, Applied
    preset_name = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_json(self):
        localized_date = self.timestamp.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id,
            "action": self.action,
            "preset_name": self.preset_name,
            "details": self.details,
            "timestamp": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

class PumpLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pump_name = db.Column(db.String(255), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    trigger_type = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    def to_json(self):
        localized_date = self.timestamp.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        return {
            "id": self.id,
            "pump_name": self.pump_name,
            "duration": self.duration,
            "trigger_type": self.trigger_type,
            "timestamp": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }

class EventLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(100), nullable=False)    # SYSTEM_STARTUP, DOSING_STARTED_EC, etc.
    category = db.Column(db.String(50), nullable=False)     # DOSING, SENSORS, SYSTEM, ALARM
    message = db.Column(db.String(500), nullable=False)
    details_json = db.Column(db.Text, nullable=True)        # Compact JSON of debug parameters
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_json(self):
        import json
        localized_date = self.timestamp.replace(tzinfo=pytz.UTC).astimezone(DEFAULT_TIMEZONE)
        details = {}
        if self.details_json:
            try:
                details = json.loads(self.details_json)
            except Exception:
                details = {"raw": self.details_json}
        return {
            "id": self.id,
            "event_id": self.event_id,
            "category": self.category,
            "message": self.message,
            "details": details,
            "timestamp": localized_date.strftime('%Y-%m-%d %H:%M:%S %Z')
        }
