'''
llm 설정 파일
'''

from langchain_naver import ChatClovaX
from dotenv import load_dotenv

load_dotenv()

# _llm_plan = ChatClovaX(model="HCX-005", temperature=0, timeout=8)
# _llm_answer = ChatClovaX(model="HCX-005", temperature=0, timeout=8)

_llm_plan = ChatClovaX(model="HCX-007", temperature=0, timeout=25, thinking={"effort": "none"}, max_tokens=2048)
_llm_answer = ChatClovaX(model="HCX-007", temperature=0, timeout=30, thinking={"effort": "none"}, max_tokens=2048)