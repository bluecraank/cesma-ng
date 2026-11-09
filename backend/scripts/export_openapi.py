"""Write the OpenAPI schema to backend/openapi.json (input for the frontend type generator)."""

import json
from pathlib import Path

from app.core.config import AuthBackend, Settings
from app.main import create_app

settings = Settings(auth_backend=AuthBackend.DEV, database_url="sqlite+aiosqlite://")
schema = create_app(settings).openapi()
Path(__file__).parent.parent.joinpath("openapi.json").write_text(
    json.dumps(schema, indent=2) + "\n"
)
print("openapi.json written")
