from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    model: str
    api_key_env: str
    api_base: str | None = None


GEMINI_FLASH = ModelConfig(
    model="gemini/gemini-2.5-flash",
    api_key_env="GEMINI_API_KEY",
)

GEMINI_PRO = ModelConfig(
    model="gemini/gemini-2.5-pro",
    api_key_env="GEMINI_API_KEY",
)

CLAUDE_SONNET = ModelConfig(
    model="anthropic/claude-sonnet-4-6",
    api_key_env="ANTHROPIC_API_KEY",
)

CLAUDE_OPUS = ModelConfig(
    model="anthropic/claude-opus-4-7",
    api_key_env="ANTHROPIC_API_KEY",
)

GITHUB_COPILOT_GPT4O = ModelConfig(
    model="openai/gpt-4o",
    api_key_env="GITHUB_COPILOT_API_KEY",
    api_base="https://models.inference.ai.azure.com",
)

GITHUB_COPILOT_O1_REASONING = ModelConfig(
    model="openai/o1",
    api_key_env="GITHUB_COPILOT_API_KEY",
    api_base="https://models.inference.ai.azure.com",
)

QWEN_CODER = ModelConfig(
    model="ollama_chat/qwen2.5-coder:3b",
    api_key_env="",
    api_base="http://ollama.hallm.local",
)

DEEPSEEK_R1 = ModelConfig(
    model="ollama_chat/deepseek-r1:8b",
    api_key_env="",
    api_base="http://ollama.hallm.local",
)
