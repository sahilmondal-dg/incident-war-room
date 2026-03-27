import os
from dotenv import load_dotenv

load_dotenv()

GCP_PROJECT_ID: str = os.environ["GCP_PROJECT_ID"]
GCP_LOCATION: str = os.getenv("GCP_LOCATION", "us-central1")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-004")

AUTO_RESOLVE_THRESHOLD: float = float(os.getenv("AUTO_RESOLVE_THRESHOLD", "0.75"))
CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))
SPREAD_THRESHOLD: float = float(os.getenv("SPREAD_THRESHOLD", "0.4"))
MEAN_FLOOR: float = float(os.getenv("MEAN_FLOOR", "0.5"))
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.65"))
MAX_LOOPS: int = int(os.getenv("MAX_LOOPS", "2"))
