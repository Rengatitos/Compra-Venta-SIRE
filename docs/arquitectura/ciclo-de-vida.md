# Ciclo de vida de la aplicación

El gestor de contexto asíncrono de ciclo de vida en [main.py](../../app/main.py:48) ejecuta, en orden, los siguientes pasos al arrancar el servidor:

1. **Conexión a Mongo.** [connect_to_mongo](../../app/db/database.py:20) abre el cliente de Motor.

2. **Deduplicación de facturas.** [deduplicate_facturas](../../app/services/maintenance.py:1) borra facturas duplicadas (mismo usuario, periodo y número de serie, quedándose con la más reciente). Esto corre en cada arranque del servidor para evitar que datos duplicados históricos disparen un doble análisis con IA — cada análisis cuesta una llamada facturable a Gemini, así que evitar duplicados tiene un costo económico directo.

3. **Creación de índices de negocio**, definida directamente en [main.py](../../app/main.py:60): un índice sobre el RUC de los usuarios SOL; un índice único compuesto por usuario y periodo en la colección de periodos; índices sobre usuario+periodo y sobre número de serie en la colección de facturas; y un índice único parcial por usuario, periodo y número de serie que solo aplica cuando el número de serie es una cadena no vacía. La creación de este último índice está envuelta en un manejo de errores específico: si ya existen datos duplicados que impiden crear el índice único, el servicio sigue funcionando igual —solo se registra una advertencia en el log— en vez de impedir que la aplicación termine de arrancar. Ver el detalle completo de estos índices en [modelo de datos — índices](../modelo-datos/indices.md).

4. **Índices de las colecciones de embeddings**, sobre el nombre de documento (y también sobre el usuario, en el caso de la colección de embeddings por usuario).

5. **Carga en memoria de la base normativa.** [cargar_vector](../../app/services/analisis_ia.py:28) carga todo el contenido de la colección de embeddings globales (la base normativa contable) a una variable en memoria del proceso. Esto se hace una sola vez al arrancar porque la búsqueda de contexto para el análisis con IA se hace por similitud de coseno en memoria, no con un índice vectorial de Mongo — para un volumen de datos grande, esto es un límite de escalabilidad conocido del diseño actual. Ver más en [flujo de análisis con IA](../flujo/05-analisis-ia.md).

Al apagar el servidor, se cierra la conexión a Mongo con [close_mongo_connection](../../app/db/database.py:30).
