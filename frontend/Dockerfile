# Прод-сборка Next.js (docs/adr/0029-prod-kontur.md, часть C). Не используется dev-стеком
# (docker-compose.yml собирает фронтенд через `npm run dev`, без этого файла) —
# только docker-compose.prod.yml.
#
# Node 24 — Active LTS на момент задачи (Node 22 уходит в Maintenance LTS, Node 20 EOL
# 30.04.2026); версия сверена в реестре, не по памяти (CLAUDE.md §5).

FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# BACKEND_ORIGIN на этапе сборки не нужен: next.config.ts читает его только в рантайме
# (rewrites() вызывается на старте сервера, не во время build).
RUN npm run build

FROM node:24-slim AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3001 \
    HOSTNAME=0.0.0.0

RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

# output: "standalone" (next.config.ts) собирает в .next/standalone минимальный
# сервер со своими node_modules — копировать node_modules всего проекта не нужно.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3001

CMD ["node", "server.js"]
