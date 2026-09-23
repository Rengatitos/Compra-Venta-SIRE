# Panel web: se compila con Node y se sirve con nginx (~10 MB de RAM).
#
# nginx además reenvía /api y /health a la API por la red interna, así que el
# navegador ve un solo origen: sin CORS y sin exponer la API aparte.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Vite incrusta las variables VITE_* al compilar: van como argumentos de build.
# El Client ID de Google no es secreto (viaja en el bundle).
ARG VITE_GOOGLE_CLIENT_ID=""
# Vacío = misma origen (`/api/v1`), que es lo que resuelve nginx de abajo.
ARG VITE_API_BASE_URL=""
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
# La imagen oficial pasa las plantillas por envsubst al arrancar: así el
# destino de la API se cambia con una variable, sin reconstruir.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
# Servicio de la API dentro de Easypanel: <proyecto>_<servicio>:<puerto>.
ENV API_UPSTREAM=apaclla_api:9007
EXPOSE 80
