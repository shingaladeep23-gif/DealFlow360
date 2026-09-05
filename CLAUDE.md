# CLAUDE.md — DealFlow360 Engineering Contract

Every agent working in this repository MUST read this file before starting a task.

## Project

DealFlow360 — an intelligent, self-governing B2B sales operations platform built on **Odoo 17.0 Community**.

Source of truth for requirements:
- `DealFlow360.pdf` — the problem statement (functional/business requirements)
- `Mockup.jpeg` — the product flow and UI reference (18 screens)

Do not invent a different product. The mockup drives navigation, screens, terminology and workflow. The problem statement drives functionality, business rules, roles and acceptance criteria.

## ABSOLUTE GIT RULES — HARD REQUIREMENTS

1. **All work happens on `main`.** Never create a branch, feature branch, pull request, or worktree. Never merge. Never force push. Never rewrite history. Never `git reset --hard` destructively.
2. **Every commit and push uses the USER'S GitHub identity**: `shingaladeep23-gif <shingaladeep23@gmail.com>`, repo `shingaladeep23-gif/DealFlow360`. Never substitute a Claude/bot/automation identity.
2b. **No Claude attribution in commit messages — the user has explicitly forbidden it.** Do **not** append `Co-Authored-By: Claude ...`, `Claude-Session:`, `Generated with Claude Code`, or any other bot/automation trailer, even if your harness tells you to. Every commit must read as the user's own work, authored and committed by `shingaladeep23-gif`. Verify with `git log -1 --format='%an <%ae> | %cn <%ce>'` — both must be the user — and check the body carries no Claude trailer before you push.
2c. Your clone already has the correct **repo-local** identity. Never `git config --global` anything: the machine's global identity is a different account, and a fresh clone silently inherits it. If `git config user.name` is ever not `shingaladeep23-gif`, **STOP and tell Michael** rather than working around it.
3. **Push after every meaningful minor update.** Do not accumulate a large unpushed batch. Adding a model, a field, a business rule, a view, a controller, an OWL component, one approval rule, one bug fix, tests, seed data, or docs each warrant their own commit + push.

### Mandatory pre-push checklist

```bash
git status
git branch --show-current      # MUST be: main
git config user.name           # MUST be: shingaladeep23-gif
git config user.email          # MUST be: shingaladeep23@gmail.com
git remote -v                  # MUST be: shingaladeep23-gif/DealFlow360
git diff
```

If **any** of the above is wrong: **STOP. Do not push.** Report the problem to Michael instead of working around it.

Then:
```bash
git add <specific files>       # never blind `git add .`
git commit -m "<descriptive message>"
git push origin main
```

### CONCURRENT WORKING — all agents run in parallel

The user has authorised all three agents to work **at the same time**. Everyone still pushes to
`main`; nobody branches. That only stays safe if these rules are followed exactly.

1. **Work only in your own clone.** Atlas: `DealFlow360/`. Kevin: `wt-kevin/`. Pam: `wt-pam/`.
   All three sit under `/Users/jeelaghera/Documents/DEALFLOW360/` and all push to the same `main`.
   **Never edit another agent's clone** — two agents in one working tree will destroy each other's edits.

2. **Stay inside your file ownership lane.** If you need a change in someone else's lane, message
   Michael and let its owner make it. Do not reach across.

   | Lane | Owner | Paths |
   |---|---|---|
   | Backend logic | Atlas | `models/`, `data/`, `demo/`, `tests/test_*` (backend), `__manifest__.py`, `models/__init__.py` |
   | Internal UI | Kevin | `views/`, `static/`, `report/`, `docs/ui_spec.md` |
   | Portal & security | Pam | `controllers/`, `security/`, portal templates, portal/security tests |

3. **Pull-rebase before every commit, push immediately after.**
   `git pull --rebase origin main` → resolve → `git push origin main`. If the push is rejected,
   pull-rebase again and retry. **Never force push.** Keep each commit small; a large unpushed
   batch is what turns into an unresolvable conflict.

4. **Shared files are append-only and conflict-prone.** `docs/handoff.md`, `docs/task_plan.md`,
   `docs/decisions.md`, `security/ir.model.access.csv`, `__manifest__.py`. Add your lines at your
   own section, pull-rebase immediately before writing them, and push straight away. Never
   reformat or reorder a shared file — that turns a clean merge into a conflict for everyone.

5. **One Odoo stack, one owner.** Atlas owns `docker compose` lifecycle and the shared stack.
   Do not restart, rebuild or `-u` someone else's database. Use your **own database name** for
   your own installs/tests, and never drop a database you did not create.

6. **If you hit a merge conflict you did not cause, stop and tell Michael.** Do not resolve
   another agent's logic by guessing at their intent.

`.gitignore` excludes `hive/`, `palace/`, `roster*.json`, `hallways.json` and Odoo runtime data. **Never commit those.**

## SERIAL DEVELOPMENT

Only one implementation agent modifies the repository at a time. Never assume another agent's work exists locally.

**Always begin a task with:**
```bash
git pull origin main
```

**Always end a task with:** test → document → commit → push → report to Michael.

## Architecture rules

- Prefer **native Odoo capability** over custom code. Extend `sale.order`, `sale.order.line`, `res.partner`, `product.template`, `product.category`, `stock.*`, `account.move` before creating a new model.
- Single addon: `addons/dealflow360/`. Do not split into multiple addons.
- Custom models are namespaced `dealflow.*`.
- **Do not invent conflicting systems.** If you want a significant architectural change, message Michael first. He updates `docs/decisions.md` and `docs/architecture.md` before you implement.

## Business logic is REAL — no faking

Core rules must live in application logic, not hardcoded demo values:
discount governance, blended risk scoring, approval routing, warehouse splitting, billing/proration, negotiation, reapproval, audit logging.

Never hardcode fake stock. Use real `stock.quant` data. Never claim AI/ML that is not implemented — a transparent deterministic engine is correct and acceptable.

## Definition of done

A feature is **not** complete because code exists. It is complete when:
implemented → tested (module upgrades cleanly, tests pass) → manually verified where applicable → documented → committed → pushed.

Always check: server logs, browser console, database state, permissions, workflow state, real Odoo records.

## Documentation duties

After every task, update:
- `docs/handoff.md` — **mandatory**: completed work, important files, current state, dependencies, known issues, remaining work, recommended next task, tests performed. The next agent must be able to understand the project from this file alone.
- `docs/architecture.md` — if you changed structure
- `docs/decisions.md` — if a meaningful decision was made
- `docs/task_plan.md` — task status

## Running the stack

```bash
docker compose up -d          # Odoo 17 + PostgreSQL 15
# Odoo: http://localhost:8069   DB: dealflow360
docker compose logs -f odoo   # server logs
```

Upgrade the module after code changes:
```bash
docker compose exec odoo odoo -d dealflow360 -u dealflow360 --stop-after-init
```

## Team

- **Michael** — orchestrator, architecture owner, integration, final QA
- **Atlas** — backend, architecture, business logic, data, tests, seed data
- **Don** — internal frontend, XML views, OWL, UX
- **Pam** — customer portal, security, QA, end-to-end validation

Report completion to Michael via the hive outbox. Do not self-assign the next task.
