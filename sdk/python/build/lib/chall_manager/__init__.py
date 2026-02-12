"""
Chall-Manager Python SDK

A Python module for generating Pulumi scenarios for chall-manager.
Supports ExposedMonopod, ExposedMultipod, and Kompose deployments.
"""

__version__ = "0.1.0"
__all__ = [
    "Scenario",
    "MonopodScenario",
    "MultipodScenario",
    "KomposeScenario",
    "Container",
    "PortBinding",
    "ExposeType",
    "Rule",
    "ScenarioBuilder",
    "quick_monopod",
    "quick_multipod",
    "quick_kompose",
]

from .base import Scenario
from .containers import Container, PortBinding, ExposeType, Rule
from .monopod import MonopodScenario
from .multipod import MultipodScenario
from .kompose import KomposeScenario
from .builder import ScenarioBuilder, quick_monopod, quick_multipod, quick_kompose
