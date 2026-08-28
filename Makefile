.PHONY: back front

# Levanta la API FastAPI en http://127.0.0.1:9007
back:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 9007 --reload

# Levanta el panel web en http://localhost:5173
front:
	npm run dev --prefix frontend
