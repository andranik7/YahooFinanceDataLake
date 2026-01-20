"""
Export/Import Kibana saved objects (dashboards, visualizations, data views).
"""

import requests
import json
import sys
from pathlib import Path
from datetime import datetime

KIBANA_URL = "http://localhost:5601"
EXPORT_PATH = Path(__file__).parent.parent / "kibana"


def export_saved_objects():
    """Export all dashboards and visualizations from Kibana."""
    EXPORT_PATH.mkdir(parents=True, exist_ok=True)

    # Export all relevant types
    payload = {
        "type": ["dashboard", "visualization", "lens", "index-pattern", "search"],
        "includeReferencesDeep": True
    }

    response = requests.post(
        f"{KIBANA_URL}/api/saved_objects/_export",
        headers={"kbn-xsrf": "true", "Content-Type": "application/json"},
        json=payload
    )

    if response.status_code == 200:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = EXPORT_PATH / f"kibana_export_{timestamp}.ndjson"

        with open(export_file, "wb") as f:
            f.write(response.content)

        print(f"Exported to: {export_file}")

        # Also save as latest
        latest_file = EXPORT_PATH / "kibana_saved_objects.ndjson"
        with open(latest_file, "wb") as f:
            f.write(response.content)
        print(f"Also saved as: {latest_file}")
    else:
        print(f"Export failed: {response.status_code}")
        print(response.text)


def import_saved_objects():
    """Import saved objects to Kibana."""
    import_file = EXPORT_PATH / "kibana_saved_objects.ndjson"

    if not import_file.exists():
        print(f"No export file found at: {import_file}")
        return

    with open(import_file, "rb") as f:
        response = requests.post(
            f"{KIBANA_URL}/api/saved_objects/_import?overwrite=true",
            headers={"kbn-xsrf": "true"},
            files={"file": f}
        )

    if response.status_code == 200:
        result = response.json()
        print(f"Imported {result.get('successCount', 0)} objects")
        if result.get('errors'):
            print(f"Errors: {result['errors']}")
    else:
        print(f"Import failed: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python kibana_export.py [export|import]")
        sys.exit(1)

    action = sys.argv[1]

    if action == "export":
        export_saved_objects()
    elif action == "import":
        import_saved_objects()
    else:
        print(f"Unknown action: {action}")
        print("Usage: python kibana_export.py [export|import]")
