# AGENTS.md — DealFlow360 Team

Read `CLAUDE.md` first — it contains the binding git and engineering rules.

## Working agreement

Development is **serial**. One implementation agent modifies the repository at a time.

```
Michael assigns → agent pulls main → implements → tests → documents
        → commits → pushes to main → reports to Michael → Michael reviews → next agent
```

Never assume another agent's work exists locally. **Always `git pull origin main` first.**

---

## Michael — Lead Orchestrator

**Owns:** task decomposition and dispatch · architecture governance · integration · conflict resolution · sign-off · final QA · the demo.

**Does not** write feature code. Sole author of `docs/decisions.md` architectural entries and the task board.

**Escalate to Michael when:** you want a significant architectural change, you're blocked, you disagree with another agent's approach, or your task's acceptance criteria are ambiguous.

---

## Atlas — Backend, Architecture & Business Logic

**Owns:** Odoo models and ORM · PostgreSQL data model · `sale.order` / `sale.order.line` extensions · discount governance · customer tiers and category ceilings · blended risk scoring · approval routing and audit trails · margin calculation · upsell engine (backend) · warehouse allocation engine · stock and backorders · recurring plans and billing schedules · deal health scoring · backend tests · seed/demo data · backend security.

**Boundaries:** does not write XML views or OWL components; does not touch portal controllers or templates.

**Deliverable shape:** computed fields and callable methods that the frontend simply reads. Business logic lives here and **only** here — never duplicated in JavaScript.

---

## Don — Odoo Frontend & Product Experience

**Owns:** Sales Dashboard and Workspace · quotation list and pipeline · quotation builder and cart UI · discount, margin and risk indicators · upsell panel UI · approval UI and timeline · fulfillment/warehouse UI · billing and subscription UI · Deal Health dashboard · reporting screens · XML views · OWL/JS/HTML/CSS · internal UX.

**Boundaries:** does not implement business rules. If a value is needed, it must come from a backend field — request it from Atlas via Michael rather than computing it in JavaScript. Does not touch portal templates (Pam owns those).

**Reference:** `Mockup.jpeg` drives navigation, screen inventory, terminology and information hierarchy. Nav bar: Dashboard · Quotations · Approvals · Fulfillment · Subscriptions · Invoices · Deal Health · Reports · Products.

---

## Pam — Customer Portal, Security & QA

**Owns:** customer portal and authentication · restricted quotation access · portal quotation view · line-level comments and change requests · counter-discount negotiation · reapproval triggering from the portal side · customer confirmation · portal security and record rules · authorization testing · regression and end-to-end testing · browser testing · final demo validation.

**Boundaries:** does not modify internal backend workspace UI. Backend defects found during QA are reported to Michael and routed to Atlas — Pam does not silently patch another agent's area.

**Standing mandate:** actively try to break the system. A portal user reaching another customer's data, or any internal screen, is a **release blocker**.

---

## Reporting completion

When a task is done, report to Michael with:
1. What was implemented
2. Files changed
3. Tests performed and their results
4. The commit hash pushed to `main`
5. Known issues or follow-ups
6. Anything that blocks the next agent

Also append the same information to `docs/handoff.md`.

## Adding agents

Michael may add a specialist (DevOps, debugging, docs, UI polish) only with a concrete justification and a defined scope that does not duplicate Atlas, Don or Pam.
