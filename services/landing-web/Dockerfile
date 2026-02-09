# Landing Page Dockerfile - Static export with pnpm workspaces
# Root Directory must be set to repo root in Railway
FROM node:20-alpine AS base
RUN corepack enable pnpm

# Install dependencies
FROM base AS deps
WORKDIR /app
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY packages/ui/package.json ./packages/ui/
COPY services/landing-web/package.json ./services/landing-web/
RUN pnpm install --frozen-lockfile

# Build static site
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/ ./
COPY packages/ui/ ./packages/ui/
COPY services/landing-web/ ./services/landing-web/

ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_APP_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL

WORKDIR /app/services/landing-web
RUN pnpm build

# Serve static files with nginx
FROM nginx:alpine AS runner

# Copy static files
COPY --from=builder /app/services/landing-web/out /usr/share/nginx/html

# Remove default nginx config and add our custom config
RUN rm /etc/nginx/conf.d/default.conf
COPY services/landing-web/nginx.conf /etc/nginx/conf.d/default.conf

# Verify files were copied and test nginx config
RUN ls -la /usr/share/nginx/html && \
    nginx -t

EXPOSE 3000

# Start nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
