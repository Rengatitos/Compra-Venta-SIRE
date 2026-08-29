.PHONY: back front

# Levanta la API FastAPI
back:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 9007 --reload

# Levanta el frontend
front:
	npm run dev --prefix frontend
