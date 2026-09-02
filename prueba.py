import os
from google import genai

# 1. Credenciales de la Service Account
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-account.json"

# 2. Cliente conectado a Vertex AI
client = genai.Client(
    vertexai=True,
    project="project-577228a1-457d-489f-972",
    location="us-central1"
)

# 3. Generación de Embedding para RAG
print("Generando vector de embedding en Vertex AI...")
embedding_response = client.models.embed_content(
    model="text-embedding-004",
    contents="Documento de prueba para el sistema RAG",
)

# En Vertex AI se accede mediante .embeddings[0].values
vector = embedding_response.embeddings[0].values
print(f"Embedding generado con éxito. Dimensión del vector: {len(vector)}")

# 4. Inferencia con Gemini
print("\nConsultando modelo Gemini en Vertex AI...")
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Dime que día es hoy y que tiempo hace en Madrid",
)
print("Respuesta de Gemini:", response.text)