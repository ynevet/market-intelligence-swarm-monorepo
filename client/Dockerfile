FROM node:20-alpine AS base

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

FROM base AS development
# Remove EXPOSE for EB. You can still use this stage locally.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM base AS build
ARG VITE_SERVER_URL=http://server:5000
ENV VITE_SERVER_URL=${VITE_SERVER_URL}
RUN npm run build

FROM node:20-alpine AS production
WORKDIR /app
COPY --from=build /app/dist ./dist
RUN npm install -g serve

ENV PORT=80
EXPOSE 80

CMD ["sh", "-c", "serve -s dist -l ${PORT}"]
