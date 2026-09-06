"""Comprobación manual de la conexión local con Ollama."""

from app.services.ollama_rag import chat, embed_query


def main() -> None:
    print("Generando vector de embedding con Ollama...")
    vector = embed_query("Documento de prueba para el sistema RAG")
    print(f"Embedding generado. Dimensión del vector: {len(vector)}")

    print("\nConsultando el modelo de chat en Ollama...")
    response = chat().invoke("Responde solamente: conexión correcta")
    print("Respuesta de Ollama:", response.content)


if __name__ == "__main__":
    main()
