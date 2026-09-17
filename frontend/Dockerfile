FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Backend URL the Next.js server proxies /api/* to. Defaults to the compose
# service name; override only when the API runs elsewhere.
ARG API_INTERNAL_URL=http://kyokki-api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# Standalone output does not include public/; without this the app icons 404 in production
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
