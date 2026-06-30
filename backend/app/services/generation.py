# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for generation."""
from functools import lru_cache

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from ..config import get_settings
from .model_router import resolve_torch_device


@lru_cache(maxsize=1)
def components():
    """Perform the components operation."""
    settings = get_settings()
    device = resolve_torch_device(settings.compute_device)
    tokenizer = AutoTokenizer.from_pretrained(settings.generation_model)
    model = AutoModelForSeq2SeqLM.from_pretrained(settings.generation_model).to(device).eval()
    return tokenizer, model, device


def generate_text(prompt: str, maximum_tokens: int = 320) -> str:
    """Perform the generate text operation."""
    tokenizer, model, device = components()
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=maximum_tokens, do_sample=False)
    return tokenizer.decode(output[0], skip_special_tokens=True).strip()

