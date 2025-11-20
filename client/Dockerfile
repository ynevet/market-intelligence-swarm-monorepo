FROM node:20-alpine AS base

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

FROM base AS development
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM base AS build
ARG VITE_SERVER_URL=http://127.0.0.1:5000
ENV VITE_SERVER_URL=${VITE_SERVER_URL}
RUN npm run build

FROM node:20-alpine AS production
WORKDIR /app
COPY --from=build /app/dist ./dist
RUN npm install -g serve
EXPOSE 4173
CMD ["serve", "-s", "dist", "-l", "4173"]

