"""Form filling. One adapter per ATS, a verification gate, and a runner that decides what happens next."""
from __future__ import annotations

from .ashby import AshbyAdapter
from .base import Adapter
from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter

ADAPTERS: dict[str, type[Adapter]] = {"greenhouse": GreenhouseAdapter, "lever": LeverAdapter, "ashby": AshbyAdapter}
