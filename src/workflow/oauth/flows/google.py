import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from ..storage import OAuthToken, OAuthClientConfig


GOOGLE_GEMINI_SCOPES = [
    "https://www.googleapis.com/auth/generative-language.retriever",
    "https://www.googleapis.com/auth/cloud-platform",
    "openid",
    "email",
]


class GoogleOAuthFlowError(Exception):
    pass


class GoogleOAuthFlow:
    TOKEN_URI = "https://oauth2.googleapis.com/token"
    
    def __init__(self, client_config: OAuthClientConfig):
        if client_config.provider != "google":
            raise ValueError("GoogleOAuthFlow requires a Google client config")
        
        self._client_config = client_config
        self._installed = client_config.client_config.get("installed", {})
        self._web = client_config.client_config.get("web", {})
        
        self._config = self._installed or self._web
        if not self._config:
            raise ValueError("Invalid Google OAuth client config: missing 'installed' or 'web' key")
        
        self._client_id = self._config.get("client_id", "")
        self._client_secret = self._config.get("client_secret", "")
        
        if not self._client_id or not self._client_secret:
            raise ValueError("Invalid Google OAuth client config: missing client_id or client_secret")
    
    @property
    def client_id(self) -> str:
        return self._client_id
    
    @property
    def client_secret(self) -> str:
        return self._client_secret
    
    async def run_local_server_flow(
        self, 
        scopes: list[str] | None = None,
        port: int = 0,
        open_browser: bool = True,
    ) -> OAuthToken:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as e:
            raise GoogleOAuthFlowError(
                "google-auth-oauthlib not installed. "
                "Install with: pip install google-auth-oauthlib"
            ) from e
        
        scopes = scopes or GOOGLE_GEMINI_SCOPES
        
        flow = InstalledAppFlow.from_client_config(
            self._client_config.client_config,
            scopes=scopes,
        )
        
        loop = asyncio.get_event_loop()
        creds = await loop.run_in_executor(
            None,
            lambda: flow.run_local_server(
                port=port, 
                open_browser=open_browser,
                prompt="consent",
            )
        )
        
        return self._credentials_to_token(creds, scopes)
    
    async def refresh_token(self, token: OAuthToken) -> OAuthToken | None:
        if not token.refresh_token:
            return None
        
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError:
            return None
        
        creds = Credentials(
            token=token.access_token,
            refresh_token=token.refresh_token,
            token_uri=token.token_uri or self.TOKEN_URI,
            client_id=token.client_id or self._client_id,
            client_secret=token.client_secret or self._client_secret,
            scopes=token.scopes,
        )
        
        if not creds.expired or not creds.refresh_token:
            return token
        
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: creds.refresh(Request())
            )
        except Exception:
            return None
        
        return self._credentials_to_token(creds, token.scopes, token.user_id)
    
    def _credentials_to_token(
        self, 
        creds: Any,
        scopes: list[str] | None = None,
        user_id: str = "default",
    ) -> OAuthToken:
        expires_at = None
        if creds.expiry:
            if creds.expiry.tzinfo:
                expires_at = creds.expiry.replace(tzinfo=None)
            else:
                expires_at = creds.expiry
        
        account_email = None
        if hasattr(creds, 'id_token') and creds.id_token:
            try:
                import base64
                parts = creds.id_token.split('.')
                if len(parts) >= 2:
                    payload = parts[1]
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += '=' * padding
                    decoded = base64.urlsafe_b64decode(payload)
                    id_token_data = json.loads(decoded)
                    account_email = id_token_data.get('email')
            except Exception:
                pass
        
        return OAuthToken(
            provider="google",
            access_token=creds.token,
            refresh_token=creds.refresh_token,
            token_uri=creds.token_uri or self.TOKEN_URI,
            client_id=creds.client_id or self._client_id,
            client_secret=creds.client_secret or self._client_secret,
            scopes=scopes or list(creds.scopes) if creds.scopes else None,
            expires_at=expires_at,
            account_email=account_email,
            user_id=user_id,
        )


async def refresh_google_token(token: OAuthToken) -> OAuthToken | None:
    from ..storage import oauth_storage
    
    client_config = oauth_storage.load_client_config("google")
    if not client_config:
        return None
    
    flow = GoogleOAuthFlow(client_config)
    return await flow.refresh_token(token)
