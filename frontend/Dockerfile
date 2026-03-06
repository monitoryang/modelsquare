# Build stage
FROM node:20-alpine AS builder

# Install git for npm dependencies that need it
RUN apk add --no-cache git

WORKDIR /app

# Build arguments for Vite environment variables
ARG VITE_API_URL=http://localhost:8020
ARG VITE_SRS_HTTP_URL=http://localhost:8090

# Set environment variables for build
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_SRS_HTTP_URL=$VITE_SRS_HTTP_URL

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
