# ── Surya Masterbatch — Frontend Image ───────────────────────────────────────
# Stage 1: build the React app
# Stage 2: serve with nginx (also acts as reverse proxy to the Flask API)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (cached layer)
COPY app/frontend/package*.json ./
RUN npm ci

# Copy source and build
COPY app/frontend/ ./
# VITE_API_URL="" → axios uses same-origin path → nginx proxies /api/ to backend
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ── Stage 2: Serve with nginx ─────────────────────────────────────────────────
FROM nginx:alpine

# React build output
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx config (SPA routing + API proxy to backend service)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
