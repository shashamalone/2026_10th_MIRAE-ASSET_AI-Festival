'''
llm 설정 파일
'''

from langchain_naver import ChatClovaX
from dotenv import load_dotenv
import os

load_dotenv()

# .env는 CLOVA_API_KEY로, langchain_naver(ChatClovaX/ClovaXEmbeddings)는
# CLOVASTUDIO_API_KEY로 키를 찾는다. 어느 이름으로 줘도 두 클래스가 같은
# 키를 쓰도록 여기서 한 번만 이어 준다(값은 로그에 남기지 않는다).
_CLOVA_KEY = os.getenv("CLOVASTUDIO_API_KEY") or os.getenv("CLOVA_API_KEY") or os.getenv("clova")
if _CLOVA_KEY:
    os.environ.setdefault("CLOVASTUDIO_API_KEY", _CLOVA_KEY)

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

        # api_key를 직접 넘기지 않는다 - 위에서 맞춰 둔 CLOVASTUDIO_API_KEY를
        # 클래스가 스스로 읽는다(None을 넘기면 pydantic 검증 에러로 죽는다).
        _embedder = ClovaXEmbeddings(model=os.getenv("CLOVA_EMBEDDING_MODEL", "bge-m3"))
    vector = _embedder.embed_query(text)
    if len(vector) != 1024:
        raise ValueError(f"HyperCLOVA embedding dimension must be 1024, got {len(vector)}")
    return [float(value) for value in vector]
