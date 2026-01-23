from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Awaitable
from enum import Enum

from ..models import ProviderConfig, ProviderType


class ProviderStatus(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    GENERATING = "generating"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass
class GenerationResult:
    content: str
    tokens_input: int = 0
    tokens_output: int = 0
    model_used: str = ""
    finish_reason: str = ""
    raw_response: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.tokens_input + self.tokens_output


@dataclass
class ModelInfo:
    model_id: str
    model_name: str
    provider: str
    context_length: int = 8192
    supports_tools: bool = False
    supports_vision: bool = False
    supports_streaming: bool = True
    cost_input_per_1k: float = 0.0
    cost_output_per_1k: float = 0.0
    metadata: dict = field(default_factory=dict)


class WorkflowLLMProvider(ABC):
    
    def __init__(self, config: ProviderConfig, api_key: str = ""):
        self.config = config
        self.api_key = api_key
        self._status = ProviderStatus.IDLE
        self._status_callback: Callable[[ProviderStatus], Awaitable[None]] | None = None
        self._last_error: str = ""

    @property
    def provider_type(self) -> ProviderType:
        return self.config.provider_type

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def status(self) -> ProviderStatus:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    def set_status_callback(self, callback: Callable[[ProviderStatus], Awaitable[None]]):
        self._status_callback = callback

    async def _set_status(self, status: ProviderStatus):
        self._status = status
        if self._status_callback:
            await self._status_callback(status)

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> GenerationResult:
        pass

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        pass

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        pass

    def estimate_cost(self, tokens_input: int, tokens_output: int) -> float:
        from ..models import estimate_cost
        return estimate_cost(self.config.model_name, tokens_input, tokens_output)

    async def validate_config(self) -> tuple[bool, str]:
        if self.config.provider_type in (
            ProviderType.GEMINI_SDK,
            ProviderType.OPENAI,
            ProviderType.OPENROUTER,
            ProviderType.GEMINI_OPENROUTER,
        ):
            if not self.api_key:
                return False, f"API key required for {self.config.provider_type.value}"
        
        if not await self.check_health():
            return False, f"Provider health check failed: {self._last_error}"
        
        return True, ""
