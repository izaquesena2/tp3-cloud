import logging
import re
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json

app = FastAPI()

CONFIG_FILE = "/home/ubuntu/prod.json"

def load_config(file_path):
    """Load configuration from a JSON file."""
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading configuration file: {e}")
        return {}

# Load configuration
config = load_config(CONFIG_FILE)

# Configure logging
logging.basicConfig(
    filename='/home/ubuntu/app.log',  
    level=logging.INFO,              
    format='%(asctime)s - %(message)s'
)

# Define the Proxy URL
TRUSTED_HOST_URL = f"http://{config.get('TRUSTED_HOST_DNS')}:8000/run-query"

# Define request and response schemas
class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    error: int
    stdout: str

# Validate SQL query for basic SQL injection patterns
def validate_query(query: str) -> bool:
    """Basic SQL injection validation."""
    # Disallow dangerous keywords or characters
    forbidden_patterns = [
        r"--",         # Comment injection
        r";",          # Chaining queries
        r"union",      # UNION injection
        r"select.+from information_schema",  # Information schema access
        r"drop",       # Dropping tables
        r"or 1=1",     # Boolean-based injection
    ]
    return not any(re.search(pattern, query, re.IGNORECASE) for pattern in forbidden_patterns)

# Helper function to send SQL query to Trusted Host
def send_query_to_trusted_host(query: str):
    try:
        logging.info(f"Sending request to trusted host: {TRUSTED_HOST_URL}")
        response = requests.post(TRUSTED_HOST_URL, json={"query": query}, timeout=5)
        logging.info(f"Received response from trusted host: {response}")
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logging.error(f"Error communicating with Trusted Host: {e}")
        return None

@app.post("/run-query/", response_model=QueryResponse)
async def run_query(request: QueryRequest):
    query = request.query.strip()
    logging.info(f"Received query: {query}")
    
    # Validate the query
    if not validate_query(query):
        logging.error(f"Query validation failed: {query}")
        raise HTTPException(status_code=400, detail="Query contains potentially harmful content.")
    
    # Forward validated query to Trusted Host
    response = send_query_to_trusted_host(query)
    if response and response.status_code == 200:
        return QueryResponse(error=0, stdout=response.json().get("stdout", ""))
    else:
        raise HTTPException(status_code=500, detail="Error processing query in Trusted Host")
