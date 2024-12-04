import logging
import re
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json

# Configure logging
logging.basicConfig(
    filename='./app.log',  
    level=logging.INFO,              
    format='%(asctime)s - %(message)s'
)

# Define request and response schemas
class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    error: int
    stdout: str

# Helper function to send SQL query to Trusted Host
def send_query_to_gatekeeper(url, query: str):
    try:
        logging.info(f"Sending request to: {url}")
        response = requests.post(url, json={"query": query}, timeout=5)
        logging.info(f"Received response: {response}")
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logging.error(f"Error communicating with Trusted Host: {e}")
        return None

async def run_query(request: QueryRequest):
    query = request.query.strip()
    logging.info(f"Received query: {query}")
        
    # Forward validated query to Trusted Host
    response = send_query_to_trusted_host(query)
    if response and response.status_code == 200:
        return QueryResponse(error=0, stdout=response.json().get("stdout", ""))
    else:
        raise HTTPException(status_code=500, detail="Error processing query in Trusted Host")


def benchmarking(gatekeepr_and_trusted_host_result):
    print("-------BENCHMARKING-------")
    url = f"http://{gatekeepr_and_trusted_host_result["gatekeeper"]["dns"]}:8000/run-query"
    delete_all_query = "DELETE FROM actor WHERE first_name = 'John' AND last_name = 'Doe'"
    send_query_to_gatekeeper(url, delete_all_query)
    count_actors_query = "SELECT COUNT(*) AS actor_count FROM actor WHERE first_name = 'John' AND last_name = 'Doe'"
    response = send_query_to_gatekeeper(url, count_actors_query)
    print(f"number of actors whose first_name is John and last_name is Doe: ${response.json().get("stdout", "")}")
    print("SENDING 2000 REQUESTS")
    for _ in range(1000):
        write_query =  "INSERT INTO actor (first_name, last_name) VALUES ('John', 'Doe')"
        read_query = "SELECT COUNT(*) AS actor_count FROM actor WHERE first_name = 'John' AND last_name = 'Doe'"
        send_query_to_gatekeeper(url, write_query)
        response = send_query_to_gatekeeper(url, read_query)
        number = response.json().get("stdout", "").split()[1]
        print(number, end=" ", flush=True)
    print()