# Metric definitions

One definition per metric, used in SQL, reports, the dashboard and the AI commentary. If a stakeholder uses
a word differently, this table settles it. The phase 1 SQL views implement these definitions; each row names
the view that will hold the metric.

**Grain:** business × channel × ISO week (Monday start) unless stated. **Currency:** USD.

## Funnel

| Metric | Definition | B1 Hearth Box | B2 Ledgerline | B3 Atlas Outdoor | Source |
|---|---|---|---|---|---|
| Spend | Media cost booked to the week, after late corrections | | | | `v_spend` |
| Impressions | Ad views reported by the platform | | | | `v_funnel` |
| Clicks | Ad clicks reported by the platform | | | | `v_funnel` |
| Lead | First identifiable action | Account sign-up | Demo request (deduplicated by e-mail domain within 30 days) | Basket saved with e-mail | `v_funnel` |
| Qualified lead | A lead with clear purchase intent | Checkout-ready (address and payment entered) | Sales-accepted lead (SQL) | Checkout started | `v_funnel` |
| Customer (conversion) | First paid transaction | First paid box | Signed contract | First order shipped | `v_customers` |
| Revenue | Customer payments in the valuation horizon (24 months) | Box revenue | Licence revenue | Order revenue net of returns | `v_cohort_value` |
| Contribution | Revenue minus the variable cost of serving the customer | Food, packaging, delivery | Hosting, support (80% gross margin) | Goods, shipping, payment, returns | `v_cohort_value` |

## Cost and return: four different questions

The same word ("return", "CAC") answers different questions depending on what is counted. Every dashboard
tile and report states which one it shows.

| Metric | Question it answers | Formula | Evidence type |
|---|---|---|---|
| **Platform CAC / ROAS** | What does the ad platform claim? | spend ÷ platform-reported conversions (`line_week.platform_cac`) | An accounting rule set by the platform. Adds view-through and multi-touch credit, so it is the most generous figure |
| **Last-click CAC / return** | What does our own CRM credit to the channel? | spend ÷ customers whose last click was the channel (`line_week.last_click_cac`) | An accounting rule we control. Still includes customers who would have bought anyway |
| **Blended CAC** | What does a customer cost overall? | total spend ÷ all new customers, paid and organic | Descriptive |
| **Incremental CAC / return** | What did the advertising actually cause, on average? | spend ÷ customers caused by ads; incremental contribution ÷ spend | Causal if from an experiment; model-based if from historical data |
| **Marginal CAC / return** | What would the next dollar buy? | Δspend ÷ Δcustomers at the current spend level; the slope of the response curve | Model-based, calibrated to experiments where they exist |
| Cost per lead (CPL) | | spend ÷ leads | Descriptive |
| Cost per qualified lead | | spend ÷ qualified leads | Descriptive |

**Return** is always *contribution per advertising dollar*, not revenue per dollar. A return of 1.0 means
the advertising exactly pays for itself over the horizon. Revenue ROAS overstates the value of low-margin
businesses and is not used for decisions.

## Customer value and profit

| Metric | Definition |
|---|---|
| Customer value (24-month) | Expected discounted contribution from one new customer over 24 months, minus one-off acquisition costs (discounts, commission, onboarding). Excludes advertising |
| Incremental contribution profit | incremental customers × customer value − advertising spend. **The decision metric** |
| Contribution profit (weekly P&L) | contribution from all active customers that week − one-off acquisition costs of new customers − ad spend (`business_week_pnl`). What finance reports; forecast in phase 2. Mostly driven by the existing customer base, so it moves slowly with marketing decisions |
| Payback months | Months until a customer's cumulative discounted contribution covers their CAC and one-off costs |
| Lead-to-qualified rate | qualified leads ÷ leads |
| Qualified-to-customer rate | customers ÷ qualified leads (B2: the sales team's win rate) |

## Forecast accuracy (phase 2)

| Metric | Plain meaning |
|---|---|
| MAE | Average size of the error, in the metric's own units |
| RMSE | Like MAE, but large misses count more |
| WAPE | Total absolute error as a share of the total actual value; comparable across businesses |
| Bias | Average signed error as a share of the actual. Positive means the forecast runs high |

## Data trust flags

Each weekly row carries flags from the phase 1 checks: `tracking_outage`, `attribution_change`,
`duplicate_leads`, `cost_restated`. Flagged rows stay in the data but are excluded from model fitting where
the flag makes the row misleading. The AI commentary must mention any flag on a metric it reports.
