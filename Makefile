# Wraps the container invocations that are impractical to type by hand.
# Run the stack directly: docker compose watch / down / build
#
#   make add-py pkg=httpx              -> adds to preward (the app)
#   make add-py pkg=httpx member=bdheal

member ?= preward

ifeq ($(shell uname),Linux)
USER_FLAG := --user $(shell id -u):$(shell id -g) -e HOME=/tmp
endif

RUN  := docker compose run --rm --no-deps $(USER_FLAG)
# The workspace root is the repo root, so that is what uv must see: the lockfile it
# writes is /uv.lock, and --package picks which member a dependency lands on.
UV   := $(RUN) -v $(CURDIR):/app api uv
PNPM := $(RUN) -v $(CURDIR)/web:/app web pnpm --store-dir /tmp/pnpm-store

.PHONY: lock add-py add-py-dev add-js

lock:
	$(UV) lock
	$(PNPM) install --lockfile-only
add-py:
	$(UV) add --no-sync --package $(member) $(pkg)
add-py-dev:
	$(UV) add --no-sync --dev --package $(member) $(pkg)
add-js:
	$(PNPM) add --lockfile-only $(pkg)
