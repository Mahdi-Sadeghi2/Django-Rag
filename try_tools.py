# isort: skip_file
from app.mcp_server.server import answer, get_page, search_docs
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))


print("=== search_docs ===")
print(search_docs("how middleware works", k=2)[:500])

print("\n=== get_page (title) ===")
print(get_page("Middleware")[:300])

print("\n=== get_page (not found) ===")
print(get_page("no-such-page"))

print("\n=== answer (good) ===")
print(answer("How do sessions work?")[:600])

print("\n=== answer (off-topic) ===")
print(answer("what is the best pizza topping?")[:300])
