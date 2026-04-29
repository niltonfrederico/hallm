"""Thin async wrappers around litellm, optionally driven by a ModelConfig."""

import os
from collections.abc import AsyncIterator

import litellm
from hallm.core.settings import settings
from hallm.litellm.models import ModelConfig
from litellm import ModelResponse

litellm.drop_params = True

type Messages = list[dict[str, str]]


def _build_kwargs(model: ModelConfig | None, extra: dict) -> dict:
    if model is None:
        kwargs: dict = {"model": settings.litellm_model, **extra}
    else:
        kwargs = {
            "model": model.model,
            "api_key": os.environ.get(model.api_key_env, ""),
            **extra,
        }
        if model.api_base:
            kwargs["api_base"] = model.api_base

    if settings.llm_timeout is not None:
        kwargs.setdefault("timeout", settings.llm_timeout)
    return kwargs


async def complete(messages: Messages, model: ModelConfig | None = None, **kwargs) -> ModelResponse:
    return await litellm.acompletion(
        messages=messages,
        **_build_kwargs(model, kwargs),
    )


async def stream(
    messages: Messages, model: ModelConfig | None = None, **kwargs
) -> AsyncIterator[str]:
    response = await litellm.acompletion(
        messages=messages,
        stream=True,
        **_build_kwargs(model, kwargs),
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
