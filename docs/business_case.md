# Business case

> All data in this project are simulated (D-001). This document describes the decision as it would be framed
> for a real company; the numbers quoted come from `reports/ground_truth_summary_SYNTHETIC.md`.

## The decision

A group that owns three recently acquired businesses has a fixed **$2.0M annual paid-acquisition budget**.
The executive team decides, once a year with a quarterly review, how much of it each business gets and how
each business spreads its share across advertising channels.

| | Hearth Box (B1) | Ledgerline (B2) | Atlas Outdoor (B3) |
|---|---|---|---|
| What it sells | Meal-kit subscription to households | Accounting software to small firms, sold by an inside-sales team | Outdoor equipment, online store |
| How it earns | Monthly box; heavy churn after the first box | Monthly licence; about 85% of customers stay each year | One-off orders, some repeat purchases |
| Funnel | Sign-up → checkout-ready → first paid box | Demo request → sales-accepted lead → signed contract | Basket with e-mail → checkout started → first order |
| Channels | Brand search, generic search, social, affiliates | Generic search, LinkedIn, review sites, programmatic display | Shopping ads, social, retargeting, affiliates |

**Who decides:** the CEO and CFO set the total and the business floors and ceilings. The Marketing Director
proposes the channel split. Each Business Unit Director signs off their own plan.

## Current approach (the baseline the analysis has to beat)

Last year's budget was rolled forward. Within each business, money moved towards the channels with the best
platform-reported return on ad spend (ROAS). That has three known weaknesses:

1. **Platform ROAS counts customers who would have bought anyway.** Brand search and retargeting mostly reach
   people who are already looking for the company.
2. **An average return is not the return on the next dollar.** Once a channel saturates, extra spend buys
   much less than the average suggests.
3. **Lead volume is not customer value.** A channel can deliver cheap leads that the sales team rarely
   converts.

## What the analysis will produce

- A recommended allocation by business and channel. Each line has an expected gain and a pessimistic gain,
  both measured against rolling last year's plan forward.
- Experiment designs that turn the most expensive assumptions into measured facts.
- Forecasts with ranges for spend, leads, customers, CAC and contribution.
- A memo for the CEO, CFO and Marketing Director, and a dashboard to track the plan.

## Decision metric

**Incremental 24-month contribution, discounted, minus advertising spend** (D-004). Incremental means only
customers the advertising caused. Contribution is revenue minus the cost of serving the customer. Payback
months are reported alongside, because the CFO also needs cash to come back within a set time.

## Cost of each type of error

| Error | What happens | Who feels it |
|---|---|---|
| Over-fund a saturated or over-attributed channel | Money buys customers who would have come anyway. Contribution is lost with no visible warning, because the dashboard still looks good | CFO, shareholders |
| Under-fund a channel with headroom | Profitable customers go to competitors. Nothing shows up anywhere; it is an opportunity cost | Marketing Director, BU Directors |
| Chase cheap leads | The sales team wastes time on leads that do not convert, and real prospects wait | BU Director (B2) |
| Trust broken tracking | Outages or signal loss make a channel look worse or better than it is, and the budget follows the error | Data Engineering, everyone downstream |
| Move too fast on uncertain estimates | A reallocation based on a wrong curve can lose more than the status quo | CFO |

The last row is why the optimiser reports a pessimistic case and limits how far any line can move in one year.

## Assumptions in the brief that this project challenges

1. **"Maximise profitable acquisition" and "minimum acquisition volume" pull against each other.** A volume
   floor forces spend into lines that lose money at the margin. The analysis prices that floor: it reports
   how much contribution the floor costs, so management can decide whether the volume is worth it.
2. **The $2M total is treated as fixed, but it may be wrong.** The optimiser reports what one more dollar of
   total budget would earn at the optimum. If that is well above or below $1, the size of the budget is
   itself a decision worth revisiting.
3. **A payback target per business can contradict the profit objective.** At last year's mix, Atlas Outdoor
   pays back in about 13 months, so a 6-month target could not be met with any allocation (D-011).
4. **"Defensive" brand-search spend is an assumption, not a fact.** A 50% floor is kept in the base case, and
   phase 3 designs a holdout test to measure what brand search actually adds.
5. **Historical data cannot establish causation on its own.** Budgets were raised in high-demand months, so
   spend and sales rise together whether or not the ads work. Channel effects estimated from history are
   labelled *model-based*. Only the experiments produce *causal* evidence.
