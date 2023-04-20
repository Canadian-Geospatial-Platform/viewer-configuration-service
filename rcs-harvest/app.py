import requests
import os 
import json
import logging 
import jsonschema

# Define your schema as a dictionary
schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "number"}
    },
    "required": ["name", "age"]
}

# Load your JSON data
data = '{"name": "Alice", "age": 30}'

# Parse the JSON data
json_data = json.loads(data)

# Validate the JSON data against the schema
jsonschema.validate(instance=json_data, schema=schema)