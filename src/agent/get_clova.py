'''
llm 설정 파일
'''

from langchain_naver import ChatClovaX
from dotenv import load_dotenv
import os

load_dotenv()

_CLOVA_KEY = os.getenv("CLOVASTUDIO_API_KEY") or os.getenv("CLOVA_API_KEY") or os.getenv("clova")
if _CLOVA_KEY:
    os.environ.setdefault("CLOVASTUDIO_API_KEY", _CLOVA_KEY)

_llm_plan = ChatClovaX(model="HCX-007", temperature=0, timeout=25, thinking={"effort": "none"}, max_tokens=2048)
_llm_answer = ChatClovaX(model="HCX-007", temperature=0, timeout=90, thinking={"effort": "none"}, max_tokens=2048)


_embedder = None


def embed(text: str) -> list[float]:
    global _embedder
    if _embedder is None:
        from langchain_naver import ClovaXEmbeddings

        _embedder = ClovaXEmbeddings(model=os.getenv("CLOVA_EMBEDDING_MODEL", "bge-m3"))
    vector = _embedder.embed_query(text)
    if len(vector) != 1024:
        raise ValueError(f"HyperCLOVA embedding dimension must be 1024, got {len(vector)}")
    return [float(value) for value in vector]
