"""Temporal client connection, shared by the worker, CLI, and Streamlit."""

from __future__ import annotations

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from ..config import get_settings


async def get_temporal_client() -> Client:
    settings = get_settings()
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
