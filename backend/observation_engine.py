import time
from datetime import datetime
from models import NutrientObservations, SystemAlerts, ActionTokens, db
from config import app

class NutrientImpactTracker:
    def __init__(self):
        self.pending_evaluation = None

    def record_nutrient_dose(self, volume_ml, pre_ph):
        """Called immediately before a nutrient dose begins."""
        self.pending_evaluation = {
            "volume_ml": volume_ml,
            "pre_ph": pre_ph,
            "time": time.time()
        }

    def evaluate_impact(self, current_ph, cooldown_s):
        """Called in the main loop to check if cooldown has elapsed and evaluate pH change."""
        if not self.pending_evaluation:
            return

        if time.time() - self.pending_evaluation["time"] >= cooldown_s:
            vol = self.pending_evaluation["volume_ml"]
            pre_ph = self.pending_evaluation["pre_ph"]
            delta = current_ph - pre_ph
            
            with app.app_context():
                obs = NutrientObservations(
                    dose_type="NUTRIENT_A_B",
                    volume_ml=vol,
                    pre_ph=pre_ph,
                    post_ph=current_ph,
                    delta_ph=delta
                )
                db.session.add(obs)
                db.session.commit()
            
            self.pending_evaluation = None

    def get_average_ph_impact_per_ml(self):
        """Returns historical average delta pH per ml of nutrient dosed (typically negative/acidic)."""
        with app.app_context():
            recent_obs = NutrientObservations.query.order_by(NutrientObservations.id.desc()).limit(10).all()
            if not recent_obs:
                return -0.005 # Fallback default
            
            total_delta = sum(obs.delta_ph for obs in recent_obs)
            total_vol = sum(obs.volume_ml for obs in recent_obs)
            
            if total_vol > 0:
                return total_delta / total_vol
            return -0.005

nutrient_impact_tracker = NutrientImpactTracker()

class AlertManager:
    @staticmethod
    def trigger_alert(alert_key):
        with app.app_context():
            alert = SystemAlerts.query.filter_by(alert_key=alert_key, status="ACTIVE").first()
            if not alert:
                alert = SystemAlerts(alert_key=alert_key, status="ACTIVE")
                db.session.add(alert)
                db.session.commit()
                return True # Indicates a new alert was raised
            return False # Already active

    @staticmethod
    def resolve_alert(alert_key):
        with app.app_context():
            alert = SystemAlerts.query.filter_by(alert_key=alert_key, status="ACTIVE").first()
            if alert:
                alert.status = "RESOLVED"
                alert.resolved_at = datetime.utcnow()
                db.session.commit()
                return True
            return False

alert_manager = AlertManager()
