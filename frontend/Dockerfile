# Stage 1: Build the application
FROM node:20.20.2-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install locked dependencies (including devDependencies)
RUN npm ci --no-audit --no-fund

# Copy source code
COPY . .

# Build the application
RUN npm run build

# hadolint ignore=DL3007,DL3029
FROM caddy:2.10.2-alpine

# Copy built static files
COPY --from=builder /app/dist /usr/share/caddy

# Copy Caddy configuration
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 3000

# Caddy runs automatically, no need for CMD
