# Docker Configuration Files

Copy these files to your project to run the dashboard with Docker.

## File Structure

\`\`\`
project-root/
├── docker-compose.yml          # Production config
├── docker-compose.dev.yml      # Development config (optional)
└── apps/
    └── web/
        ├── Dockerfile          # Production build
        ├── Dockerfile.dev      # Development build (optional)
        └── .dockerignore       # Files to exclude
\`\`\`

---

## 📄 docker-compose.yml

**Location:** Project root

\`\`\`yaml
version: '3.8'

services:
  ovn-dashboard:
    build:
      context: ./apps/web
      dockerfile: Dockerfile
    container_name: ovn_dashboard_web
    ports:
      - "3039:3039"
    environment:
      - NODE_ENV=production
      - PORT=3039
      - NEXT_PUBLIC_API_URL=http://localhost:8001
    restart: unless-stopped
    networks:
      - ovn_network
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3039"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  ovn_network:
    driver: bridge
    name: ovn_monitoring_network
\`\`\`

---

## 📄 apps/web/Dockerfile

**Location:** apps/web/Dockerfile

\`\`\`dockerfile
# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM node:18-alpine AS runner

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install production dependencies only
RUN npm ci --only=production

# Copy built assets from builder
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/public ./public

# Install serve to run the built app
RUN npm install -g serve

# Expose port 3039
EXPOSE 3039

# Set environment variables
ENV NODE_ENV=production
ENV PORT=3039

# Start the application
CMD ["serve", "-s", "dist", "-l", "3039"]
\`\`\`

---

## 📄 apps/web/.dockerignore

**Location:** apps/web/.dockerignore

\`\`\`
node_modules
npm-debug.log
.next
.git
.gitignore
README.md
.env.local
.env.development.local
.env.test.local
.env.production.local
.DS_Store
dist
build
coverage
.vscode
.idea
*.swp
*.swo
\`\`\`

---

## 🚀 Quick Start Commands

### Production Mode

\`\`\`bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild
docker-compose up -d --build
\`\`\`

### Access the Dashboard

\`\`\`
http://localhost:3039
\`\`\`

---

## 🔧 Optional: Development Mode with Hot Reload

### docker-compose.dev.yml

**Location:** Project root

\`\`\`yaml
version: '3.8'

services:
  ovn-dashboard-dev:
    build:
      context: ./apps/web
      dockerfile: Dockerfile.dev
    container_name: ovn_dashboard_web_dev
    ports:
      - "3039:3039"
    environment:
      - NODE_ENV=development
      - PORT=3039
      - NEXT_PUBLIC_API_URL=http://localhost:8001
    volumes:
      - ./apps/web/src:/app/src
      - ./apps/web/public:/app/public
      - /app/node_modules
    restart: unless-stopped
    networks:
      - ovn_network
    command: npm run dev -- --host 0.0.0.0 --port 3039

networks:
  ovn_network:
    driver: bridge
\`\`\`

### apps/web/Dockerfile.dev

**Location:** apps/web/Dockerfile.dev

\`\`\`dockerfile
FROM node:18-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

# Expose port
EXPOSE 3039

# Start dev server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3039"]
\`\`\`

### Run Development Mode

\`\`\`bash
docker-compose -f docker-compose.dev.yml up
\`\`\`

---

## 🌐 Environment Variables

You can customize the API endpoint by editing the \`environment\` section in docker-compose.yml:

\`\`\`yaml
environment:
  - NEXT_PUBLIC_API_URL=http://your-ovn-api:8001
\`\`\`

---

## 🐛 Troubleshooting

### Container won't start
\`\`\`bash
# Check logs
docker-compose logs ovn-dashboard

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up
\`\`\`

### Port already in use
Change the port in docker-compose.yml:
\`\`\`yaml
ports:
  - "YOUR_PORT:3039"  # Change YOUR_PORT
\`\`\`

### Cannot connect to API
- Verify your OVN API is running
- Check the API URL in environment variables
- Ensure network connectivity between containers
