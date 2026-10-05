FROM node:24-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM dependencies AS source
COPY . .

FROM source AS build
RUN npm run build

FROM scratch AS assets
COPY --from=build /app/dist/ /

FROM source AS development
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
