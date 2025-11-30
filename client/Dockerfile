FROM node:20-alpine AS base

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

FROM base AS development
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM base AS build
ARG VITE_SERVER_URL=http://mis-app-api-dev.us-east-1.elasticbeanstalk.com
ENV VITE_SERVER_URL=${VITE_SERVER_URL}
RUN npm run build

FROM node:20-alpine AS production
WORKDIR /app
COPY --from=build /app/dist ./dist
RUN npm install -g serve

ENV PORT=80
EXPOSE 80

CMD ["sh", "-c", "serve -s dist -l ${PORT}"]
