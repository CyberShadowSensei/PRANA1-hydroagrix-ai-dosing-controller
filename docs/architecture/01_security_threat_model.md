# Security Architecture & Threat Model

## Threat Mitigations
- **Dosing Runaway**: Hardcoded hardware emergency stops (`hal.emergency_stop_all()`) and mid-dose sensor cutoff.
- **Physical Acidification**: Dynamic Cross-Tank Dependency Lock prevents nutrient additions if pH UP is depleted.
- **Power Failure**: Atomic configuration persistence and boot-time pin LOW pull-down.
