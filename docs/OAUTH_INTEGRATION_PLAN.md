# OAuth Integration Plan for UltraClaude

## Executive Summary

This document outlines the plan to add OAuth authentication to UltraClaude's Multi-LLM Workflow Pipeline. OAuth will be an **alternative** to API keys for providers that support it, offering:

1. **No API key management** - Users authenticate via browser, tokens stored securely
2. **Free-tier access** - Some providers offer free access via OAuth (e.g., Gemini AI Studio)
3. **Better security** - No plaintext API keys to manage or leak

## Current Architecture

### Provider System
```
src/workflow/providers/
├── base.py              # WorkflowLLMProvider base class
├── registry.py          # ModelRegistry - creates providers, manages API keys
├── gemini.py            # GeminiSDKProvider (uses API key)
├── openai.py            # OpenAIProvider, OpenRouterProvider  
├── ollama.py            # OllamaProvider (local, no auth)
└── lm_studio.py         # LMStudioProvider (local, no auth)
```

### Current Auth Flow
```python
# models.py - ProviderKeys stores API keys
@dataclass
class ProviderKeys:
    gemini_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_url: str = "http://localhost:11434"
    lm_studio_url: str = "http://localhost:1234/v1"

# registry.py - Creates provider with API key
def create_provider(self, config: ProviderConfig) -> WorkflowLLMProvider:
    keys = self._load_keys()
    api_key = keys.get_key(config.provider_type)
    return GeminiSDKProvider(config, api_key)
```

## Target OAuth Providers

| Provider | OAuth Type | Priority | Benefit |
|----------|------------|----------|---------|
| **Google Gemini** | OAuth 2.0 (InstalledAppFlow) | HIGH | Free tier via AI Studio, large context |
| **GitHub Copilot** | Device Code Flow | MEDIUM | Existing subscription, no extra cost |
| **OpenAI** | None (API key only) | N/A | No OAuth support |
| **OpenRouter** | None (API key only) | N/A | No OAuth support |

### Priority: Google Gemini OAuth (Phase 1)

**Why First:**
- Most valuable: Free tier with 2M context Gemini models
- Well-documented OAuth flow via `google-auth-oauthlib`
- Users likely have Google accounts already
- Standard OAuth 2.0 InstalledAppFlow pattern

---

## Architecture Design

### New Components

```
src/workflow/
├── oauth/
│   ├── __init__.py
│   ├── manager.py       # OAuthManager - token lifecycle
│   ├── storage.py       # Secure token storage (DB + encryption)
│   ├── flows/
│   │   ├── __init__.py
│   │   ├── base.py      # BaseOAuthFlow
│   │   ├── google.py    # GoogleOAuthFlow (InstalledAppFlow wrapper)
│   │   └── github.py    # GitHubCopilotFlow (Device Code)
│   └── web.py           # OAuth callback endpoints for web UI
├── providers/
│   ├── gemini_oauth.py  # GeminiOAuthProvider (uses OAuth tokens)
│   └── copilot.py       # CopilotProvider (uses OAuth tokens)
```

### Database Schema Changes

```sql
-- New table for OAuth tokens
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,           -- 'google', 'github_copilot'
    user_id TEXT DEFAULT 'default',   -- For multi-user support later
    access_token_encrypted TEXT NOT NULL,
    refresh_token_encrypted TEXT,
    token_uri TEXT,
    client_id TEXT,
    scopes TEXT,                      -- JSON array of scopes
    expires_at TEXT,                  -- ISO timestamp
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, user_id)
);

CREATE INDEX IF NOT EXISTS idx_oauth_tokens_provider ON oauth_tokens(provider);
```

### ProviderType Enum Updates

```python
class ProviderType(Enum):
    # Existing
    CLAUDE_CODE = "claude_code"
    GEMINI_SDK = "gemini_sdk"           # API key auth
    GEMINI_OPENROUTER = "gemini_openrouter"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    NONE = "none"
    
    # New OAuth providers
    GEMINI_OAUTH = "gemini_oauth"       # OAuth auth (same API, different auth)
    GITHUB_COPILOT = "github_copilot"   # Copilot API via OAuth
```

### Model Selection Enum

```python
class AuthMethod(Enum):
    API_KEY = "api_key"
    OAUTH = "oauth"
    NONE = "none"  # For local providers
```

---

## Implementation Phases

### Phase 1: OAuth Infrastructure (Est. 4-6 hours)

**Goal:** Build the foundation for OAuth token management.

#### 1.1 Database Layer
- [ ] Add `oauth_tokens` table to schema
- [ ] Add `db.save_oauth_token()`, `db.get_oauth_token()`, `db.delete_oauth_token()`
- [ ] Add encryption for tokens (reuse existing encryption from API keys)

#### 1.2 OAuth Manager
```python
# src/workflow/oauth/manager.py
class OAuthManager:
    """Manages OAuth token lifecycle"""
    
    async def get_valid_token(self, provider: str) -> str | None:
        """Get a valid access token, refreshing if needed"""
        
    async def refresh_token(self, provider: str) -> bool:
        """Refresh an expired token"""
        
    def is_authenticated(self, provider: str) -> bool:
        """Check if user has valid OAuth for provider"""
        
    def get_auth_status(self) -> dict[str, AuthStatus]:
        """Get OAuth status for all providers"""
```

#### 1.3 Storage Layer
```python
# src/workflow/oauth/storage.py
class OAuthTokenStorage:
    """Secure token storage with encryption"""
    
    def save_token(self, provider: str, token_data: dict) -> None:
    def load_token(self, provider: str) -> dict | None:
    def delete_token(self, provider: str) -> None:
```

### Phase 2: Google Gemini OAuth (Est. 6-8 hours)

**Goal:** Enable Gemini access via Google OAuth.

#### 2.1 Google OAuth Flow
```python
# src/workflow/oauth/flows/google.py
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

class GoogleOAuthFlow:
    SCOPES = [
        "https://www.googleapis.com/auth/generative-language.retriever",
        "https://www.googleapis.com/auth/cloud-platform",
    ]
    
    def __init__(self, client_config: dict):
        """
        client_config: OAuth client config from Google Cloud Console
        {
            "installed": {
                "client_id": "xxx.apps.googleusercontent.com",
                "client_secret": "xxx",
                "redirect_uris": ["http://localhost"],
                ...
            }
        }
        """
        self.client_config = client_config
    
    async def start_flow(self, port: int = 0) -> Credentials:
        """Start OAuth flow with local server callback"""
        flow = InstalledAppFlow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
        )
        # Opens browser, waits for callback
        creds = flow.run_local_server(port=port, open_browser=True)
        return creds
    
    def refresh_credentials(self, creds: Credentials) -> Credentials:
        """Refresh expired credentials"""
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        return creds
```

#### 2.2 Gemini OAuth Provider
```python
# src/workflow/providers/gemini_oauth.py
class GeminiOAuthProvider(WorkflowLLMProvider):
    """Gemini provider using OAuth instead of API key"""
    
    def __init__(self, config: ProviderConfig, oauth_manager: OAuthManager):
        self.oauth_manager = oauth_manager
        # ... rest of init
    
    async def _get_auth_header(self) -> dict[str, str]:
        """Get OAuth bearer token for requests"""
        token = await self.oauth_manager.get_valid_token("google")
        if not token:
            raise AuthenticationError("Google OAuth not configured")
        return {"Authorization": f"Bearer {token}"}
    
    async def generate(self, prompt: str, ...) -> str:
        headers = await self._get_auth_header()
        # Use Gemini API with OAuth token instead of API key
```

#### 2.3 Registry Updates
```python
# src/workflow/providers/registry.py
class ModelRegistry:
    def __init__(self):
        self._oauth_manager = OAuthManager()
    
    def create_provider(self, config: ProviderConfig) -> WorkflowLLMProvider:
        if config.provider_type == ProviderType.GEMINI_OAUTH:
            return GeminiOAuthProvider(config, self._oauth_manager)
        # ... existing logic
```

### Phase 3: Web UI Integration (Est. 4-6 hours)

**Goal:** Add OAuth setup flow to the web dashboard.

#### 3.1 OAuth API Endpoints
```python
# src/workflow/api.py (additions)

@router.get("/oauth/status")
async def get_oauth_status():
    """Get OAuth status for all providers"""
    return oauth_manager.get_auth_status()

@router.post("/oauth/google/start")
async def start_google_oauth(background_tasks: BackgroundTasks):
    """Start Google OAuth flow"""
    # Returns URL for user to open in browser
    # Or opens browser automatically in desktop mode

@router.get("/oauth/google/callback")
async def google_oauth_callback(code: str, state: str):
    """Handle OAuth callback from Google"""
    # Exchange code for tokens, store securely

@router.delete("/oauth/{provider}")
async def revoke_oauth(provider: str):
    """Revoke OAuth tokens for a provider"""
```

#### 3.2 Web UI Components
- [ ] Add "OAuth Providers" section to Settings page
- [ ] Show auth status: ✅ Connected | ❌ Not connected | ⚠️ Expired
- [ ] "Connect" button starts OAuth flow (opens popup/new tab)
- [ ] "Disconnect" button revokes tokens
- [ ] Show connected Google account email if available

#### 3.3 Template Editor Updates
- [ ] In provider dropdown, show both "Gemini (API Key)" and "Gemini (OAuth)"
- [ ] Grey out OAuth option if not connected
- [ ] Show "Connect" button inline if OAuth not configured

### Phase 4: GitHub Copilot OAuth (Optional, Est. 6-8 hours)

**Goal:** Enable Copilot access via GitHub device code flow.

#### 4.1 Device Code Flow
```python
# src/workflow/oauth/flows/github.py
class GitHubCopilotFlow:
    """GitHub device code OAuth flow for Copilot"""
    
    DEVICE_CODE_URL = "https://github.com/login/device/code"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    CLIENT_ID = "..."  # GitHub OAuth App client ID
    
    async def start_flow(self) -> DeviceCodeResponse:
        """Start device code flow, returns code for user to enter"""
        # POST to device code endpoint
        # Returns: user_code, device_code, verification_uri
    
    async def poll_for_token(self, device_code: str) -> str:
        """Poll for token after user enters code"""
        # Poll TOKEN_URL until user completes auth
```

#### 4.2 Copilot Provider
```python
# src/workflow/providers/copilot.py
class CopilotProvider(WorkflowLLMProvider):
    """GitHub Copilot provider"""
    # Implementation similar to GeminiOAuthProvider
```

---

## Configuration Requirements

### Google OAuth Setup (User Must Do Once)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select existing
3. Enable "Generative Language API"
4. Create OAuth 2.0 credentials (Desktop app type)
5. Download `client_secret.json`
6. Upload to UltraClaude settings OR paste JSON content

**Stored Config:**
```json
{
  "google_oauth_client": {
    "installed": {
      "client_id": "xxx.apps.googleusercontent.com",
      "project_id": "my-project",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "client_secret": "xxx",
      "redirect_uris": ["http://localhost"]
    }
  }
}
```

### UltraClaude OAuth Secrets (for production)

For a production deployment, UltraClaude could have its own registered OAuth app:
- Google OAuth App
- GitHub OAuth App

This simplifies user setup (no Google Cloud Console needed).

---

## Security Considerations

### Token Storage
- Access tokens: Encrypted at rest in SQLite (same encryption as API keys)
- Refresh tokens: Also encrypted, stored separately
- Encryption key: Derived from machine ID or user-provided secret

### Token Lifecycle
- Check expiry before each API call
- Refresh proactively (e.g., 5 min before expiry)
- Handle refresh failures gracefully (prompt re-auth)

### Scope Minimization
- Request only scopes needed for Gemini API calls
- Don't request broader Google account access

---

## Migration Path

### For Existing Users
1. API key auth continues working unchanged
2. OAuth is **additive**, not replacement
3. Users can configure both and choose per-template

### Provider Priority
When both OAuth and API key are configured:
1. Template explicitly specifies `gemini_oauth` → Use OAuth
2. Template explicitly specifies `gemini_sdk` → Use API key
3. Default behavior: Prefer API key (more reliable, no expiry)

---

## Testing Plan

### Unit Tests
- [ ] `test_oauth_storage.py` - Token encryption/decryption
- [ ] `test_oauth_manager.py` - Token refresh logic
- [ ] `test_google_oauth_flow.py` - Mock flow tests

### Integration Tests
- [ ] `test_gemini_oauth_provider.py` - End-to-end with real tokens
- [ ] `test_registry_oauth.py` - Provider creation with OAuth

### Manual Testing
- [ ] Full OAuth flow in browser
- [ ] Token refresh after expiry
- [ ] Graceful degradation when token invalid
- [ ] Template editor shows correct OAuth status

---

## Effort Estimates

| Phase | Description | Effort | Priority |
|-------|-------------|--------|----------|
| 1 | OAuth Infrastructure | 4-6 hours | HIGH |
| 2 | Google Gemini OAuth | 6-8 hours | HIGH |
| 3 | Web UI Integration | 4-6 hours | HIGH |
| 4 | GitHub Copilot OAuth | 6-8 hours | LOW |
| **Total** | | **20-28 hours** | |

**Recommended Implementation Order:**
1. Phase 1 → 2 → 3 (core Gemini OAuth: 14-20 hours)
2. Phase 4 later (Copilot: nice-to-have)

---

## Dependencies

### Python Packages (to add)
```
google-auth>=2.0.0
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.1.0
```

### Existing Dependencies (already have)
- `aiohttp` - HTTP client for OAuth flows
- `cryptography` - Token encryption (if not already using)

---

## Open Questions

1. **Bundled OAuth App vs User-Provided?**
   - Bundled: Simpler user experience, but requires Google OAuth app review
   - User-provided: More setup, but works immediately
   - **Recommendation:** Start with user-provided, add bundled later

2. **Multi-user support?**
   - Current design uses single `user_id='default'`
   - Schema supports multi-user for future
   - **Recommendation:** Keep single-user for v1

3. **Token refresh during long workflows?**
   - Gemini tokens expire after 1 hour
   - Workflow phases can run for hours
   - **Recommendation:** Check/refresh token before each phase execution

---

## Next Steps

1. **Review this plan** - Get feedback on architecture decisions
2. **Set up Google OAuth App** - Create test credentials in Google Cloud Console
3. **Implement Phase 1** - OAuth infrastructure
4. **Implement Phase 2** - Gemini OAuth provider
5. **Implement Phase 3** - Web UI integration
6. **Test end-to-end** - Full workflow with OAuth auth

---

*Document created: Session continuation*
*Last updated: Current session*
