FROM node:18-alpine as build

WORKDIR /app

# Copy only package files to set relationships
COPY package.json package-lock.json ./
RUN npm install

# Copy only the source (node_modules already installed, do not copy)
COPY src ./src
COPY public ./public
COPY index.html ./
COPY vite.config.js ./
COPY tailwind.config.js ./
COPY postcss.config.js ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
