from typing import AsyncIterator
import json

from .base import WorkflowLLMProvider, GenerationResult, ModelInfo, ProviderStatus
from ..models import ProviderConfig

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaProvider(WorkflowLLMProvider):
    
    def __init__(self, config: ProviderConfig, api_key: str = ""):
        super().__init__(config, api_key)
        self._client: "httpx.AsyncClient | None" = None
        self._models_cache: list[ModelInfo] = []

    def _get_base_url(self) -> str:
        return self.config.api_url or DEFAULT_OLLAMA_URL

    async def _ensure_client(self):
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx package not installed. Run: pip install httpx")
        
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._get_base_url(),
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
            payload: dict = {
                "model": self.config.model_name or "llama3.2:latest",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature or self.config.temperature,
                },
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens
            
            assert self._client is not None
            response = await self._client.post("/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            
            await self._set_status(ProviderStatus.READY)
            return GenerationResult(
                content=data.get("response", ""),
                tokens_input=data.get("prompt_eval_count", 0),
                tokens_output=data.get("eval_count", 0),
                model_used=data.get("model", self.config.model_name),
                finish_reason="stop" if data.get("done") else "unknown",
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
            payload: dict = {
                "model": self.config.model_name or "llama3.2:latest",
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": temperature or self.config.temperature,
                },
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens
            
            assert self._client is not None
            async with self._client.stream("POST", "/api/generate", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            content = data.get("response", "")
                            if content:
                                yield content
                            if data.get("done"):
                                break
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
            response = await self._client.get("/api/tags")
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
            response = await self._client.get("/api/tags")
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            models = []
            
            for m in data.get("models", []):
                name = m.get("name", "")
                details = m.get("details", {})
                
                context_length = 8192
                param_size = details.get("parameter_size", "")
                if "70b" in param_size.lower():
                    context_length = 131072
                elif "32b" in param_size.lower() or "34b" in param_size.lower():
                    context_length = 65536
                elif "13b" in param_size.lower() or "14b" in param_size.lower():
                    context_length = 32768
                elif "7b" in param_size.lower() or "8b" in param_size.lower():
                    context_length = 16384
                
                models.append(ModelInfo(
                    model_id=name,
                    model_name=name,
                    provider="ollama",
                    context_length=context_length,
                    supports_tools="tool" in name.lower() or "function" in name.lower(),
                    supports_vision="vision" in name.lower() or "llava" in name.lower(),
                    supports_streaming=True,
                    cost_input_per_1k=0.0,
                    cost_output_per_1k=0.0,
                    metadata={
                        "family": details.get("family", ""),
                        "parameter_size": param_size,
                        "quantization": details.get("quantization_level", ""),
                        "format": details.get("format", ""),
                        "size": m.get("size", 0),
                    },
                ))
            
            self._models_cache = models
            return models
        except Exception as e:
            self._last_error = str(e)
            return []

    async def pull_model(self, model_name: str) -> bool:
        try:
            await self._ensure_client()
            assert self._client is not None
            response = await self._client.post(
                "/api/pull",
                json={"name": model_name, "stream": False},
                timeout=600.0,
            )
            return response.status_code == 200
        except Exception as e:
            self._last_error = str(e)
            return False

    async def delete_model(self, model_name: str) -> bool:
        try:
            await self._ensure_client()
            assert self._client is not None
            request = self._client.build_request(
                "DELETE",
                "/api/delete",
                json={"name": model_name},
            )
            response = await self._client.send(request)
            return response.status_code == 200
        except Exception as e:
            self._last_error = str(e)
            return False

    async def get_model_info(self, model_name: str) -> dict | None:
        try:
            await self._ensure_client()
            assert self._client is not None
            response = await self._client.post(
                "/api/show",
                json={"name": model_name},
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            self._last_error = str(e)
            return None

    def clear_cache(self):
        self._models_cache = []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


async def detect_ollama(url: str = DEFAULT_OLLAMA_URL) -> tuple[bool, list[str]]:
    if not HTTPX_AVAILABLE:
        return False, []
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                return True, models
    except Exception:
        pass
    
    return False, []
