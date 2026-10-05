FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM dependencies AS source
COPY . .

FROM source AS build
RUN npm run build

FROM scratch AS assets
COPY --from=build /app/dist/ /

# Cloud Run supplies HTTPS; this stage only listens on the configured HTTP port.
FROM caddy:2.11.7-alpine@sha256:d76116d819d5162f464b0f2cd09bd28c568a86148c7bc539ce17c33eb22d8bbb AS serving
# High ports do not need the official image binary's privileged-port capability.
RUN setcap -r /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist/ /srv/
USER 10001:10001
ENV PORT=8080
EXPOSE 8080
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]

FROM source AS development
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
