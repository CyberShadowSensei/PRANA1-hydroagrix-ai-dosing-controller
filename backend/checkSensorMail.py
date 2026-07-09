from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import smtplib
import json
import os
from datetime import datetime, timedelta

class SensorMonitor:
    """
    Two-tier alert system:
    
    TIER 1 — DANGER (emails sent): Values so extreme they indicate hardware failure
             or genuine crop risk. Uses wide "danger zone" thresholds.
             e.g., pH < 3.0 or > 10.0, Temp > 45°C, EC > 8.0
    
    TIER 2 — WARNING (logged only): Values slightly outside the user's monitoring
             range. These are normal fluctuations — no email, just console log.
    """
    
    # Absolute danger thresholds — these should NEVER be hit under normal conditions.
    # If they ARE hit, something is seriously wrong (broken sensor, chemical spill, etc.)
    DANGER_THRESHOLDS = {
        'temperature': {'min': 5,  'max': 45},   # °C — below 5 = frost, above 45 = equipment failure
        'humidity':    {'min': 10, 'max': 98},    # % — below 10 = sensor fault, above 98 = condensation
        'tds':         {'min': 0,  'max': 8.0},   # mS/cm — above 8 = chemical spill / sensor fault
        'ph':          {'min': 3.0, 'max': 10.0}  # — below 3 = acid spill, above 10 = base spill
    }
    
    # Default margins for sensors WITHOUT user-set limits
    # For pH and EC, margins are computed dynamically from the user's range
    DEFAULT_MARGINS = {
        'temperature': 5,    # ±5°C beyond user range (fixed — environment is standardized)
        'humidity':    15,   # ±15% beyond user range (fixed)
        'tds':         1.5,  # Fallback if no user limits set
        'ph':          1.0   # Fallback if no user limits set
    }
    
    @staticmethod
    def _compute_margin(sensor_name, user_limits):
        """
        For pH and EC: margin = 50% of the user's set range width.
        This makes alerts scale with how tight/loose the user has set their monitoring.
        
        Example: pH range 5.5–7.0 → width=1.5 → margin=0.75 → alerts at <4.75 or >7.75
        Example: EC range 1.0–3.0 → width=2.0 → margin=1.0 → alerts at <0.0 or >4.0
        """
        if sensor_name in ('ph', 'tds') and user_limits:
            range_width = abs(user_limits['max'] - user_limits['min'])
            # Min margin of 0.5 for pH, 0.5 for EC — never go below this
            min_margins = {'ph': 0.5, 'tds': 0.5}
            return max(range_width * 0.5, min_margins.get(sensor_name, 0.5))
        return SensorMonitor.DEFAULT_MARGINS.get(sensor_name, 1.0)

    def __init__(self):
        self.email_config = self.load_email_config()
        
        self.sensor_states = {
            'temperature': {'is_faulted': False, 'last_notification': None, 'fault_start': None},
            'humidity':    {'is_faulted': False, 'last_notification': None, 'fault_start': None},
            'tds':         {'is_faulted': False, 'last_notification': None, 'fault_start': None},
            'ph':          {'is_faulted': False, 'last_notification': None, 'fault_start': None}
        }
        
        self.notification_cooldown = 4  # Hours between repeated alerts for same sensor
    
    def load_email_config(self):
        """Load email configuration from a JSON file"""
        try:
            with open('email_config.json', 'r') as f:
                return json.load(f)
        except Exception:
            return {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'sender_email': 'placeholder@gmail.com',
                'sender_password': 'placeholder_password',
                'receiver_email': 'placeholder_recipient@gmail.com'
            }

    def send_report(self, subject, body, attachments=None):
        """Sends an email with optional attachments (daily digest, manual reports)."""
        if self.email_config.get('sender_email') == 'placeholder@gmail.com':
            print(f"[MAIL-STUB] Report: {subject}")
            return True, "Success (Stubbed)"

        try:
            from email.utils import formatdate, make_msgid
            msg = MIMEMultipart('mixed')
            msg['From'] = self.email_config['sender_email']
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid()
            
            # Support multiple recipients (comma or semicolon separated)
            recipients_raw = self.email_config.get('recipient_email') or self.email_config.get('receiver_email', '')
            recipients = [r.strip() for r in recipients_raw.replace(';', ',').split(',') if r.strip()]
            
            msg['To'] = ", ".join(recipients)
            from email.header import Header
            msg['Subject'] = Header(subject, 'utf-8')

            # Pre-format the body to replace newlines with HTML line breaks prior to formatting the f-string
            body_html_formatted = body.replace('\n', '<br>')

            # Wrap the plain-text body in a beautiful HTML report container
            html_body = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0c100d; color: #e2e8f0; margin: 0; padding: 24px; min-height: 100%;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #121813; border: 1px solid #10b981; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(16, 185, 129, 0.15);">
                    <div style="background: linear-gradient(135deg, #052e16 0%, #022c22 100%); padding: 32px 24px; text-align: center; border-bottom: 1px solid #10b981;">
                        <h1 style="margin: 0; font-size: 24px; font-weight: 700; color: #10b981; letter-spacing: 0.05em; text-transform: uppercase;">Hydroponics System</h1>
                        <p style="margin: 8px 0 0 0; font-size: 14px; color: #06b6d4; font-weight: 500;">Daily Agricultural Digest</p>
                    </div>
                    <div style="padding: 32px 24px;">
                        <p style="font-size: 16px; line-height: 1.6; margin-top: 0; color: #f1f5f9;">{body_html_formatted}</p>
                    </div>
                    <div style="background-color: #0d120e; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #1e293b;">
                </div>
            </div>
            """
            msg.attach(MIMEText(html_body, 'html'))

            if attachments:
                for filename, content in attachments.items():
                    part = MIMEApplication(content, Name=filename)
                    part['Content-Disposition'] = f'attachment; filename="{filename}"'
                    msg.attach(part)
            
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg)
            
            return True, "Email sent successfully"
        except Exception as e:
            print(f"Failed to send report email: {str(e)}")
            return False, str(e)

    def send_email_alert(self, sensor_name, error_message, severity="DANGER", bypass_cooldown=False):
        """Send email notification about sensor emergency"""
        if self.email_config.get('sender_email') == 'placeholder@gmail.com':
            print(f"[MAIL-STUB] {severity} Alert for {sensor_name}: {error_message}")
            return

        try:
            current_time = datetime.now()
            sensor_state = self.sensor_states[sensor_name]
            
            # Enforce cooldown — don't spam for the same sensor unless bypassed
            if not bypass_cooldown and (sensor_state['last_notification'] and 
                (current_time - sensor_state['last_notification']).total_seconds() < self.notification_cooldown * 3600):
                print(f"DEBUG: Email alert for {sensor_name} skipped due to {self.notification_cooldown}h cooldown")
                return
            

            from email.utils import formatdate, make_msgid
            msg = MIMEMultipart('mixed')
            msg['From'] = self.email_config['sender_email']
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid()
            
            # Support multiple recipients
            recipients_raw = self.email_config.get('recipient_email') or self.email_config.get('receiver_email', '')
            recipients = [r.strip() for r in recipients_raw.replace(';', ',').split(',') if r.strip()]
            msg['To'] = ", ".join(recipients)
            
            from email.header import Header
            msg['Subject'] = Header(f"{severity}: {sensor_name.upper()} Sensor Notification", 'utf-8')
            
            # PLAIN TEXT FALLBACK (Crucial for spam filters)
            plain_text = f"""
            HydroAgrix System Telemetry Notification
            
            Severity: {severity}
            Sensor Tag: {sensor_name.upper()}
            Status Scan: {error_message}
            Timestamp (IST): {current_time.strftime('%Y-%m-%d %H:%M:%S')}
            
            """
            if severity == "DANGER":
                plain_text += "Warning: Critical bounds violated. This reading has deviated outside standard safety tolerances. Manual intervention requested to ensure hardware safety."
            else:
                plain_text += "Metric Restored. The sensor reading has returned to normal ranges."
                
            plain_text += "\n\nGenerated automatically by the HydroAgrix IoT Gateway Monitoring Node. Please do not reply directly."

            # HTML VERSION
            header_gradient = "linear-gradient(135deg, #7f1d1d 0%, #450a0a 100%)" if severity == "DANGER" else "linear-gradient(135deg, #064e3b 0%, #022c22 100%)"
            border_color = "#ef4444" if severity == "DANGER" else "#10b981"
            title_color = "#fca5a5" if severity == "DANGER" else "#a7f3d0"
            
            html_body = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0c100d; color: #e2e8f0; margin: 0; padding: 24px; min-height: 100%;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #121813; border: 1px solid {border_color}; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(239, 68, 68, 0.15);">
                    <div style="background: {header_gradient}; padding: 28px 24px; text-align: center; border-bottom: 1px solid {border_color};">
                        <h1 style="margin: 8px 0 0 0; font-size: 22px; font-weight: 700; color: {title_color}; letter-spacing: 0.05em; text-transform: uppercase;">{severity} NOTIFICATION</h1>
                        <p style="margin: 4px 0 0 0; font-size: 13px; color: #94a3b8;">System Telemetry Integrity Scan</p>
                    </div>
                    <div style="padding: 24px;">
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
                            <tr style="border-bottom: 1px solid #1e293b;">
                                <td style="padding: 12px 8px; font-size: 14px; color: #94a3b8; font-weight: 600; width: 35%;">Sensor Tag:</td>
                                <td style="padding: 12px 8px; font-size: 15px; color: #06b6d4; font-weight: 700;">{sensor_name.upper()}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #1e293b;">
                                <td style="padding: 12px 8px; font-size: 14px; color: #94a3b8; font-weight: 600;">Status Scan:</td>
                                <td style="padding: 12px 8px; font-size: 14px; color: {border_color}; font-weight: 700;">{error_message}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #1e293b;">
                                <td style="padding: 12px 8px; font-size: 14px; color: #94a3b8; font-weight: 600;">Timestamp (IST):</td>
                                <td style="padding: 12px 8px; font-size: 14px; color: #f1f5f9;">{current_time.strftime('%Y-%m-%d %H:%M:%S')}</td>
                            </tr>
                        </table>
            """
            
            if severity == "DANGER":
                html_body += f"""
                        <div style="background-color: #1a1010; border-left: 4px solid #ef4444; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
                            <h4 style="margin: 0 0 8px 0; color: #fca5a5; font-size: 15px;">Critical Bounds Violated</h4>
                            <p style="margin: 0; font-size: 13px; color: #f87171; line-height: 1.5;">
                                This reading has deviated outside standard safety tolerances. Potential triggers include probe disconnections, driver failures, empty chemical bins, or environmental anomalies.
                            </p>
                        </div>
                        <div style="text-align: center;">
                            <p style="font-size: 14px; font-weight: 700; color: #ef4444; margin: 0;">MANUAL INTERVENTION REQUESTED</p>
                        </div>
                """
            else:
                html_body += f"""
                        <div style="background-color: #062f22; border-left: 4px solid #10b981; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
                            <h4 style="margin: 0 0 8px 0; color: #a7f3d0; font-size: 15px;">Metric Restored</h4>
                            <p style="margin: 0; font-size: 13px; color: #34d399; line-height: 1.5;">
                                The sensor reading has returned to normal ranges. Automated system scheduling has resumed.
                            </p>
                        </div>
                """
                
            html_body += """
                    </div>
                    <div style="background-color: #0d120e; padding: 20px; text-align: center; font-size: 11px; color: #64748b; border-top: 1px solid #1e293b;">
                        HydroAgrix IoT Gateway Monitoring Node. Please do not reply directly.
                    </div>
                </div>
            </div>
            """
            
            alt_part = MIMEMultipart('alternative')
            alt_part.attach(MIMEText(plain_text, 'plain'))
            alt_part.attach(MIMEText(html_body, 'html'))
            msg.attach(alt_part)
            
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg, to_addrs=recipients)
            
            sensor_state['last_notification'] = current_time
            if severity == "DANGER" and not sensor_state['is_faulted']:
                sensor_state['is_faulted'] = True
                sensor_state['fault_start'] = current_time
            
            print(f"EMAIL {severity} alert sent for {sensor_name}: {error_message}")
        except Exception as e:
            print(f"Failed to send email alert: {str(e)}")

    def _log_to_db(self, event_id, category, message, details=None):
        """Save warning/danger logs to the database so they appear in the UI."""
        try:
            from config import app, db
            from models import EventLog
            with app.app_context():
                details_str = json.dumps(details) if details else None
                db.session.add(EventLog(
                    event_id=event_id,
                    category=category,
                    message=message,
                    details_json=details_str
                ))
                db.session.commit()
        except Exception as e:
            print(f"DEBUG: Failed to save DB log: {e}")

    DEADBANDS = {
        'temperature': 1.0,   # °C
        'humidity':    3.0,   # %
        'tds':         0.3,   # mS/cm
        'ph':          0.2    # pH units
    }

    def check_sensor_reading(self, sensor_name, value, user_limits=None):
        """
        Two-tier check:
        1. DANGER: Is the value beyond absolute safety thresholds? -> EMAIL
        2. WARNING: Is it just slightly outside user's monitoring range? -> LOG ONLY
        
        Args:
            sensor_name: 'ph', 'tds', 'temperature', or 'humidity'
            value: The sensor reading
            user_limits: Optional dict {'min': float, 'max': float} from SensorLimits table
        """
        if sensor_name not in self.DANGER_THRESHOLDS:
            return
        
        # NULL value = sensor disconnected = always an emergency
        if value is None:
            is_new_fault = not self.sensor_states[sensor_name]['is_faulted']
            self.send_email_alert(sensor_name, "Sensor returned NULL - possible hardware disconnection", "DANGER", bypass_cooldown=is_new_fault)
            self._log_to_db(f"{sensor_name.upper()}_NULL", "DANGER", f"Sensor returned NULL - possible hardware disconnection")
            return
        
        danger = self.DANGER_THRESHOLDS[sensor_name]
        
        # TIER 1: Check ABSOLUTE danger thresholds (hardware failure / crop emergency)
        if value < danger['min'] or value > danger['max']:
            msg = f"EXTREME reading: {value} (safe range: {danger['min']}-{danger['max']})"
            is_new_fault = not self.sensor_states[sensor_name]['is_faulted']
            self.send_email_alert(sensor_name, msg, "DANGER", bypass_cooldown=is_new_fault)
            self._log_to_db(f"{sensor_name.upper()}_EXTREME", "DANGER", msg, {"value": value})
            return
        
        # TIER 1b: Check USER-SET limits + dynamic safety margin
        # Only fires if value is WAY beyond what the user set (not just slightly off)
        if user_limits:
            margin = self._compute_margin(sensor_name, user_limits)
            alert_min = user_limits['min'] - margin
            alert_max = user_limits['max'] + margin
            
            if value < alert_min or value > alert_max:
                msg = f"Value {value} is significantly outside your set range ({user_limits['min']}-{user_limits['max']}) by more than {margin} units"
                is_new_fault = not self.sensor_states[sensor_name]['is_faulted']
                self.send_email_alert(sensor_name, msg, "DANGER", bypass_cooldown=is_new_fault)
                self._log_to_db(f"{sensor_name.upper()}_DANGER_RANGE", "DANGER", msg, {"value": value})
                return
        
        # If we get here, the value is within acceptable range
        if self.sensor_states[sensor_name]['is_faulted']:
            # Apply deadband to prevent recovery alerts on boundary jitter
            db_val = self.DEADBANDS.get(sensor_name, 0.2)
            abs_ok = (danger['min'] + db_val) <= value <= (danger['max'] - db_val)
            
            user_ok = True
            if user_limits:
                margin = self._compute_margin(sensor_name, user_limits)
                user_ok = (user_limits['min'] - margin + db_val) <= value <= (user_limits['max'] + margin - db_val)
                
            if abs_ok and user_ok:
                # Sensor recovered fully inside the deadband zone
                msg = f"Sensor recovered! Current value: {value}"
                self.send_email_alert(sensor_name, msg, "RECOVERY", bypass_cooldown=True)
                self._log_to_db(f"{sensor_name.upper()}_RECOVERY", "RECOVERY", msg, {"value": value})
                self.sensor_states[sensor_name]['is_faulted'] = False
        
        # Minor out-of-range (within user limits but outside monitoring range)?
        # Just log, NEVER email for this.
        if user_limits and (value < user_limits['min'] or value > user_limits['max']):
            msg = f"INFO {sensor_name}: {value} slightly outside user range ({user_limits['min']}-{user_limits['max']}) - logged, no alert"
            print(msg)
            self._log_to_db(f"{sensor_name.upper()}_WARNING", "WARNING", f"{sensor_name} at {value} is slightly outside limits.", {"value": value})

    def load_config(self):
        """Reload email config from file (called by update_email_config route)."""
        self.email_config = self.load_email_config()
        print(f"DEBUG: Email config reloaded. Sender: {self.email_config.get('sender_email', 'N/A')}")
