FROM node:22-alpine AS build
# 国内构建可覆盖：compose 默认注入 npmmirror，也可用 --build-arg NPM_REGISTRY=... 覆盖
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm config set registry ${NPM_REGISTRY} && npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
