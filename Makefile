# Wraps the container invocations that are impractical to type by hand.
# Run the stack directly: docker compose watch / down / build
#
#   make add-py pkg=httpx              -> adds to ixq (the app)
#   make add-py pkg=httpx member=bdheal
#   make release                       -> builds, pushes and deploys the API

member ?= ixq

ifeq ($(shell uname),Linux)
USER_FLAG := --user $(shell id -u):$(shell id -g) -e HOME=/tmp
endif

RUN  := docker compose run --rm --no-deps $(USER_FLAG)
# The workspace root is the repo root, so that is what uv must see: the lockfile it
# writes is /uv.lock, and --package picks which member a dependency lands on.
UV   := $(RUN) -v $(CURDIR):/app api uv
PNPM := $(RUN) -v $(CURDIR)/web:/app web pnpm --store-dir /tmp/pnpm-store

.PHONY: lock add-py add-py-dev add-js release

lock:
	$(UV) lock
	$(PNPM) install --lockfile-only
add-py:
	$(UV) add --no-sync --package $(member) $(pkg)
add-py-dev:
	$(UV) add --no-sync --dev --package $(member) $(pkg)
add-js:
	$(PNPM) add --lockfile-only $(pkg)

# The corpus lives only on this machine — `data/` is gitignored — so CI has nothing to
# bake into the image and the build has to happen here. Render's image-backed services
# do not redeploy themselves when a tag is pushed, hence the third step.
#
# `.env` is sourced rather than included: its values are quoted, which Make would carry
# into the image name verbatim. Keeping the hook a shell variable also stops Make from
# echoing a secret that triggers a deploy for anyone who reads it.
TAG := $(shell git rev-parse --short HEAD)

release:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	test -n "$$GH_USER" || { echo "GH_USER is unset (add it to .env)"; exit 1; }; \
	test -n "$$RENDER_DEPLOY_HOOK" || { echo "RENDER_DEPLOY_HOOK is unset (add it to .env)"; exit 1; }; \
	IMAGE=ghcr.io/$$(echo "$$GH_USER" | tr '[:upper:]' '[:lower:]')/ixq-api:$(TAG); \
	echo "releasing $$IMAGE"; \
	docker build --platform linux/amd64 --provenance=false -f api/Dockerfile -t "$$IMAGE" . && \
	docker push "$$IMAGE" && \
	curl -fsS "$$RENDER_DEPLOY_HOOK&imgURL=$$IMAGE" && echo "" && echo "deploy triggered"
