from typing import AsyncIterator
import json

from .base import WorkflowLLMProvider, GenerationResult, ModelInfo, ProviderStatus
from ..models import ProviderConfig

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


DEFAULT_LM_STUDIO_URL = "http://localhost:1234/v1"


class LMStudioProvider(WorkflowLLMProvider):
    
    def __init__(self, config: ProviderConfig, api_key: str = ""):
        super().__init__(config, api_key)
        self._client: "httpx.AsyncClient | None" = None
        self._models_cache: list[ModelInfo] = []

    def _get_base_url(self) -> str:
        url = self.config.api_url or DEFAULT_LM_STUDIO_URL
        if not url.endswith("/v1"):
            url = url.rstrip("/") + "/v1"
        return url

    async def _ensure_client(self):
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx package not installed. Run: pip install httpx")
        
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._get_base_url(),
                headers={"Content-Type": "application/json"},
                timeout=300.0,
            )

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
            
            model = self.config.model_name
            if not model:
                models = await self.list_models()
                model = models[0].model_id if models else "local-model"
            
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature or self.config.temperature,
                "max_tokens": max_tokens or 8192,
                "stream": False,
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
                model_used=data.get("model", model),
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
            
            model = self.config.model_name
            if not model:
                models = await self.list_models()
                model = models[0].model_id if models else "local-model"
            
            payload = {
                "model": model,
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
        if self._models_cache:
            return self._models_cache
        
        try:
            await self._ensure_client()
            assert self._client is not None
            response = await self._client.get("/models")
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            models = []
            
            for m in data.get("data", []):
                model_id = m.get("id", "")
                
                context_length = 8192
                if "32k" in model_id.lower():
                    context_length = 32768
                elif "16k" in model_id.lower():
                    context_length = 16384
                elif "128k" in model_id.lower():
                    context_length = 131072
                elif "70b" in model_id.lower():
                    context_length = 131072
                elif "34b" in model_id.lower() or "32b" in model_id.lower():
                    context_length = 65536
                elif "13b" in model_id.lower() or "14b" in model_id.lower():
                    context_length = 32768
                elif "7b" in model_id.lower() or "8b" in model_id.lower():
                    context_length = 16384
                
                models.append(ModelInfo(
                    model_id=model_id,
                    model_name=model_id,
                    provider="lm_studio",
                    context_length=context_length,
                    supports_tools=False,
                    supports_vision="vision" in model_id.lower() or "llava" in model_id.lower(),
                    supports_streaming=True,
                    cost_input_per_1k=0.0,
                    cost_output_per_1k=0.0,
                    metadata={
                        "owned_by": m.get("owned_by", ""),
                    },
                ))
            
            self._models_cache = models
            return models
        except Exception as e:
            self._last_error = str(e)
            return []

    def clear_cache(self):
        self._models_cache = []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


async def detect_lm_studio(url: str = DEFAULT_LM_STUDIO_URL) -> tuple[bool, list[str]]:
    if not HTTPX_AVAILABLE:
        return False, []
    
    base_url = url
    if not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/models")
            if response.status_code == 200:
                data = response.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                return True, models
    except Exception:
        pass
    
    return False, []
