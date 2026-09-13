"""Suite-wide fixtures."""

from fablestar import telemetry

# Command tests exercise real handlers that emit telemetry; without this they
# append fake kills and missions to the live soak log in logs/.
telemetry.disable()
