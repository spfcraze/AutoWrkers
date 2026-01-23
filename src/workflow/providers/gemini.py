from typing import AsyncIterator
import json

from .base import WorkflowLLMProvider, GenerationResult, ModelInfo, ProviderStatus
from ..models import ProviderConfig, ProviderType

try:
    import google.generativeai as genai
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    GEMINI_SDK_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


GEMINI_MODELS = {
    "gemini-2.0-flash": {"context": 1048576, "input": 0.0001, "output": 0.0004},
    "gemini-1.5-pro": {"context": 2097152, "input": 0.00125, "output": 0.005},
    "gemini-1.5-flash": {"context": 1048576, "input": 0.000075, "output": 0.0003},
    "gemini-1.5-flash-8b": {"context": 1048576, "input": 0.0000375, "output": 0.00015},
}


class GeminiSDKProvider(WorkflowLLMProvider):
    
    def __init__(self, config: ProviderConfig, api_key: str = ""):
        super().__init__(config, api_key)
        self._client: "genai.GenerativeModel | None" = None

    async def _ensure_client(self):
        if not GEMINI_SDK_AVAILABLE:
            raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
        
        if self._client is None:
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.config.model_name or "gemini-2.0-flash")

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> GenerationResult:
        await self._ensure_client()
        await self._set_status(ProviderStatus.GENERATING)
        
        try:
            generation_config = genai.GenerationConfig(
                temperature=temperature or self.config.temperature,
                max_output_tokens=max_tokens or 8192,
            )
            
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            
            assert self._client is not None
            response = self._client.generate_content(
                full_prompt,
                generation_config=generation_config,
            )
            
            tokens_in = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            tokens_out = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            
            await self._set_status(ProviderStatus.READY)
            return GenerationResult(
                content=response.text,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                model_used=self.config.model_name or "gemini-2.0-flash",
                finish_reason=response.candidates[0].finish_reason.name if response.candidates else "unknown",
            )
        except Exception as e:
            self._last_error = str(e)
            await self._set_status(ProviderStatus.ERROR)
            raise

    async def _generate_stream_impl(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        await self._ensure_client()
        await self._set_status(ProviderStatus.GENERATING)
        
        try:
            generation_config = genai.GenerationConfig(
                temperature=temperature or self.config.temperature,
                max_output_tokens=max_tokens or 8192,
            )
            
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            
            assert self._client is not None
            response = self._client.generate_content(
                full_prompt,
                generation_config=generation_config,
                stream=True,
            )
            
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            
            await self._set_status(ProviderStatus.READY)
        except Exception as e:
            self._last_error = str(e)
            await self._set_status(ProviderStatus.ERROR)
            raise

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        return self._generate_stream_impl(prompt, system_prompt, temperature, max_tokens)

    async def check_health(self) -> bool:
        try:
            await self._ensure_client()
            assert self._client is not None
            self._client.generate_content("test", generation_config=genai.GenerationConfig(max_output_tokens=1))
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    async def list_models(self) -> list[ModelInfo]:
        models = []
        for model_id, info in GEMINI_MODELS.items():
            models.append(ModelInfo(
                model_id=model_id,
                model_name=model_id,
                provider="gemini_sdk",
                context_length=info["context"],
                supports_tools=True,
                supports_vision=True,
                supports_streaming=True,
                cost_input_per_1k=info["input"],
                cost_output_per_1k=info["output"],
            ))
        return models


class GeminiOpenRouterProvider(WorkflowLLMProvider):
    
    OPENROUTER_URL = "https://openrouter.ai/api/v1"
    
    MODEL_MAP = {
        "gemini-2.0-flash": "google/gemini-2.0-flash-001",
        "gemini-1.5-pro": "google/gemini-pro-1.5",
        "gemini-1.5-flash": "google/gemini-flash-1.5",
    }

    def __init__(self, config: ProviderConfig, api_key: str = ""):
        super().__init__(config, api_key)
        self._client: "httpx.AsyncClient | None" = None

    async def _ensure_client(self):
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx package not installed. Run: pip install httpx")
        
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://ultraclaude.local",
                    "X-Title": "UltraClaude Workflow",
                },
                timeout=120.0,
            )

    def _get_model_id(self) -> str:
        model = self.config.model_name or "gemini-2.0-flash"
        return self.MODEL_MAP.get(model, f"google/{model}")

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> GenerationResult:
        await self._ensure_client()
        await self._set_status(ProviderStatus.GENERATING)
        
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self._get_model_id(),
                "messages": messages,
                "temperature": temperature or self.config.temperature,
                "max_tokens": max_tokens or 8192,
            }
            
            assert self._client is not None
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            usage = data.get("usage", {})
            choice = data.get("choices", [{}])[0]
            
            await self._set_status(ProviderStatus.READY)
            return GenerationResult(
                content=choice.get("message", {}).get("content", ""),
                tokens_input=usage.get("prompt_tokens", 0),
                tokens_output=usage.get("completion_tokens", 0),
                model_used=data.get("model", self._get_model_id()),
                finish_reason=choice.get("finish_reason", "unknown"),
                raw_response=data,
            )
        except Exception as e:
            self._last_error = str(e)
            await self._set_status(ProviderStatus.ERROR)
            raise

    async def _generate_stream_impl(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        await self._ensure_client()
        await self._set_status(ProviderStatus.GENERATING)
        
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self._get_model_id(),
                "messages": messages,
                "temperature": temperature or self.config.temperature,
                "max_tokens": max_tokens or 8192,
                "stream": True,
            }
            
            assert self._client is not None
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
            
            await self._set_status(ProviderStatus.READY)
        except Exception as e:
            self._last_error = str(e)
            await self._set_status(ProviderStatus.ERROR)
            raise

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        return self._generate_stream_impl(prompt, system_prompt, temperature, max_tokens)

    async def check_health(self) -> bool:
        try:
            await self._ensure_client()
            assert self._client is not None
            response = await self._client.get("/models")
            return response.status_code == 200
        except Exception as e:
            self._last_error = str(e)
            return False

    async def list_models(self) -> list[ModelInfo]:
        models = []
        for short_name, openrouter_id in self.MODEL_MAP.items():
            info = GEMINI_MODELS.get(short_name, {"context": 8192, "input": 0.001, "output": 0.002})
            models.append(ModelInfo(
                model_id=openrouter_id,
                model_name=short_name,
                provider="gemini_openrouter",
                context_length=info["context"],
                supports_tools=True,
                supports_vision=True,
                supports_streaming=True,
                cost_input_per_1k=info["input"],
                cost_output_per_1k=info["output"],
            ))
        return models

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


def create_gemini_provider(config: ProviderConfig, api_key: str) -> WorkflowLLMProvider:
    if config.provider_type == ProviderType.GEMINI_SDK:
        return GeminiSDKProvider(config, api_key)
    elif config.provider_type == ProviderType.GEMINI_OPENROUTER:
        return GeminiOpenRouterProvider(config, api_key)
    else:
        raise ValueError(f"Invalid provider type for Gemini: {config.provider_type}")
