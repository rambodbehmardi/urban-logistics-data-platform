"""Synthetic urban-logistics data platform."""

from .generate import generate_batches
from .pipeline import get_summary, run_pipeline

__all__ = ["generate_batches", "get_summary", "run_pipeline"]

__version__ = "0.1.0"
