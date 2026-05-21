# Landing Page Dockerfile - Static export with pnpm workspaces
# Root Directory must be set to repo root in Railway
FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@10.32.1 --activate

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

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy nginx config template and entrypoint script
COPY services/landing-web/nginx.conf.template /etc/nginx/conf.d/default.conf.template
COPY services/landing-web/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Verify files were copied
RUN ls -la /usr/share/nginx/html

# Railway will set PORT env var - expose it (defaults to 80 in script)
EXPOSE 80

# Use custom entrypoint that handles PORT env var
ENTRYPOINT ["/docker-entrypoint.sh"]
