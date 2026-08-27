#!/bin/bash
# ==============================================================================
# Hydroagrix AI Dosing Controller - Database Diagnostics & Verification Utility
# Target Path on reTerminal: ~/hydro-db-check.sh
# ==============================================================================

DB_PATH="/home/pi/hydroagrix-ai-dosing-controller/backend/instance/mydatabase.db"

# Fallback to local relative path if executing from inside repo folder
if [ ! -f "$DB_PATH" ]; then
    DB_PATH="./backend/instance/mydatabase.db"
fi

if [ ! -f "$DB_PATH" ]; then
    echo "[ERROR] SQLite database file not found at $DB_PATH"
    exit 1
fi

echo "=============================================================================="
echo "         HYDROAGRIX AI DOSING CONTROLLER - DB DIAGNOSTIC CHECK               "
echo "=============================================================================="
echo "Database Location: $DB_PATH"
echo "Check Timestamp:   $(date)"
echo ""

echo "--- 1. Database Integrity & Journal Mode ---"
INTEGRITY=$(sqlite3 "$DB_PATH" "PRAGMA quick_check;")
JOURNAL=$(sqlite3 "$DB_PATH" "PRAGMA journal_mode;")
echo "SQLite Quick Check: $INTEGRITY"
echo "Journal Mode:       $JOURNAL"
echo ""

echo "--- 2. Record Counts ---"
echo "PlantStageStatus Records: $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM plant_stage_status;")"
echo "PlantPreset Records:      $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM plant_preset;")"
echo "SensorLimits Records:     $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sensor_limits;")"
echo "PHData Records (10m):     $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM ph_data;")"
echo "TDSData Records (10m):    $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM tds_data;")"
echo "PumpLog Records:          $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM pump_log;")"
echo "EventLog Records:         $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM event_log;")"
echo "EmailAuditLog Records:    $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM email_audit_log;")"
echo ""

echo "--- 3. Active Grow Cycle Status ---"
sqlite3 -header -column "$DB_PATH" "SELECT plant_name, plant_stage, state, cycle_start_date FROM plant_stage_status LIMIT 1;"
echo ""

echo "--- 4. Active Sensor Limits ---"
sqlite3 -header -column "$DB_PATH" "SELECT sensor_type, min_value, max_value, is_active FROM sensor_limits;"
echo ""

echo "--- 5. Recent System Warnings & Danger Logs (Last 5) ---"
sqlite3 -header -column "$DB_PATH" "SELECT timestamp, category, message FROM event_log WHERE category IN ('WARNING', 'DANGER', 'ALARM') ORDER BY id DESC LIMIT 5;"
echo ""

echo "--- 6. Solution Tanks Inventory ---"
sqlite3 -header -column "$DB_PATH" "SELECT tank_id, name, capacity_ml, current_volume_ml, consecutive_blocked_attempts FROM solution_tanks ORDER BY tank_id ASC;"
echo ""

echo "--- 7. Recent Pump Dosing Actions (Last 5) ---"
sqlite3 -header -column "$DB_PATH" "SELECT timestamp, pump_name, duration, trigger_type FROM pump_log ORDER BY id DESC LIMIT 5;"
echo ""

echo "--- 8. Database File Sizes & Disk Usage ---"
ls -lh "$DB_PATH"* 2>/dev/null || echo "No database files matched."
echo ""

echo "=============================================================================="
echo "                         DIAGNOSTIC CHECK COMPLETE                            "
echo "=============================================================================="
