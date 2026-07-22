FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:24-slim
WORKDIR /app
COPY --from=build /app/build ./build
COPY --from=build /app/package.json ./
ENV PORT=3000
EXPOSE 3000
CMD ["node", "build/index.js"]
