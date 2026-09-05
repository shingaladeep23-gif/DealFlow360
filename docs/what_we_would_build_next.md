# What we would build next

Deliverable 4. Ordered by what we think actually matters, not by what is
easiest to demo.

## 1. Approve a specific version, not just "the current one"

Today an approval binds to a fingerprint of the order, and any edit supersedes
the chain. That is correct but blunt: fixing a typo in a line description is
governance-neutral, yet it retires a chain and sends the deal round again.

Next: snapshot the approved **lines** onto the approval, diff them on change,
and only supersede when the diff touches price, quantity, product or tier. The
approval screen would then show the reviewer exactly what changed since they
last looked, rather than a fresh chain with no memory of the previous one.

## 2. Delegation and out-of-office

The chain routes to a role, and anyone holding that role can act. Real approval
chains need a named approver, a deputy, and an escalation timer that reassigns
rather than only flagging a delay on a dashboard. `df_health_signal_approval_delay`
already measures the wait; nothing acts on it automatically.

## 3. Make the risk model configurable rather than constant

`6 · blended + 3 · max` and the 40-point split are deliberate, documented and
tested — but they are constants in code. A finance team should be able to tune
the weights per company, and see the effect on historical deals before saving.
That means a small rules model plus a back-test screen, and it is the point at
which "transparent deterministic engine" becomes genuinely self-governing.

## 4. Learn the upsell ranking from outcomes

The current ranking is honest and explainable: curated pairings, real
co-purchase counts, a promotion bonus, a margin floor. It does not learn. With
more time we would log which suggestions were added, dismissed and ultimately
sold, and weight future ranking by acceptance rate per customer segment — while
keeping the reason string, because a rep who cannot see *why* a suggestion
appeared will not trust it.

## 5. Multi-currency and multi-company

Listed as a bonus in the problem statement and not attempted. The billing
engine already sets `company_id` explicitly on generated invoices, but ceilings,
the risk threshold and the default discount are global `ir.config_parameter`
values. They would need to become per-company records, and the allocation engine
would need inter-company transfer rules before a split could cross companies.

## 6. Negotiation beyond a single percentage

A customer can currently counter with one number that applies to the whole
order. Real negotiation is line-level: "drop the service, keep the hardware
price". The data model supports it — `dealflow.negotiation` could carry lines —
and the portal already has a line-level comment box that would be the natural
place to attach it.

## 7. Delivery promise, properly

`df_health_signal_delivery_risk` measures stock shortfall, which is a proxy.
The spec asks for *delivery promise slippage*: committed date versus the date
the allocation engine can actually achieve, including lead times and the
backorder. That needs a promised-date field and a scheduling pass over
`stock.rule` lead times.

## 8. Tests we know are missing

- **Concurrency.** Two managers approving the same step simultaneously; a rep
  editing a line while an approval commits. The write guard makes this safe at
  the field level, but nothing tests it under a race.
- **Browser tests.** Every OWL screen is covered only through its ORM calls.
  `HttpCase` tours would catch a template that renders but is unusable.
- **Migration from real data.** The migrations are tested on databases this
  project created. A restore from a genuinely old snapshot is untested.

## Known limitations we would fix rather than document

- A category or tier ceiling of `0` means *unset*. A business that genuinely
  wants "no discount permitted on this category" cannot express it. This needs
  a nullable field or an explicit "no discount allowed" flag.
- `df_last_activity` counts any chatter message as activity, so an automated
  nudge makes a stalled deal look alive. It should distinguish inbound customer
  activity from internal noise.
- The portal shows one flat discount per line. An order carrying both a
  pricelist reduction and a rep discount reads as a single number, which is
  fine for a customer but hides the split a rep needs.
