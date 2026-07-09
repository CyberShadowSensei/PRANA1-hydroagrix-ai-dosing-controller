# Hydroponics Deployment Notes

Status: Active

Classification: Verified by user statement unless later superseded by test results.

## Development and Deployment Model

Verified:

- Development and code maintenance will be performed on the laptop.
- The laptop will maintain a mirror copy of the complete codebase.
- The reTerminal will contain the deployed/testing version of the code.
- Code will be transferred to the reTerminal for testing and deployment using SCP or SSH.
- The codebase should be pushed to GitHub periodically for version history, backup, and collaboration.

## reTerminal Connection Details

Verified:

- IP address: `192.168.29.9`
- Username: `raspberrypi`
- Remote project directory: `~/tools/` (confirmed 2026-06-20 by SSH `ls` inspection)
- Calibration config directory: `~/tools/config/`

Unknown:

- SSH key configuration.
- GitHub repository URL.
- Preferred branch strategy.

## Recommended Workflow

Proposed:

1. Edit and maintain source code on the laptop.
2. Commit meaningful changes locally.
3. Copy the updated code to the reTerminal using SCP or synchronize with a dedicated deployment command.
4. Run hardware tests on the reTerminal.
5. Record raw observations and test results in the project documentation.
6. Push stable checkpoints to GitHub.

## Example Transfer Commands

These commands are examples only. Confirm the remote project directory before treating them as the deployment standard.

Copy one file:

```powershell
scp "e:\Hydroagrix Ai\Ai Dosing Unit\tools\temperature_source.py" raspberrypi@192.168.29.9:~/tools/temperature_source.py
```

Copy all tool scripts at once:

```powershell
scp "e:\Hydroagrix Ai\Ai Dosing Unit\tools\*.py" raspberrypi@192.168.29.9:~/tools/
```

Open an SSH session:

```powershell
ssh raspberrypi@192.168.29.9
```

Run the EC raw monitor on the reTerminal:

```bash
python3 ~/tools/ec_raw_monitor.py --channels 0,1,2,3 --interval 1
```

Save EC raw readings to CSV:

```bash
python3 ~/tools/ec_raw_monitor.py --channels 0,1,2,3 --interval 1 --csv ~/tools/logs/ec_raw_readings.csv
```

## Documentation Requirement

After each deployment or hardware test, record:

- Date and time.
- Code version or commit hash, if available.
- File or folder transferred.
- reTerminal destination path.
- Test command executed.
- Raw observations.
- Conclusion.
- Recommended next action.
