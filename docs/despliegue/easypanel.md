# Despliegue en Easypanel (VM de 4 GB)

Guía para levantar Sire en el proyecto **apaclla** de Easypanel, en una VM de Compute Engine con 2 vCPU y ~4 GB de RAM.

## Cuánta memoria usa cada pieza

| Servicio | RAM | Nota |
|---|---|---|
| `api` con el clasificador cargado | ~1,2 GB | torch + modelo de embeddings (int8) + índice de 5 910 fragmentos |
| Chromium de Playwright | +0,4–0,6 GB | solo mientras corre una extracción SOL o una consulta RUC |
| `mongobd` | 0,2–0,5 GB | sin límite, su caché crece hasta la mitad de la RAM: hay que limitarlo |
| `web` (nginx) | ~10 MB | |
| Easypanel + Traefik | ~0,3–0,4 GB | |

Cabe, pero sin margen para picos: por eso el swap y los límites por servicio de abajo.

## 1. Preparar la VM (una vez, por SSH)

Swap de 4 GB y que el kernel lo use solo como colchón:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system
free -h   # debe mostrar Swap: 4.0Gi
```

En GCP, la regla de firewall de la VM debe permitir **80 y 443** (Easypanel usa el 3000 para su panel).

## 2. Dominio con HTTPS

El login con Google **no funciona sobre `http://IP`**: Google solo acepta orígenes `https://` (salvo `localhost`). Opciones:

- El dominio gratuito que ofrece Easypanel (`*.easypanel.host`), con HTTPS automático.
- Un dominio propio apuntando (registro A) a la IP de la VM.

Ese origen (`https://tu-dominio`) se agrega en Google Cloud → Google Auth Platform → Clientes → «Cliente web 1» → **Orígenes autorizados de JavaScript**.

## 3. Mongo (`mongobd`, ya existe)

- **Recursos → límite de memoria: 1 GB.** MongoDB lee el límite del contenedor y dimensiona su caché con él.
- Anota la **URL de conexión interna** que muestra Easypanel (`mongodb://usuario:clave@apaclla_mongobd:27017/...`).

### Pasar los datos locales

En tu PC (con el Mongo local levantado):

```powershell
docker exec sire-mongodb mongodump --db Mod_Facturas --archive --gzip > sire.archive.gz
scp sire.archive.gz usuario@34.176.14.150:~/
```

En la VM:

```bash
docker ps --filter name=apaclla_mongobd --format '{{.Names}}'   # nombre del contenedor
docker exec -i <contenedor> mongorestore --username <usuario> --password <clave> \
  --authenticationDatabase admin --archive --gzip < ~/sire.archive.gz
```

## 4. Servicio `api` (App)

- **Origen:** GitHub, repositorio `Rengatitos/Compra-Venta-SIRE`, rama `main`, **Dockerfile** en la raíz (`/Dockerfile`).
- **Puerto:** 9007. Sin dominio propio: el público entra por `web`.
- **Montajes:**
  - Volumen `datos` → `/app/data` (PDFs, índice del clasificador, modelo de embeddings).
  - Archivo → `/app/service-account.json`, con el contenido del JSON de la cuenta de servicio de Google.
- **Recursos:** límite de memoria **2,5 GB**.
- **Variables de entorno:** las del `.env` local, cambiando estas:

```env
MONGO_URI=mongodb://usuario:clave@apaclla_mongobd:27017/?authSource=admin
MONGO_FACTURASDB_NAME=Mod_Facturas
CORS_ORIGINS=https://tu-dominio
GOOGLE_APPLICATION_CREDENTIALS=/app/service-account.json
SUNAT_DATA_DIR=/app/data
SUNAT_SCRAPER_HEADLESS=true
CLASIFICADOR_HABILITADO=true
# 2 vCPU: que torch no abra más hilos que núcleos.
CPU_THREADS=2
OMP_NUM_THREADS=2
EMBEDDING_BATCH_SIZE=8
```

`JWT_SECRET_KEY` y `SOL_USER_CRYPTO_KEY` deben ser **los mismos del entorno de donde vienen los datos**: con otra `SOL_USER_CRYPTO_KEY` las contraseñas SOL guardadas no se pueden descifrar.

### El índice del clasificador

Al primer arranque la API descarga el modelo de embeddings (~470 MB) y calcula el índice del conocimiento: en 2 vCPU tarda unos 10 minutos y queda en el volumen `datos`, así que ocurre una sola vez. Para saltárselo, se puede copiar el índice ya calculado de un equipo de desarrollo:

```powershell
tar -czf clasificador.tgz -C data clasificador
scp clasificador.tgz usuario@34.176.14.150:~/
```

```bash
# Ruta del volumen en la VM:
docker volume inspect $(docker volume ls -q | grep datos) --format '{{.Mountpoint}}'
sudo tar -xzf ~/clasificador.tgz -C <ruta-del-volumen>
sudo chown -R 1000:1000 <ruta-del-volumen>/clasificador
```

## 5. Servicio `web` (App)

- **Origen:** el mismo repositorio, **Dockerfile** en `frontend/Dockerfile`, con `frontend` como contexto de build.
- **Argumento de build:** `VITE_GOOGLE_CLIENT_ID=<el ID de cliente de Google>`.
- **Variable de entorno:** `API_UPSTREAM=apaclla_api:9007` (es el valor por defecto; cámbialo solo si el servicio de la API se llama distinto).
- **Dominio:** el del paso 2, apuntando al **puerto 80** del servicio.
- **Recursos:** límite de memoria **128 MB**.

nginx sirve el panel y reenvía `/api` a la API por la red interna: el navegador ve un único origen, sin CORS.

## 6. Comprobar

```bash
free -h                              # memoria y swap
docker stats --no-stream             # consumo por contenedor
```

- `https://tu-dominio/health` → `{"status":"ok"}`.
- En los logs de `api`: `Clasificador contable listo`.
- Entrar con Google y abrir una empresa.

## Si falta memoria

Por orden, lo que más ahorra:

1. `CLASIFICADOR_HABILITADO=false` mientras no se clasifique: la API no carga torch ni el modelo y baja de ~1,2 GB a ~100 MB (medido).
2. No lanzar a la vez una extracción SOL y una clasificación.
3. `GEMINI_MODEL=gemini-3.8-flash`: no ahorra RAM, pero cada comprobante tarda menos, así que el pico dura menos.
