"""CPU-oriented speech recognition using an approved free Hugging Face model.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from ..config import get_settings


@lru_cache(maxsize=1)
def inference_pool() -> ThreadPoolExecutor:
    """Create a bounded OS-scheduled worker pool for blocking model inference."""
    return ThreadPoolExecutor(max_workers=get_settings().training_thread_workers, thread_name_prefix="hcp-inference")


@lru_cache(maxsize=2)
def speech_pipeline(model_id: str):
    """Load a CPU speech-recognition pipeline only when audio is requested."""
    from transformers import pipeline

    get_settings().require_allowed_model(model_id)
    return pipeline("automatic-speech-recognition", model=model_id, device=-1)


async def transcribe_audio(data: bytes, model_id: str | None = None) -> str:
    """Transcribe audio on a bounded worker with an administrator-defined timeout."""
    settings = get_settings()
    if len(data) > settings.upload_max_bytes:
        raise ValueError("Audio upload exceeds UPLOAD_MAX_BYTES")
    selected = model_id or settings.audio_model
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(inference_pool(), lambda: speech_pipeline(selected)(data)["text"])
    return str(await asyncio.wait_for(future, timeout=settings.inference_timeout_seconds)).strip()
