FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 3100

# Dev server (compose overrides if needed). Production build is a later phase.
CMD ["npm", "run", "dev"]
