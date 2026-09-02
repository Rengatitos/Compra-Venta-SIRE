# RAG contable local con Ollama

La clasificación de cuentas no usa un modelo generativo. Los embeddings se generan con
`nomic-embed-text` mediante LangChain/Ollama y la decisión se obtiene por coincidencia
exacta, filtro de empresa, similitud híbrida y agregación de precedentes. Ningún
comprobante ni documento de conocimiento sale del equipo.

## Índices

MongoDB mantiene colecciones independientes para reglas, plan CONTASIS, históricos,
conocimiento de empresa, normativa documental y auditoría. La recuperación combina
similitud coseno, coincidencia textual, filtros por empresa y coincidencias exactas.

Los Excel fuente están en `source/rag/`. Cada fila se indexa como un documento separado.
Las hojas `04_CAPTURA_SIRE` y `05_AUDITORIA_RAG` se excluyen del conocimiento para evitar
que predicciones no aprobadas se conviertan en precedentes.

## Reconstruir

```powershell
ollama pull gemma3:4b
ollama pull nomic-embed-text
uv run python scripts/indexar_rag_contable.py --dry-run
uv run python scripts/indexar_rag_contable.py --rehacer
```

La clasificación tiene dos etapas: primero determina naturaleza, giro, origen, pago y
aptitud tributaria; después el modelo solo puede escoger entre cuentas recuperadas del
plan CONTASIS. Un validador rechaza cuentas ausentes, contrapartidas inválidas y exige
revisión cuando la confianza es menor al umbral configurado.

## Configuración

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
RAG_TOP_K_RULES=6
RAG_TOP_K_ACCOUNTS=8
RAG_TOP_K_HISTORICAL=6
RAG_CONFIDENCE_THRESHOLD=0.80
```

Cada ejecución deja una entrada en `rag_auditoria` con hash del comprobante, modelos,
fuentes recuperadas, cuentas candidatas, salida y campos reservados para revisión manual.
