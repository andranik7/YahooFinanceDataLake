#!/bin/bash
# Wait for Kibana to be ready and import saved objects

KIBANA_URL="http://kibana:5601"
EXPORT_FILE="/opt/airflow/kibana/kibana_saved_objects.ndjson"

echo "Waiting for Kibana to be ready..."

# Wait for Kibana (max 120 seconds)
for i in {1..60}; do
    if curl -s "${KIBANA_URL}/api/status" | grep -q '"level":"available"'; then
        echo "Kibana is ready!"
        break
    fi
    echo "Waiting for Kibana... ($i/60)"
    sleep 2
done

# Import saved objects if file exists
if [ -f "$EXPORT_FILE" ]; then
    echo "Importing Kibana saved objects..."
    curl -s -X POST "${KIBANA_URL}/api/saved_objects/_import?overwrite=true" \
        -H "kbn-xsrf: true" \
        -F file=@"$EXPORT_FILE"
    echo ""
    echo "Kibana import complete!"
else
    echo "No Kibana export file found at $EXPORT_FILE"
fi
