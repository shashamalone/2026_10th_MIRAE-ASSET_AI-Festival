'''
llm 설정 파일
'''

from langchain_naver import ChatClovaX
from dotenv import load_dotenv
import os

load_dotenv()

# _llm_plan = ChatClovaX(model="HCX-005", temperature=0, timeout=8)
# _llm_answer = ChatClovaX(model="HCX-005", temperature=0, timeout=8)

_llm_plan = ChatClovaX(model="HCX-007", temperature=0, timeout=25, thinking={"effort": "none"}, max_tokens=2048)
_llm_answer = ChatClovaX(model="HCX-007", temperature=0, timeout=30, thinking={"effort": "none"}, max_tokens=2048)


_embedder = None


def embed(text: str) -> list[float]:
    """Create the canonical 1024-dimensional HyperCLOVA embedding lazily."""
    global _embedder
    if _embedder is None:
        from langchain_naver import ClovaXEmbeddings

        _embedder = ClovaXEmbeddings(
            model=os.getenv("CLOVA_EMBEDDING_MODEL", "bge-m3"),
            api_key=os.getenv("CLOVA_API_KEY") or os.getenv("clova"),
        )
    vector = _embedder.embed_query(text)
    if len(vector) != 1024:
        raise ValueError(f"HyperCLOVA embedding dimension must be 1024, got {len(vector)}")
    return [float(value) for value in vector]
