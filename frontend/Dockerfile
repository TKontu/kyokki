# Stage 1: Builder
FROM node:18-alpine AS builder
WORKDIR /app

# Copy package.json and lock file
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application source code
COPY . .

# Build the Next.js application
RUN npm run build

# Stage 2: Production Runner
FROM node:18-alpine AS runner
WORKDIR /app

# Set the NODE_ENV to 'production'
ENV NODE_ENV=production

# Copy built assets from the builder stage
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Expose the port the app runs on
EXPOSE 3000

# The new 'server.js' is not created by default in recent Next.js versions.
# We need to use the new output format.
# The start command is now part of the standalone output.
CMD ["node", "server.js"]
