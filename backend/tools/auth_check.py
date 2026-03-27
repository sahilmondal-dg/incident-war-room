import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_google_vertexai import ChatVertexAI
from config import GCP_PROJECT_ID, GCP_LOCATION, GEMINI_MODEL

llm = ChatVertexAI(model=GEMINI_MODEL, project=GCP_PROJECT_ID, location=GCP_LOCATION)

response = llm.invoke("Reply with the single word: READY")

if "ready" in response.content.lower():
    print("GCP auth: OK")
    sys.exit(0)
else:
    print(f"Unexpected response: {response.content}")
    sys.exit(1)
