# Wraps the container invocations that are impractical to type by hand.
# Run the stack directly: docker compose watch / down / build

ifeq ($(shell uname),Linux)
USER_FLAG := --user $(shell id -u):$(shell id -g) -e HOME=/tmp
endif

RUN  := docker compose run --rm --no-deps $(USER_FLAG)
UV   := $(RUN) -v $(CURDIR)/api:/app api uv
PNPM := $(RUN) -v $(CURDIR)/web:/app web pnpm --store-dir /tmp/pnpm-store

.PHONY: lock add-py add-js

lock:
	$(UV) lock
	$(PNPM) install --lockfile-only
add-py:
	$(UV) add --no-sync $(pkg)
add-js:
	$(PNPM) add --lockfile-only $(pkg)
