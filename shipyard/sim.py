"""Sim mode: set SHIPYARD_SIM_MODE=true to print instead of act."""

import os


def is_sim_mode() -> bool:
    return os.environ.get("SHIPYARD_SIM_MODE", "").lower() in ("1", "true", "yes")
