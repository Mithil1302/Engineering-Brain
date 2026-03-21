FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --production || npm install --production --legacy-peer-deps
COPY src ./src
COPY proto ./proto
EXPOSE 3001
CMD ["npm", "start"]
