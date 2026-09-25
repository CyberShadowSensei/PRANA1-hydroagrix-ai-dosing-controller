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
            
            # OUTLIER CLAMPING: Guard against manual chemical additions.
            # If someone pours acid in mid-dose, the delta will be massive.
            # We cap the recorded delta to +/- 0.05 pH per mL so it doesn't corrupt the historical average.
            if vol > 0:
                impact_per_ml = delta / vol
                clamped_impact_per_ml = max(-0.05, min(0.05, impact_per_ml))
                clamped_delta = clamped_impact_per_ml * vol
            else:
                clamped_delta = 0

            with app.app_context():
                obs = NutrientObservations(
                    dose_type="NUTRIENT_A_B",
                    volume_ml=vol,
                    pre_ph=pre_ph,
                    post_ph=current_ph,
                    delta_ph=clamped_delta  # Store the clamped value
                )
                db.session.add(obs)
                db.session.commit()
            
            self.pending_evaluation = None

    def get_average_ph_impact_per_ml(self):
        """Returns historical average delta pH per ml of nutrient dosed using Robust EMA."""
        with app.app_context():
            # Only fetch last 6 doses (low CPU overhead, fast adaptation)
            recent_obs = NutrientObservations.query.order_by(NutrientObservations.id.desc()).limit(6).all()
            if not recent_obs:
                return -0.005 # Fallback default
            
            # Reverse to chronological order (oldest to newest)
            recent_obs.reverse()

            # Base EMA weighting (30% new data, 70% historical)
            alpha = 0.3
            ema_impact = -0.005 # Baseline starting point
            
            for obs in recent_obs:
                if obs.volume_ml > 0:
                    current_impact = obs.delta_ph / obs.volume_ml
                    
                    # TREND REVERSAL DETECTION:
                    # If historical EMA is acidic (-) and new dose is clearly basic (+),
                    # increase alpha to 60% to cross the zero-line and adapt to the new chemical faster.
                    if (ema_impact < 0 and current_impact > 0.002) or (ema_impact > 0 and current_impact < -0.002):
                        ema_impact = (current_impact * 0.6) + (ema_impact * 0.4)
                    else:
                        ema_impact = (current_impact * alpha) + (ema_impact * (1 - alpha))

            return ema_impact

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
