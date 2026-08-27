import threading
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
        'temperature': {'min': 5, 'max': 40},   # °C — below 5 = frost, above 40 = equipment failure
        'humidity':    {'min': 10, 'max': 98},    # % — below 10 = sensor fault, above 98 = condensation
        'tds':         {'min': 0.0,  'max': 5.5},   # mS/cm — above 5.5 = chemical spill / sensor fault
        'ph':          {'min': 2.5, 'max': 11.5}  # — below 2.5 = acid spill, above 11.5 = base spill
    }
    

    def __init__(self):
        self.email_config = self.load_email_config()
        
        self.sensor_states = {
            'temperature': {'is_faulted': False, 'last_notification': None, 'fault_start': None, 'consecutive_alerts': 0},
            'humidity':    {'is_faulted': False, 'last_notification': None, 'fault_start': None, 'consecutive_alerts': 0},
            'tds':         {'is_faulted': False, 'last_notification': None, 'fault_start': None, 'consecutive_alerts': 0},
            'ph':          {'is_faulted': False, 'last_notification': None, 'fault_start': None, 'consecutive_alerts': 0}
        }
        
        self.notification_cooldown = 4  # Hours between repeated alerts for same sensor
        self.last_warning_logged = {}
    
    def _is_dummy_config(self):
        """Check if the email config uses default/dummy credentials."""
        sender = self.email_config.get('sender_email', '').lower().strip()
        if not sender:
            return True
        dummies = ['placeholder@gmail.com', 'test@test.com', 'example.com']
        return any(d in sender for d in dummies)
    
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

    def send_report(self, subject, body, attachments=None, html_body=None):
        """Sends an email with optional attachments (daily digest, manual reports)."""
        recipients_raw = self.email_config.get('recipient_email') or self.email_config.get('receiver_email', '')
        recipients = [r.strip() for r in recipients_raw.replace(';', ',').split(',') if r.strip()]
        recipients_str = ", ".join(recipients)

        if self._is_dummy_config():
            print(f"[MAIL-STUB] Report: {subject} (Dummy credentials detected)")
            self._log_audit(subject, recipients_str, "REPORT", "STUBBED")
            return True, "Email not configured (Stubbed due to dummy credentials)."

        try:
            from email.utils import formatdate, make_msgid
            msg = MIMEMultipart('mixed')
            msg['From'] = self.email_config['sender_email']
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid()
            
            msg['To'] = recipients_str
            from email.header import Header
            msg['Subject'] = Header(subject, 'utf-8')

            # Content inside the body
            if html_body is not None:
                content_html = html_body
            else:
                body_html_formatted = body.replace('\n', '<br>') if body else ""
                content_html = f"<p style='font-size: 15px; line-height: 1.6; margin-top: 0; color: #334155;'>{body_html_formatted}</p>"

            final_html = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f8fafc; color: #334155; margin: 0; padding: 32px 16px; min-height: 100%;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.025);">
                    <div style="background-color: #0f172a; padding: 32px 24px; text-align: center; border-bottom: 1px solid #e2e8f0;">
                        <h1 style="margin: 0; font-size: 20px; font-weight: 700; color: #ffffff; letter-spacing: 0.05em; text-transform: uppercase;">Hydroagrix Farm System</h1>
                        <p style="margin: 6px 0 0 0; font-size: 13px; color: #38bdf8; font-weight: 500; letter-spacing: 0.025em;">Daily Agricultural Digest</p>
                    </div>
                    <div style="padding: 32px 24px;">
                        {content_html}
                    </div>
                    <div style="background-color: #f8fafc; padding: 24px; text-align: center; font-size: 11px; color: #64748b; border-top: 1px solid #e2e8f0;">
                        This is an automated digest message from your Hydroagrix AI Dosing Controller.<br>
                        Please do not reply directly to this email.
                    </div>
                </div>
            </div>
            """
            # Plain-text fallback for spam prevention
            alt_part = MIMEMultipart('alternative')
            plain_fallback = body if body else subject
            alt_part.attach(MIMEText(plain_fallback, 'plain', 'utf-8'))
            alt_part.attach(MIMEText(final_html, 'html', 'utf-8'))
            msg.attach(alt_part)

            if attachments:
                for filename, content in attachments.items():
                    part = MIMEApplication(content, Name=filename)
                    part['Content-Disposition'] = f'attachment; filename="{filename}"'
                    msg.attach(part)
            
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg, to_addrs=recipients)
            
            self._log_audit(subject, recipients_str, "REPORT", "SENT")
            return True, "Email sent successfully"
        except Exception as e:
            print(f"Failed to send report email: {str(e)}")
            self._log_audit(subject, recipients_str, "REPORT", "FAILED", error_message=str(e))
            self._add_to_backlog(subject, body, final_html, recipients_str, "REPORT")
            return False, str(e)

    def send_email_alert(self, sensor_name, error_message, severity="DANGER", bypass_cooldown=False):
        """Send email notification about sensor emergency"""
        subject_text = f"[DANGER] Critical System Alert: {sensor_name.upper()} Out of Bounds" if severity == "DANGER" else f"[RECOVERY] System Alert Resolved: {sensor_name.upper()} Restored"
        recipients_raw = self.email_config.get('recipient_email') or self.email_config.get('receiver_email', '')
        recipients = [r.strip() for r in recipients_raw.replace(';', ',').split(',') if r.strip()]
        recipients_str = ", ".join(recipients)

        if self._is_dummy_config():
            print(f"[MAIL-STUB] {severity} Alert for {sensor_name}: {error_message} (Dummy credentials detected)")
            self._log_audit(subject_text, recipients_str, severity, "STUBBED", sensor_name)
            return

        try:
            current_time = datetime.now()
            sensor_state = self.sensor_states.get(sensor_name)
            
            # Enforce cooldown — don't spam for the same sensor unless bypassed
            if sensor_state and not bypass_cooldown and sensor_state['last_notification']:
                consecutive = sensor_state.get('consecutive_alerts', 0)
                if consecutive == 1:
                    cooldown_hours = 6
                elif consecutive >= 2:
                    cooldown_hours = 24
                else:
                    cooldown_hours = 0
                    
                if (current_time - sensor_state['last_notification']).total_seconds() < cooldown_hours * 3600:
                    print(f"DEBUG: Email alert for {sensor_name} skipped due to {cooldown_hours}h cooldown")
                    self._log_audit(subject_text, recipients_str, severity, "SKIPPED_COOLDOWN", sensor_name)
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
            if severity == "DANGER":
                subject_text = f"[DANGER] Critical System Alert: {sensor_name.upper()} Out of Bounds"
            else:
                subject_text = f"[RECOVERY] System Alert Resolved: {sensor_name.upper()} Restored"
            display_severity = "PROBLEM" if severity == "DANGER" else "FIXED"
            msg['Subject'] = Header(subject_text, 'utf-8')
            
            # PLAIN TEXT FALLBACK (Crucial for spam filters)
            plain_text = f"""
            HydroAgrix Farm Message
            
            Status: {display_severity}
            Sensor: {sensor_name.upper()}
            Message: {error_message}
            Time (IST): {current_time.strftime('%Y-%m-%d %I:%M %p')}
            
            """
            if severity == "DANGER":
                plain_text += "Immediate attention required. Sensor readings are outside safe operational bounds. Please inspect hardware and environment."
            else:
                plain_text += "System operation restored to normal parameters."
                
            plain_text += "\n\nThis is an automated system message. Please do not reply."

            # HTML VERSION
            header_bg = "#dc2626" if severity == "DANGER" else "#16a34a"
            alert_name = "CRITICAL ALERT" if severity == "DANGER" else "SYSTEM RESOLVED"
            
            html_body = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f8fafc; color: #334155; margin: 0; padding: 32px 16px; min-height: 100%;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.025);">
                    <div style="background-color: {header_bg}; padding: 32px 24px; text-align: center; border-bottom: 1px solid #e2e8f0;">
                        <h1 style="margin: 0; font-size: 20px; font-weight: 700; color: #ffffff; letter-spacing: 0.05em; text-transform: uppercase;">{alert_name}</h1>
                        <p style="margin: 6px 0 0 0; font-size: 13px; color: #f8fafc; font-weight: 500; opacity: 0.9;">Automatic Farm Message</p>
                    </div>
                    <div style="padding: 32px 24px;">
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px;">
                            <tr style="border-bottom: 1px solid #e2e8f0;">
                                <td style="padding: 12px 8px; color: #64748b; font-weight: 600; width: 35%;">Sensor:</td>
                                <td style="padding: 12px 8px; color: #0f172a; font-weight: 700;">{sensor_name.upper()}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #e2e8f0;">
                                <td style="padding: 12px 8px; color: #64748b; font-weight: 600;">Message:</td>
                                <td style="padding: 12px 8px; color: #0f172a; font-weight: 600;">{error_message}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #e2e8f0;">
                                <td style="padding: 12px 8px; color: #64748b; font-weight: 600;">Time (IST):</td>
                                <td style="padding: 12px 8px; color: #334155;">{current_time.strftime('%Y-%m-%d %I:%M %p')}</td>
                            </tr>
                        </table>
            """
            
            if severity == "DANGER":
                html_body += f"""
                        <div style="background-color: #fef2f2; border: 1px solid #fee2e2; border-left: 4px solid #ef4444; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
                            <h4 style="margin: 0 0 6px 0; color: #991b1b; font-size: 14px; font-weight: 700;">Action Required</h4>
                            <p style="margin: 0; font-size: 13px; color: #991b1b; line-height: 1.5; opacity: 0.9;">
                                Immediate attention required. Sensor readings are outside safe operational bounds. Please inspect hardware and environment.
                            </p>
                        </div>
                """
            else:
                html_body += f"""
                        <div style="background-color: #f0fdf4; border: 1px solid #dcfce7; border-left: 4px solid #16a34a; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
                            <h4 style="margin: 0 0 6px 0; color: #166534; font-size: 14px; font-weight: 700;">System Restored</h4>
                            <p style="margin: 0; font-size: 13px; color: #166534; line-height: 1.5; opacity: 0.9;">
                                System operation restored to normal parameters.
                            </p>
                        </div>
                """
                
            html_body += """
                    </div>
                    <div style="background-color: #f8fafc; padding: 24px; text-align: center; font-size: 11px; color: #64748b; border-top: 1px solid #e2e8f0;">
                        This is an automated system message. Please do not reply directly to this email.
                    </div>
                </div>
            </div>
            """
            
            alt_part = MIMEMultipart('alternative')
            alt_part.attach(MIMEText(plain_text, 'plain'))
            alt_part.attach(MIMEText(html_body, 'html'))
            msg.attach(alt_part)
            
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'], timeout=15) as server:
                server.starttls()
                server.login(self.email_config['sender_email'], self.email_config['sender_password'])
                server.send_message(msg, to_addrs=recipients)
            
            if sensor_state:
                sensor_state['last_notification'] = current_time
                if severity == "DANGER":
                    sensor_state['consecutive_alerts'] = sensor_state.get('consecutive_alerts', 0) + 1
                    if not sensor_state['is_faulted']:
                        sensor_state['is_faulted'] = True
                        sensor_state['fault_start'] = current_time
                elif severity == "RECOVERY":
                    sensor_state['consecutive_alerts'] = 0
            
            print(f"EMAIL {severity} alert sent for {sensor_name}: {error_message}")
            self._log_audit(subject_text, recipients_str, severity, "SENT", sensor_name)
        except Exception as e:
            print(f"Failed to send email alert: {str(e)}")
            self._log_audit(subject_text, recipients_str, severity, "FAILED", sensor_name, str(e))
            if severity == "DANGER":
                self._add_to_backlog(subject_text, plain_text, html_body, recipients_str, "DANGER")

    def _add_to_backlog(self, subject, body_text, body_html, recipients, alert_type):
        try:
            from config import app, db
            from models import EmailBacklog
            with app.app_context():
                # Enforce 50-email cap
                count = EmailBacklog.query.count()
                if count >= 50:
                    oldest = EmailBacklog.query.order_by(EmailBacklog.created_at.asc()).first()
                    if oldest:
                        db.session.delete(oldest)
                db.session.add(EmailBacklog(
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    recipients=recipients,
                    alert_type=alert_type
                ))
                db.session.commit()
        except Exception as e:
            print(f"DEBUG: Failed to save to email backlog: {e}")

    def _log_to_db(self, event_id, category, message, details=None):
        """Save warning/danger logs to the database so they appear in the UI."""
        try:
            from config import app, db
            from models import EventLog
            from sqlalchemy import text
            with app.app_context():
                # Cap EventLog to 5,000 records to prevent table bloat and lock contention
                count = EventLog.query.count()
                if count >= 5000:
                    db.session.execute(text(
                        'DELETE FROM event_log WHERE id IN '
                        '(SELECT id FROM event_log ORDER BY timestamp ASC LIMIT 500)'
                    ))
                details_str = json.dumps(details) if details else None
                db.session.add(EventLog(
                    event_id=event_id,
                    category=category,
                    message=message,
                    details_json=details_str
                ))
                db.session.commit()
        except Exception as e:
            try:
                from config import db
                db.session.rollback()
            except Exception:
                pass
            print(f"DEBUG: Failed to save DB log: {e}")
        finally:
            try:
                from config import db
                db.session.remove()
            except Exception:
                pass

    DEADBANDS = {
        'temperature': 1.0,   # °C
        'humidity':    3.0,   # %
        'tds':         0.3,   # mS/cm
        'ph':          0.2    # pH units
    }

    def check_sensor_reading(self, sensor_name, value, user_limits=None, min_consecutive=1):

        """
        Two-tier check:
        1. DANGER: Is the value beyond absolute safety thresholds? -> EMAIL
        2. WARNING: Is it just slightly outside user's monitoring range? -> LOG ONLY
        
        Args:
            sensor_name: 'ph', 'tds', 'temperature', or 'humidity'
            value: The sensor reading
            user_limits: Optional dict {'min': float, 'max': float} from SensorLimits table
            min_consecutive: Number of consecutive abnormal readings required before alerting (default: 2)
        """
        if user_limits is None or user_limits.get('is_active') == False:
            return

        if sensor_name not in self.DANGER_THRESHOLDS:
            return
        
        state = self.sensor_states[sensor_name]
        
        # NULL value = sensor disconnected = emergency if consecutive >= min_consecutive
        if value is None:
            state['consecutive_null'] = state.get('consecutive_null', 0) + 1
            if state['consecutive_null'] < min_consecutive:
                return
            is_new_fault = not state['is_faulted']
            self.send_email_alert(sensor_name, "Sensor has no reading. A wire might be disconnected.", "DANGER", bypass_cooldown=is_new_fault)
            self._log_to_db(f"{sensor_name.upper()}_NULL", "DANGER", f"Sensor returned NULL - possible hardware disconnection")
            return
        
        state['consecutive_null'] = 0
        danger = self.DANGER_THRESHOLDS[sensor_name]
        
        # TIER 1: Check ABSOLUTE danger thresholds (hardware failure / crop emergency)
        is_dynamic_danger = False
        if sensor_name == 'tds' and user_limits:
            target_max = user_limits.get('max', 2.0)
            if value >= 5.5 or value > (target_max + 2.0):
                is_dynamic_danger = True

        if value < danger['min'] or value > danger['max'] or is_dynamic_danger:
            state['consecutive_danger'] = state.get('consecutive_danger', 0) + 1
            # Debounce transient hardware/EMI spikes: require min_consecutive consecutive
            # abnormal readings before firing an emergency alert email.
            if state['consecutive_danger'] < min_consecutive:
                return
            msg = f"The number is {value}. The safe numbers are {danger['min']} to {danger['max']}."
            is_new_fault = not state['is_faulted']
            self.send_email_alert(sensor_name, msg, "DANGER", bypass_cooldown=is_new_fault)
            self._log_to_db(f"{sensor_name.upper()}_EXTREME", "DANGER", msg, {"value": value})
            return

        
        # Safe reading — reset anomaly debouncing counter
        state['consecutive_danger'] = 0

        # If we get here, the value is within acceptable range
        if state['is_faulted']:
            # Apply deadband to prevent recovery alerts on boundary jitter
            db_val = self.DEADBANDS.get(sensor_name, 0.2)
            abs_ok = (danger['min'] + db_val) <= value <= (danger['max'] - db_val)
            
            if abs_ok:
                # Sensor recovered fully inside the deadband zone
                msg = f"Sensor recovered! Current value: {value}"
                self.send_email_alert(sensor_name, msg, "RECOVERY", bypass_cooldown=True)
                self._log_to_db(f"{sensor_name.upper()}_RECOVERY", "RECOVERY", msg, {"value": value})
                state['is_faulted'] = False

        
        # Minor out-of-range (within user limits but outside monitoring range)?
        # Just log, NEVER email for this.
        if user_limits and (value < user_limits['min'] or value > user_limits['max']):
            current_time = datetime.now()
            last_logged = self.last_warning_logged.get(sensor_name)
            if not last_logged or (current_time - last_logged).total_seconds() >= 15 * 60:
                val_fmt = round(value, 2) if sensor_name in ('ph', 'tds') else round(value, 1)
                min_fmt = round(user_limits['min'], 2) if sensor_name in ('ph', 'tds') else round(user_limits['min'], 1)
                max_fmt = round(user_limits['max'], 2) if sensor_name in ('ph', 'tds') else round(user_limits['max'], 1)
                msg = f"INFO {sensor_name}: {val_fmt} slightly outside user range ({min_fmt}-{max_fmt}) - logged, no alert"
                print(msg)
                self._log_to_db(f"{sensor_name.upper()}_WARNING", "WARNING", f"{sensor_name} at {value} is slightly outside limits.", {"value": value})
                self.last_warning_logged[sensor_name] = current_time

    def load_config(self):
        """Reload email config from file (called by update_email_config route)."""
        self.email_config = self.load_email_config()
        print(f"DEBUG: Email config reloaded. Sender: {self.email_config.get('sender_email', 'N/A')}")

    def _log_audit(self, subject, recipients, alert_type, status, sensor_name=None, error_message=None):
        from config import app, db
        from models import EmailAuditLog
        try:
            with app.app_context():
                # Bounded table size: keep at most 500 records.
                # Use a single bulk DELETE instead of fetching-and-deleting in a Python loop.
                count = EmailAuditLog.query.count()
                if count >= 500:
                    from sqlalchemy import text
                    db.session.execute(text(
                        'DELETE FROM email_audit_log WHERE id IN '
                        '(SELECT id FROM email_audit_log ORDER BY created_at ASC LIMIT 50)'
                    ))
                
                log_entry = EmailAuditLog(
                    subject=subject,
                    recipients=recipients,
                    alert_type=alert_type,
                    status=status,
                    sensor_name=sensor_name,
                    error_message=error_message
                )
                db.session.add(log_entry)
                db.session.commit()
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            print(f"DEBUG: Failed to save email audit log: {e}")
        finally:
            try:
                db.session.remove()
            except Exception:
                pass

