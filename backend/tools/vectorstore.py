import os
import sys
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_google_vertexai import VertexAIEmbeddings

from config import EMBEDDING_MODEL, GCP_LOCATION, GCP_PROJECT_ID, SIMILARITY_THRESHOLD

_vectorstore: Chroma | None = None

_RUNBOOKS_DIR = Path(__file__).parent.parent / "fixtures" / "runbooks"
_PERSIST_DIR = str(Path(__file__).parent.parent / ".chroma")


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse simple YAML frontmatter between --- markers without external deps."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1].strip()
    body = parts[2].strip()
    metadata: dict = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            metadata[key] = [item.strip() for item in inner.split(",") if item.strip()]
        else:
            metadata[key] = value
    return metadata, body


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        embeddings = VertexAIEmbeddings(
            model_name=EMBEDDING_MODEL,
            project=GCP_PROJECT_ID,
            location=GCP_LOCATION,
        )
        _vectorstore = Chroma(
            collection_name="runbooks",
            embedding_function=embeddings,
            persist_directory=_PERSIST_DIR,
        )
    return _vectorstore


def seed_vectorstore() -> int:
    vs = get_vectorstore()
    # Skip seeding if documents already exist to avoid duplicates on restart
    if vs._collection.count() > 0:
        existing = vs._collection.count()
        print(f"[vectorstore] Already has {existing} documents — skipping seed.")
        return 0
    docs: list[Document] = []
    for md_file in sorted(_RUNBOOKS_DIR.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        metadata, body = _parse_frontmatter(content)
        metadata["source"] = md_file.name
        if "title" not in metadata:
            metadata["title"] = md_file.stem
        # Flatten list values so Chroma metadata stays string-compatible
        for k, v in metadata.items():
            if isinstance(v, list):
                metadata[k] = ", ".join(v)
        docs.append(Document(page_content=body, metadata=metadata))
    if docs:
        vs.add_documents(docs)
    return len(docs)


# Alias used by main.py startup: `from tools.vectorstore import seed`
seed = seed_vectorstore


def calibrate() -> None:
    vs = get_vectorstore()
    queries = [
        "db_timeout connection pool timeout HikariPool",
        "OutOfMemoryError GC overhead limit exceeded JVM heap",
        "DNS resolution failed upstream connect error",
    ]
    print(f"\nCalibration  (SIMILARITY_THRESHOLD={SIMILARITY_THRESHOLD})")
    print("-" * 64)
    for query in queries:
        results = vs.similarity_search_with_score(query, k=1)
        if results:
            doc, score = results[0]
            title = doc.metadata.get("title", doc.metadata.get("source", "unknown"))
            verdict = "PASS" if score < SIMILARITY_THRESHOLD else "FAIL"
            print(f"Query : {query[:60]}")
            print(f"Match : {title}")
            print(f"Score : {score:.4f}  [{verdict}]")
        else:
            print(f"Query : {query[:60]}")
            print(f"Match : (no results)")
            print(f"Score : N/A  [FAIL]")
        print()


if __name__ == "__main__":
    if "--seed" in sys.argv:
        n = seed_vectorstore()
        print(f"Seeded {n} documents")
    elif "--calibrate" in sys.argv:
        calibrate()
    else:
        print("Usage: python tools/vectorstore.py [--seed | --calibrate]")
