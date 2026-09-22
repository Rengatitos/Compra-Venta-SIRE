# MongoDB local para captura

La captura guarda conjuntamente eventos, documentos, sesiones y auditoría. Necesita
transacciones de MongoDB, disponibles con replica set. La instalación local utiliza el
mismo volumen `sire-mongodb-data` y la misma base del backend, con una réplica de un nodo
llamada `sire-rs`. Este nodo único habilita transacciones; no aporta alta disponibilidad.

## Reiniciar una instalación ya configurada

Desde la raíz del proyecto:

```powershell
docker compose -f chatbot_whatsapp/docker-compose.mongo-local.yml up -d
docker compose -f docker-compose.yml -f chatbot_whatsapp/docker-compose.yml up --build -d
```

En el `.env` de la raíz, para servicios ejecutados en Docker Desktop:

```dotenv
MONGO_URI=mongodb://host.docker.internal:27017/?tls=false&replicaSet=sire-rs&directConnection=true
```

`directConnection=true` evita depender del descubrimiento de nodos a través de la red
de Docker en este entorno de un solo nodo. Si el backend se ejecuta directamente en
Windows, puede usar `127.0.0.1` como dirección de conexión con las mismas opciones.
La configuración de Atlas u otros servidores se conserva especificando su propia URI.

Comprobar el nodo:

```powershell
docker exec sire-mongodb mongosh --quiet --eval "printjson({setName:db.hello().setName,primary:db.hello().isWritablePrimary})"
```

Debe mostrar `sire-rs` y `primary: true`.

## Conversión de un contenedor independiente existente

El Compose usa un volumen externo y falla si no existe, para no arrancar accidentalmente
con una base vacía. Antes de convertir otra instalación:

1. Comprobar el volumen montado en `/data/db`, la versión y la configuración del servidor.
2. Detener los clientes, crear un respaldo con `mongodump --archive --gzip`, copiarlo
   fuera del contenedor y verificar su integridad. Registrar conteos por colección.
3. Detener y conservar el contenedor anterior. Nunca arrancar dos procesos MongoDB sobre
   el mismo volumen ni usar `down -v` o `docker volume rm` durante la conversión.
4. Arrancar el Compose local sobre ese mismo volumen. `MONGO_LOCAL_VOLUME` permite
   indicar un nombre de volumen distinto antes de ejecutar Compose.
5. Verificar que `host.docker.internal:27017` llega al mismo servidor tanto desde el
   contenedor MongoDB como desde la red de la API. Después, inicializar una sola vez:

```powershell
docker exec sire-mongodb mongosh --quiet --eval "printjson(rs.initiate({_id:'sire-rs',members:[{_id:0,host:'host.docker.internal:27017'}]}))"
```

6. Esperar a que sea primario, comparar conteos y probar una transacción. Actualizar
   `MONGO_URI` y recrear los clientes. No volver a ejecutar `rs.initiate` en una réplica
   ya inicializada.

En la conversión local del 22/09/2026 se guardó el respaldo en
`data/backups/mongo-before-replica-20260922/`, excluido del repositorio, y se conservó el
contenedor anterior como `sire-mongodb-before-replica-20260922`, detenido.

Para recuperar el arranque anterior, detener primero los clientes y el nuevo MongoDB,
retirar únicamente el nuevo contenedor (conservar los volúmenes), devolver al contenedor
anterior su nombre y arrancarlo. Quitar `replicaSet` de la URI antes de recrear clientes.
En modo independiente la captura volverá a rechazar operaciones que requieren transacciones.

Esta receta corresponde al Docker local sin autenticación ya existente. Servidores con
autenticación necesitan configurar también la autenticación interna de la réplica.
Referencia: [conversión oficial de MongoDB](https://www.mongodb.com/docs/manual/tutorial/convert-standalone-to-replica-set/).
