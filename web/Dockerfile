FROM node:24-alpine

RUN corepack enable pnpm
WORKDIR /app
RUN chown node:node /app

USER node

COPY --chown=node:node package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY --chown=node:node . .

EXPOSE 3000
CMD ["pnpm", "dev"]
