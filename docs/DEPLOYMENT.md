# Deployment and development

## Local development

Each component runs in Docker. The host needs no installation.

```bash
docker compose watch   # start both services with live reload
docker compose down    # stop
```

- API — http://localhost:8000 (`/health`, `/docs`)
- Web — http://localhost:3000

`docker compose watch` copies the changed files into the running containers. It does not
bind-mount the working tree. Therefore the build artifacts (`.next`, `node_modules`,
`__pycache__`) stay in the containers and do not go into the checkout.

### Make the findings again without a fetch

The system stores each section verbatim. Therefore it can compute again what a clause is,
and which concept the clause carries. After a change to the clause splitter or the lexicon,
use these commands:

```bash
ixq reclassify              # every substance
ixq reclassify --substance ramipril
```

`ixq run` gets the corpus again to answer a question that the stored bytes already answer.
Each fetch is billable.

### Upgrade an existing database

The schema is create-only, and `connect()` refuses a file that it does not recognise.
Therefore a database from an earlier build must move forward before the API opens it:

```bash
ixq upgrade
```

The command only adds columns, and it leaves each new column NULL. A document that the
system fetched before a field existed has no value for that field. To invent a value states
something about a page that no person examined. Do not delete the database instead: it
contains hundreds of billable fetches, and `ixq init` does not restore them.

### Add dependencies

```bash
make add-py pkg=httpx    # Python, into ixq
make add-py pkg=httpx member=bdheal
make add-js pkg=zod      # Node
docker compose build     # rebuild images with the new dependency
```

The Makefile exists for these commands and for `make release` only. The `docker compose
run` commands below them are long. The `--user` flag that they need on Linux must not be
used on macOS. `make lock` makes the two lockfiles again after a manual edit to a
manifest.

`uv.lock` and `web/pnpm-lock.yaml` are in the repository, and the images install from
frozen lockfiles. Therefore a build gives the same result on each machine.

## Deploying

Put the web application on Vercel. Set the root directory to `web` and set `API_URL` to the
public URL of the API. Put the API on Render as a free web service. The two services do not
need a payment card.

The project ships the corpus. It does not scrape the corpus in place. `ixq run` writes
`data/*.db` on the local machine and `docker build` puts the files into the image. To refresh the
data, build the image again and deploy again. The API only reads. Therefore the container
needs a writable filesystem, because `bdheal` applies its schema on each connection. But the
container does not need a permanent filesystem: no data that the API writes at runtime
continues after the request that wrote it. This lets the API operate on a free tier, because
a free Render instance has no permanent disk. The API supplies each endpoint in
approximately 70 MB of the 512 MB of the free instance.

`data/` is in `.gitignore`. Therefore the release must **build the image locally and push it
to a registry**. If Render builds from the repository, the service has empty databases.

```bash
# one-time: a GitHub personal access token with write:packages
echo $GH_TOKEN | docker login ghcr.io -u <github-user> --password-stdin

# every release: build, push, and tell Render to pull the new tag
make release
```

`make release` reads `GH_USER` and `RENDER_DEPLOY_HOOK` from `.env`, which is in
`.gitignore`. If the two values are in a different location, supply them in the
environment.

Make the service one time as a Render **web service from an existing image**. Do not make a
private service, because only other Render services can connect to a private service. Point
the service at `ghcr.io/<github-user>/ixq-api` and set the port to 8000. A public GHCR
package needs no registry credentials on the service.

`make release` is necessary because CI cannot do this work: `data/` is in `.gitignore`,
therefore a GitHub Actions runner has no corpus to put into the image. The two build flags
are both necessary. Render needs `linux/amd64`. Without `--provenance=false`, buildx makes a
multi-architecture manifest list that Render will not pull. The last `curl` command calls
the Render deploy hook from the Settings tab of the service. A service that uses an image
never deploys again on a tag push. Keep the hook URL in the environment and not in a
file. It is a secret, and any person who has it can start a deploy.

**The image tag is the git HEAD, and not the working tree.** `TAG` is
`git rev-parse --short HEAD`, but `docker build` uses the working tree. Therefore an image
that a build makes from uncommitted changes has a tag that does not identify its contents.
Commit before a release to keep the image reproducible.

### Keep the service awake

A free Render service stops after 15 minutes with no traffic. Each page is a Server
Component. Therefore an API that is asleep does not make a page slow — it stops the page. An
external pinger (cron-job.org) requests `/health` in that 15-minute period.

A scheduled GitHub Action was the first solution, and it does not operate correctly.
`schedule` is best-effort. In 24 sequential runs, the requested interval was 13 minutes but
the mean interval was 22 minutes, with a maximum of 46 minutes. 21 of the 24 intervals were
longer than the stop threshold. Nine runs took 39 to 41 seconds and not 7 seconds, because
the ping was waking a service that had already stopped. A scheduler with 20 minutes of
jitter cannot hold a 15-minute period. Use a tool that is made for this.

On the free plan, uptime is the constraint. Memory and image size are not. The allowance is
750 instance hours for each workspace for each calendar month. A service that operates
continuously in a 31-day month uses 744 hours. This is a margin of six hours, and for one
service only. This is why the web half of the project is on Vercel.

The same image operates without modification on Cloud Run
(`--port 8000 --allow-unauthenticated`) with a Google billing account. Render is the
default because it needs no card.

### Prove that the databases shipped

Each page is a Server Component. Therefore the browser never calls the API, and the API
needs no CORS configuration. Before a change goes out, run the image with no volume mounted:

```bash
docker run --rm -p 8099:8000 "$IMG"
curl localhost:8099/substances   # empty array means the databases did not ship
```
