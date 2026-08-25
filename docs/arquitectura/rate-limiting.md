# Rate limiting

[main.py](../../app/main.py:44) crea un limitador global basado en la dirección IP remota del cliente y lo registra como estado de la aplicación, junto con el manejador de excepción para cuando se excede el límite.

Sin embargo, cada router que necesita límites de tasa —[sol_users.py](../../app/api/routes/sol_users.py), [sire.py](../../app/api/routes/sire.py) y [analysis.py](../../app/api/routes/analysis.py)— vuelve a instanciar su propio limitador local (con la misma configuración basada en IP remota) y aplica los límites sobre sus propios endpoints usando esa instancia local, en vez de reutilizar el limitador global de la aplicación.

## Límites conocidos

- Crear usuario SOL ([create_user](../../app/api/routes/sol_users.py:101)): 5 por minuto.
- Sincronizar propuesta SIRE ([get_sire_propuesta](../../app/api/routes/sire.py:20)): 10 por minuto.
- Disparar scraping de detalle ([post_scrape_detalles](../../app/api/routes/sire.py:93)): 5 por minuto.
- Ejecutar análisis con IA ([ejecutar_analisis](../../app/api/routes/analysis.py:22)): 5 por minuto.

El resto de los endpoints no tiene límite de tasa propio.
