from __future__ import annotations

import os


os.environ.setdefault("INTEGRATION_TOKEN_KEY", "integration-token-key-for-tests")
os.environ.setdefault("RINGCENTRAL_CLIENT_ID", "test-client-id")
os.environ.setdefault("RINGCENTRAL_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("RINGCENTRAL_SERVER_URL", "https://platform.ringcentral.com")
os.environ.setdefault(
    "RINGCENTRAL_REDIRECT_URI",
    "https://api.360-encompass.com/api/v1/integrations/ringcentral/callback",
)
