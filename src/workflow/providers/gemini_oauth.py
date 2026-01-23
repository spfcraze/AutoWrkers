from typing import AsyncIterator
import json

from .base import WorkflowLLMProvider, GenerationResult, ModelInfo, ProviderStatus
from .gemini import GEMINI_MODELS
from ..models import ProviderConfig
from ..oauth.manager import OAuthManager, oauth_manager

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class GeminiOAuthError(Exception):
    pass


class GeminiOAuthProvider(WorkflowLLMProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    
    def __init__(
        self, 
        config: ProviderConfig, 
        oauth_mgr: OAuthManager | None = None,
        user_id: str = "default",
    ):
        super().__init__(config, api_key="")
        self._oauth_manager = oauth_mgr or oauth_manager
        self._user_id = user_id
        self._client: "httpx.AsyncClient | None" = None

    async def _get_access_token(self) -> str:
        token = await self._oauth_manager.get_valid_access_token("google", self._user_id)
        if not token:
            raise GeminiOAuthError(
                "Google OAuth not configured or token expired. "
                "Please authenticate via the OAuth settings."
            )
        return token

    async def _ensure_client(self):
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx package not installed. Run: pip install httpx")
        
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=120.0,
            )

    async def _get_headers(self) -> dict[str, str]:
        token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _get_model_path(self) -> str:
        model = self.config.model_name or "gemini-2.0-flash"
        if not model.startswith("models/"):
            model = f"models/{model}"
        return model

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
            headers = await self._get_headers()
            model_path = self._get_model_path()
            
            contents = []
            if system_prompt:
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"System: {system_prompt}"}]
                })
                contents.append({
                    "role": "model", 
                    "parts": [{"text": "Understood. I will follow those instructions."}]
                })
            
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature or self.config.temperature,
                    "maxOutputTokens": max_tokens or 8192,
                },
            }
            
            assert self._client is not None
            response = await self._client.post(
                f"/{model_path}:generateContent",
                headers=headers,
                json=payload,
            )
            
            if response.status_code == 401:
                raise GeminiOAuthError("OAuth token expired or invalid. Please re-authenticate.")
            
            response.raise_for_status()
            data = response.json()
            
            candidates = data.get("candidates", [])
            if not candidates:
                raise GeminiOAuthError(f"No candidates in response: {data}")
            
            content_parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(part.get("text", "") for part in content_parts)
            
            usage = data.get("usageMetadata", {})
            tokens_in = usage.get("promptTokenCount", 0)
            tokens_out = usage.get("candidatesTokenCount", 0)
            
            finish_reason = candidates[0].get("finishReason", "UNKNOWN")
            
            await self._set_status(ProviderStatus.READY)
            return GenerationResult(
                content=content,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                model_used=self.config.model_name or "gemini-2.0-flash",
                finish_reason=finish_reason,
                raw_response=data,
            )
        except GeminiOAuthError:
            await self._set_status(ProviderStatus.ERROR)
            raise
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
            headers = await self._get_headers()
            model_path = self._get_model_path()
            
            contents = []
            if system_prompt:
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"System: {system_prompt}"}]
                })
                contents.append({
                    "role": "model",
                    "parts": [{"text": "Understood. I will follow those instructions."}]
                })
            
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature or self.config.temperature,
                    "maxOutputTokens": max_tokens or 8192,
                },
            }
            
            assert self._client is not None
            async with self._client.stream(
                "POST",
                f"/{model_path}:streamGenerateContent?alt=sse",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code == 401:
                    raise GeminiOAuthError("OAuth token expired or invalid. Please re-authenticate.")
                
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            candidates = data.get("candidates", [])
                            if candidates:
                                content_parts = candidates[0].get("content", {}).get("parts", [])
                                for part in content_parts:
                                    text = part.get("text", "")
                                    if text:
                                        yield text
                        except json.JSONDecodeError:
                            continue
            
            await self._set_status(ProviderStatus.READY)
        except GeminiOAuthError:
            await self._set_status(ProviderStatus.ERROR)
            raise
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
            headers = await self._get_headers()
            assert self._client is not None
            response = await self._client.get("/models", headers=headers)
            return response.status_code == 200
        except Exception as e:
            self._last_error = str(e)
            return False

    async def validate_config(self) -> tuple[bool, str]:
        if not self._oauth_manager.is_authenticated("google", self._user_id):
            return False, "Google OAuth not configured. Please authenticate first."
        
        try:
            await self._ensure_client()
            headers = await self._get_headers()
            assert self._client is not None
            response = await self._client.get("/models", headers=headers)
            if response.status_code == 200:
                return True, "OAuth authentication valid"
            elif response.status_code == 401:
                return False, "OAuth token expired or invalid"
            else:
                return False, f"API error: {response.status_code}"
        except Exception as e:
            return False, str(e)

    async def list_models(self) -> list[ModelInfo]:
        models = []
        for model_id, info in GEMINI_MODELS.items():
            models.append(ModelInfo(
                model_id=model_id,
                model_name=model_id,
                provider="gemini_oauth",
                context_length=int(info["context"]),
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
