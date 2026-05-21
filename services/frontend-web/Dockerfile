# Frontend Dockerfile - Multi-stage build with pnpm workspaces
# IMPORTANT: Root Directory must be set to "/" (repo root) in Railway
FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@10.32.1 --activate

# Install dependencies
FROM base AS deps
WORKDIR /app
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY packages/ui/package.json ./packages/ui/
COPY services/frontend-web/package.json ./services/frontend-web/
RUN pnpm install --frozen-lockfile

# Build the application
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/ ./
COPY packages/ui/ ./packages/ui/
COPY services/frontend-web/ ./services/frontend-web/

# Build arguments for environment variables
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID
ARG NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_MIXPANEL_TOKEN

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=$NEXT_PUBLIC_GOOGLE_CLIENT_ID
ENV NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=$NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_MIXPANEL_TOKEN=$NEXT_PUBLIC_MIXPANEL_TOKEN

WORKDIR /app/services/frontend-web
RUN pnpm build

# Production image
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production

# Create non-root user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy built application (standalone output mirrors monorepo structure)
COPY --from=builder /app/services/frontend-web/public ./services/frontend-web/public
COPY --from=builder --chown=nextjs:nodejs /app/services/frontend-web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/services/frontend-web/.next/static ./services/frontend-web/.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "services/frontend-web/server.js"]
