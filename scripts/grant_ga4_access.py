"""
One-time script: Grant the service account Viewer access to the GA4 property
via the Admin API, authenticated as YOU (opens a browser for OAuth).

Run once:
  pip install google-analytics-admin google-auth-oauthlib
  python scripts/grant_ga4_access.py

You'll need a Desktop OAuth client ID from Google Cloud Console:
  APIs & Services → Credentials → + Create Credentials → OAuth client ID → Desktop app
  Download the JSON → save as secrets/oauth_client.json
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.analytics.admin import AnalyticsAdminServiceClient
from google.analytics.admin_v1alpha.types import AccessBinding

PROPERTY_ID      = "540216240"
SERVICE_ACCOUNT  = "elocoach-ga-exporter@email-bot-gmail.iam.gserviceaccount.com"
OAUTH_CLIENT_FILE = "secrets/oauth_client.json"

SCOPES = ["https://www.googleapis.com/auth/analytics.manage.users"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, scopes=SCOPES)
    creds = flow.run_local_server(port=0)

    client = AnalyticsAdminServiceClient(credentials=creds)

    binding = client.create_access_binding(
        parent=f"properties/{PROPERTY_ID}",
        access_binding=AccessBinding(
            user=SERVICE_ACCOUNT,
            roles=["predefinedRoles/viewer"],
        ),
    )
    print(f"Done — access binding created: {binding.name}")

if __name__ == "__main__":
    main()
