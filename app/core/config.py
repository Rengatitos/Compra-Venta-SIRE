import json
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# El default cubre el frontend en desarrollo (Vite en 5173).
CORS_ORIGINS_POR_DEFECTO = ["http://localhost:5173", "http://localhost:3000"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Automatización SUNAT API"
    API_V1_PREFIX: str = "/api/v1"

    JWT_SECRET_KEY: str
    SOL_USER_CRYPTO_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 2

    # Cliente OAuth de Google (tipo "aplicación web") contra el que se valida el
    # `aud` de los ID tokens. Sin él no se puede entrar: ver el guard explícito
    # en `app.services.google_oauth`, donde se explica por qué dejarlo vacío no
    # puede degradarse a "no valides la audiencia".
    GOOGLE_CLIENT_ID: str | None = None

    MONGO_URI: str | None = None
    MONGO_FACTURASDB_NAME: str | None = None

    SUNAT_CLIENT_ID: str | None = None
    SUNAT_CLIENT_SECRET: str | None = None
    # Un endpoint por libro. `URL_SIRE_PROPUESTA` conserva su nombre —sin
    # sufijo— para no romper los despliegues que ya la tienen puesta.
    URL_SIRE_PROPUESTA: str | None = None
    URL_SIRE_PROPUESTA_VENTAS: str | None = None

    # Paginación de la propuesta. Antes `page=1&perPage=100` iba incrustado y
    # cualquier periodo con más de cien comprobantes se truncaba en silencio;
    # en ventas, con las boletas, eso pasa casi siempre. `SIRE_MAX_PAGINAS` es
    # el freno por si el endpoint ignora `page` y devuelve siempre lo mismo.
    # 100 es además el techo que acepta el SIRE: por encima responde 422.
    SIRE_PER_PAGE: int = 100
    SIRE_MAX_PAGINAS: int = 50

    # Scraping del portal SOL. Hasta ahora todos estos valores estaban
    # incrustados en el código, así que ajustar el scraper obligaba a tocarlo.
    SUNAT_SCRAPER_HEADLESS: bool = True
    # Techo de espera de cada paso de Playwright. Subirlo sólo si SUNAT va
    # lento: multiplica el coste de cada comprobante que falla.
    SUNAT_SCRAPER_TIMEOUT_MS: int = 15000
    # Techo para esperar la respuesta de la búsqueda. Ya no significa "cuánto
    # esperar antes de darlo por inexistente": los que el portal no tiene se
    # descartan al instante por su propio aviso (`SUNAT_TEXTOS_SIN_RESULTADOS`),
    # así que este plazo sólo lo agotan los emisores lentos. Con los 8000 de
    # antes, los bancos —BBVA y BCP tardan sobre 9 s— se contaban como ausentes
    # y se quedaban sin detalle ni PDF.
    SUNAT_TIMEOUT_BUSQUEDA_MS: int = 25000
    # Avisos con los que el portal dice que no hay resultados. Se comparan como
    # subcadena y sin distinguir mayúsculas contra el texto del iframe.
    #
    # Conviene quedarse corto: un aviso que no casa sólo cuesta esperar el techo
    # de arriba, mientras que uno demasiado amplio da por ausente un comprobante
    # que sí está, que es exactamente el fallo que esto viene a corregir. Por eso
    # tampoco se documenta en `.env.example`: al ser un tipo compuesto,
    # pydantic-settings lo lee como JSON y un valor a mano tumbaría el arranque.
    SUNAT_TEXTOS_SIN_RESULTADOS: tuple[str, ...] = (
        "no se encontraron",
        "no existen datos",
        "no hay información",
    )
    # Comprobantes que se piden como máximo en una extracción. Antes era un
    # `limit=100` escondido en el repositorio que recortaba el trabajo sin
    # decir nada.
    SUNAT_MAX_COMPROBANTES: int = 100

    # Raíz de los PDFs descargados del portal SOL. Relativa al root del repo si
    # no es absoluta, igual que el directorio de logs.
    #
    # OJO EN DOCKER: la imagen no declara ningún `VOLUME`, así que sin montar un
    # volumen en `{WORKDIR}/data` los PDFs se pierden al reiniciar el
    # contenedor. `/app` sí es escribible (el Dockerfile hace `chown` a
    # `appuser`), así que el código funciona igual; lo que no sobrevive es el
    # archivo.
    SUNAT_DATA_DIR: str = "data"
    # Techo de PDFs por trabajo, en la línea de `SUNAT_MAX_COMPROBANTES`: cada
    # uno cuesta una búsqueda en el portal, así que un periodo grande se cubre
    # en varias vueltas en vez de en un trabajo de horas.
    SUNAT_MAX_PDFS: int = 100
    # Techo aparte para la captura del PDF: renderizar o descargar el documento
    # tarda más que leer la tabla de ítems que ya está en el DOM.
    SUNAT_PDF_TIMEOUT_MS: int = 20000

    # Clasificador contable (RAG + Gemini en `app/services/clasificador`). Va
    # apagado por defecto: al encenderlo la API carga torch y el modelo de
    # embeddings (~1 GB de RAM) y necesita la credencial de Vertex AI. Sus
    # parámetros finos (modelo, pesos del RAG, rutas) se leen del mismo `.env`
    # desde `app/services/clasificador/config.py`.
    CLASIFICADOR_HABILITADO: bool = False
    # Techo de comprobantes por trabajo de clasificación, en la línea de
    # `SUNAT_MAX_COMPROBANTES`: cada uno cuesta tres llamadas a Gemini.
    CLASIFICADOR_MAX_COMPROBANTES: int = 200
    # Antes de clasificar, consultar en la Consulta RUC de SUNAT las
    # actividades (CIIU) de las contrapartes que aún no están en caché. Cada
    # consulta nueva cuesta unos segundos de navegador.
    CLASIFICADOR_CONSULTAR_CONTRAPARTES: bool = True
    # Días que una ficha RUC guardada se da por vigente. Las actividades de un
    # contribuyente cambian rara vez; pasado este plazo se vuelve a consultar.
    FICHA_RUC_VIGENCIA_DIAS: int = 90
    # Parecido mínimo (Jaccard sobre las palabras de la glosa) para reutilizar
    # una clasificación frecuente en vez de consultar a la IA. 1.0 = mismas
    # palabras; con 0.8 «SACOS DE PAPA DE PRIMERA» y «SACOS DE PAPA PRIMERA»
    # coinciden y «SACOS DE PAPA» con «SACOS DE ARROZ» no.
    CLASIFICADOR_SIMILITUD_MINIMA: float = 0.8
    # Cuántos comprobantes con la misma glosa se mandan a la IA en un trabajo
    # mientras no dé cuenta. Pasado el tope, el resto queda en revisión sin
    # gastar más consultas; recibe la cuenta en cuanto otro igual acierte.
    CLASIFICADOR_INTENTOS_POR_GLOSA: int = 3

    # Clave con la que sire-bot (Apaclla Bot) se autentica en la cabecera
    # `X-Api-Key`. Sin ella los endpoints del bot responden 503: la integración
    # falla cerrada en vez de quedar abierta a cualquiera. Debe ser la misma
    # cadena que el bot tiene en su `SIRE_API_KEY`.
    SIRE_BOT_API_KEY: str | None = None
    # Dónde se guardan las fotos que manda el bot, una carpeta por empresa.
    # Vive dentro de `data/`, que docker-compose ya monta como volumen.
    COMPROBANTES_EXTERNOS_DIR: str = "data/comprobantes-externos"

    # Orígenes permitidos por CORS. Se acepta tanto la lista separada por comas
    # que documenta `.env.example` como una lista JSON.
    #
    # `NoDecode` es imprescindible: sin él, pydantic-settings trata cualquier
    # campo complejo del entorno como JSON y falla en `prepare_field_value`
    # antes de que `_parsear_origenes` llegue a ejecutarse, así que el formato
    # con comas reventaba el arranque con JSONDecodeError.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = CORS_ORIGINS_POR_DEFECTO

    # Administradores fijos del panel: entran siempre como admin y no se pueden
    # quitar desde la web. El resto de correos los agregan ellos desde el panel
    # (colección `usuarios`, ver `app.domain.usuario`). Mismo formato que CORS_ORIGINS
    # —lista separada por comas o JSON— y por el mismo motivo lleva `NoDecode`:
    # sin él, pydantic-settings intenta leer el valor como JSON en
    # `prepare_field_value` y un correo suelto tumba el arranque con
    # JSONDecodeError antes de que el validador llegue a ejecutarse.
    #
    # La diferencia con CORS_ORIGINS está en el valor vacío, y es deliberada:
    # allí significa "no lo configuré" y cae al default, porque una lista vacía
    # dejaría al frontend bloqueado sin ninguna pista. Aquí significa "no entra
    # nadie". Un default permisivo abriría el panel a cualquier cuenta de
    # Google, así que este campo falla cerrado.
    GOOGLE_ALLOWED_EMAILS: Annotated[list[str], NoDecode] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parsear_origenes(cls, v):
        if not isinstance(v, str):
            return v

        texto = v.strip()
        # Un valor vacío significa "no lo configuré", no "no permitas nada":
        # dejar la lista vacía bloquearía al frontend sin ninguna pista del por qué.
        if not texto:
            return list(CORS_ORIGINS_POR_DEFECTO)

        # Con NoDecode ya nadie decodifica el JSON, así que hay que hacerlo aquí
        # para no romper los despliegues que ya usaban esa forma.
        if texto.startswith("["):
            try:
                decodificado = json.loads(texto)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "CORS_ORIGINS parece una lista JSON pero no se pudo decodificar. "
                    "Usa una lista separada por comas o un JSON válido."
                ) from exc
            if not isinstance(decodificado, list):
                raise ValueError("CORS_ORIGINS en JSON debe ser una lista de cadenas")
            return [str(origen).strip() for origen in decodificado if str(origen).strip()]

        return [origen.strip() for origen in texto.split(",") if origen.strip()]

    @field_validator("GOOGLE_ALLOWED_EMAILS", mode="before")
    @classmethod
    def _parsear_correos(cls, v):
        # Google entrega el correo en minúsculas, pero el .env lo escribe una
        # persona: se normaliza en las tres formas de llegada (lista ya
        # construida, JSON y la cadena con comas) para que la comparación de
        # `app.domain.usuario` no dependa de cómo se tecleó.
        if isinstance(v, list):
            return [str(correo).strip().lower() for correo in v if str(correo).strip()]

        if not isinstance(v, str):
            return v

        texto = v.strip()
        if not texto:
            return []

        if texto.startswith("["):
            try:
                decodificado = json.loads(texto)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "GOOGLE_ALLOWED_EMAILS parece una lista JSON pero no se pudo decodificar. "
                    "Usa una lista separada por comas o un JSON válido."
                ) from exc
            if not isinstance(decodificado, list):
                raise ValueError("GOOGLE_ALLOWED_EMAILS en JSON debe ser una lista de cadenas")
            return [str(correo).strip().lower() for correo in decodificado if str(correo).strip()]

        return [correo.strip().lower() for correo in texto.split(",") if correo.strip()]


settings = Settings()
