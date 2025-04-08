# Stage 1: Build environment
FROM node:18-alpine as build

WORKDIR /app

# Copy source files
COPY . .

# Accept build arguments
ARG API_URL
ARG MAPBOX_TOKEN

# Replace configuration values 
RUN sed -i "s|http://localhost:8000/api|$API_URL|g" app.js
RUN sed -i "s|pk.your_mapbox_token_here|$MAPBOX_TOKEN|g" app.js

# Stage 2: Production environment
FROM nginx:alpine

# Copy built application from first stage
COPY --from=build /app /usr/share/nginx/html

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:80 || exit 1