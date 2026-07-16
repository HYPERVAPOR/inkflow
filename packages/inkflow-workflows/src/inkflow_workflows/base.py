"""Workflow abstraction and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from inkflow_core.config import Config
from inkflow_core.models import Script
from inkflow_core.types import WorkflowOutput
from inkflow_generators.cost import CostTracker


class Workflow(ABC):
    """Base class for all InkFlow video generation workflows."""

    name: ClassVar[str]

    def __init__(self, config: Config, cost_tracker: CostTracker) -> None:
        self.config = config
        self.cost_tracker = cost_tracker

    @abstractmethod
    async def run(self, script: Script) -> WorkflowOutput:
        """Run the workflow and return generated media paths."""
        ...


class WorkflowRegistry:
    """Registry mapping workflow names to workflow classes."""

    _registry: ClassVar[dict[str, type[Workflow]]] = {}

    @classmethod
    def register(cls, workflow_class: type[Workflow]) -> type[Workflow]:
        """Register a workflow class and return it unchanged."""
        cls._registry[workflow_class.name] = workflow_class
        return workflow_class

    @classmethod
    def resolve(cls, script: Script) -> type[Workflow]:
        """Return the workflow class for the given script."""
        workflow_name = script.resolved_workflow
        if workflow_name not in cls._registry:
            raise ValueError(f"Unknown workflow: {workflow_name}")
        return cls._registry[workflow_name]

    @classmethod
    def names(cls) -> list[str]:
        """Return all registered workflow names."""
        return list(cls._registry.keys())
