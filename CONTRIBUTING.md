# Working as a 3-Person Team on One Repo

One shared GitHub repo, one Postgres/Redis setup per developer's machine (via `docker-compose up`), never a shared live database — everyone runs the full stack locally, and the repo is how code moves between you, not a shared server.

## Initial setup (once)

1. One person creates the GitHub repo (private, under one person's account or a shared GitHub org/team — an org is cleaner for a 3-person group project, easier to manage access without one person "owning" it).
2. That person adds the other two as **collaborators** (Settings → Collaborators), or as team members if using an org.
3. Everyone clones it locally:
   ```bash
   git clone https://github.com/<your-org-or-user>/<repo-name>.git
   cd <repo-name>
   cp .env.example .env   # fill in local values, .env is gitignored — never pushed
   ```
4. Set up branch protection on `main` (Settings → Branches → add rule for `main`): require at least 1 pull-request review before merging, and require the branch to be up to date before merging. This is what actually prevents the classic group-project disaster of one person's untested push breaking everyone else's local setup.

## Branching strategy — keep it simple

- **`main`** — always working. Nobody pushes to `main` directly; it only updates via merged pull requests.
- **One feature branch per unit of work**, named by area and task: `core-api/auth-sessions`, `inference-service/predict-endpoint`, `workers/paysim-consumer`, `ml/xgboost-training`. Since your architecture already splits cleanly into `core-api` / `inference-service` / `workers` / `notebooks`, this naming convention also roughly maps to "who's likely working on what" without formally assigning it.

```bash
git checkout main
git pull
git checkout -b core-api/auth-sessions
# ... do the work ...
git add .
git commit -m "Add session-based auth with Redis backend"
git push -u origin core-api/auth-sessions
# open a Pull Request on GitHub, ask one of the other two to review, then merge
```

## Why a PR-based flow specifically (not just pushing to main)

Beyond avoiding conflicts, this is also what your spec's Section 3.8 is checking for: "commits must be made regularly and meaningfully throughout the semester" and "a repository containing a single commit made shortly before submission will be treated as evidence of poor development process." A steady stream of small, dated, individually-attributed commits and PRs across the semester is exactly the evidence trail that satisfies this — and it happens naturally if you actually work this way, rather than needing to be manufactured near the deadline.

## Splitting the work along the architecture's own seams

The locked architecture (see README.md Section 5) already divides into independent pieces — use that division for task assignment, since it minimizes how often two people need to touch the same file:

| Area | Roughly independent of | Good for |
|---|---|---|
| `core-api/` (auth, RBAC, CRUD, dashboards) | `inference-service`, `workers` | Whoever's strongest on backend/web |
| `inference-service/` (model loading, `/predict`) | `core-api` (only needs the HTTP contract agreed) | Whoever's doing the model training too — same person naturally owns both |
| `workers/` (4 streaming processes) | `core-api` internals | Whoever wants to focus on the Redis Streams/real-time piece |
| `notebooks/` (data loading, feature engineering, training, evaluation) | everything else until a model artifact is produced | The person driving the ML side |

**Agree on the contract before splitting, not after:** the `inference-service`'s `/predict` request/response schema (exact field names, types) needs to be settled by all three of you *before* `core-api` and `inference-service` are built in parallel — otherwise you'll integrate two pieces that don't fit. Same for the feature-engineering function signature that both the training notebook and the `workers/` consumer need to call identically (this is the same training/serving-consistency point already flagged in README Section 7.1 — write that function once, in a shared module both notebooks and workers import, don't reimplement it twice).

## Avoiding merge conflicts on shared files

- `docker-compose.yml`, `.env.example`, and the SQLAlchemy models directory are the most likely conflict points since everyone eventually touches them. Whoever adds a new service or table, do it in its own small PR, merged quickly, rather than batching it into a bigger feature branch that sits open for days.
- Database schema changes go through Alembic migrations (one migration file per change, committed), not manual `ALTER TABLE` — so schema history is itself part of the Git history, not something only one person's local DB knows about.

## Day-to-day

```bash
# start of a work session
git checkout main && git pull
git checkout -b <your-branch>

# whenever you want to check what's changed on main since you branched
git fetch origin && git log main..HEAD    # what you have that main doesn't
git log HEAD..origin/main                  # what main has that you don't

# keep your branch current if main has moved on while you were working
git checkout main && git pull
git checkout <your-branch>
git merge main    # resolve any conflicts locally, then keep working
```

## Running the stack locally (any of the three of you)

```bash
docker-compose up --build
```
Brings up `nginx`, `core-api`, `inference-service`, all four workers, `postgres`, and `redis` together. Each person runs this independently on their own machine — nobody needs to share a live server for development.
