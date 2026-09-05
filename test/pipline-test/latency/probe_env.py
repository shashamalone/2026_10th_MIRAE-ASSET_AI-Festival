import os, sys, time, json
sys.path.insert(0, "src")
from dotenv import load_dotenv; load_dotenv(".env")
import importlib
for m in ["langgraph","langchain_naver","langchain_core","psycopg2","pyoxigraph","openai","requests"]:
    try:
        mod=importlib.import_module(m); print("OK ", m, getattr(mod,"__version__","?"))
    except Exception as e: print("MISSING", m, e)
from langchain_naver import ChatClovaX
print("ChatClovaX fields:", [f for f in ChatClovaX.model_fields if 'retr' in f or 'timeout' in f or 'model' in f])
# RDB API
import requests
base=os.getenv("RDB_API_BASE_URL","http://40.82.145.44:8000")
t=time.time()
try:
    r=requests.get(base+"/db/version",timeout=10); print("RDB /db/version", r.status_code, r.text[:300], f"{time.time()-t:.2f}s")
except Exception as e: print("RDB version FAIL", e)
t=time.time()
try:
    r=requests.post(base+"/db/sql",data="SELECT count(*) AS n FROM raw.bond".encode(),headers={"Content-Type":"text/plain; charset=utf-8"},timeout=30); print("RDB sql", r.status_code, r.text[:200], f"{time.time()-t:.2f}s")
except Exception as e: print("RDB sql FAIL", e)
# Graph
from infrastructure.graph_db.client import OxigraphClient
gc=OxigraphClient()
print("graph remote:",gc.remote_store_path, "local:",gc.local_store_path, gc.local_store_path.is_dir(), "endpoint:",gc.endpoint)
t=time.time()
try: print("triple_count", gc.triple_count(), f"{time.time()-t:.2f}s")
except Exception as e: print("graph FAIL", type(e).__name__, e)
# Vector
from infrastructure.vector_db.client import VectorDBClient
t=time.time()
try:
    vc=VectorDBClient(); print("vec", vc._run_read_sql("SELECT count(*) AS n FROM vec.document_chunk"), f"{time.time()-t:.2f}s")
except Exception as e: print("vec FAIL", type(e).__name__, e)
# Clova remaining probe
key=os.getenv("CLOVASTUDIO_API_KEY") or os.getenv("CLOVA_API_KEY")
r=requests.post("https://clovastudio.stream.ntruss.com/v1/openai/chat/completions",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":"HCX-007","messages":[{"role":"user","content":"1"}],"max_completion_tokens":1,"temperature":0},timeout=30)
print("clova", r.status_code, {k:v for k,v in r.headers.items() if k.lower().startswith("x-ratelimit")})
