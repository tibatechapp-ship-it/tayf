# Tayf Studio AI gateway — minimal Node sidecar (LLM + image model proxy).
FROM node:20-alpine
WORKDIR /app
COPY package.json ./
COPY index.mjs ./
RUN npm install --omit=dev --no-audit --no-fund \
    && npm cache clean --force

USER node
ENV AI_GATEWAY_HOST=0.0.0.0 \
    AI_GATEWAY_PORT=3030
EXPOSE 3030

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:3030/health || exit 1

CMD ["node", "index.mjs"]
