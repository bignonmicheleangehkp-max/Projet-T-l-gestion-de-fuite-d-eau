FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
# --host 0.0.0.0 : indispensable pour que le navigateur de votre machine atteigne le serveur du conteneur
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
