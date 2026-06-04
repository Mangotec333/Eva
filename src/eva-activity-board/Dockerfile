FROM node:20-slim

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install --prefer-offline
RUN npm install @rollup/rollup-linux-x64-gnu --save-optional

# Copy source
COPY . .

# Build
RUN npm run build

# Seed DB if not exists
RUN node -e "
const fs = require('fs');
if (!fs.existsSync('/data/data.db') && fs.existsSync('data.db')) {
  fs.mkdirSync('/data', { recursive: true });
  fs.copyFileSync('data.db', '/data/data.db');
  console.log('Seeded initial data');
}
" 2>/dev/null || true

EXPOSE 3001

ENV NODE_ENV=production
ENV DATABASE_PATH=/data/data.db

CMD ["node", "dist/index.cjs"]
