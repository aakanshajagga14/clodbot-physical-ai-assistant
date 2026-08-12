from dataclasses import dataclass, replace


@dataclass(frozen=True)
class MachineState:
    """A point-in-time, immutable view of the simulated workstation."""

    name: str = "Hydraulic Pump A"
    power_on: bool = False
    pressure_psi: float = 0.0
    isolation_valve_open: bool = False
    lockout_applied: bool = False
    lockout_verified: bool = False
    emergency_stop: bool = False
    worker_in_hazard_zone: bool = False
    gas_ppm: float = 0.0
    pressure_cap_removed: bool = False
    filter_installed: bool = True
    work_area_clear: bool = True

    def __post_init__(self) -> None:
        if self.pressure_psi < 0:
            raise ValueError("pressure_psi cannot be negative")
        if self.gas_ppm < 0:
            raise ValueError("gas_ppm cannot be negative")
        if self.lockout_verified and not self.lockout_applied:
            raise ValueError("lockout cannot be verified unless it is applied")
        if not self.filter_installed and not self.pressure_cap_removed:
            raise ValueError("a removed filter requires an open pressure cap")

    def evolve(self, **changes: object) -> "MachineState":
        return replace(self, **changes)
