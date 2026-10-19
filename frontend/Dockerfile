FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173

# Dev server: picks up VITE_API_BASE from the container environment.
CMD ["npm", "run", "dev"]
