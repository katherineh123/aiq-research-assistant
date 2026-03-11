# Market Share Model — Conversation Export
**Skill:** /market-share-model
**Market:** Online Advertising
**Companies:** Google, Meta, Amazon, Microsoft
**Date:** 2026-03-10

---

**User:** /market-share-model online advertising market share

**Assistant:** Got the market: online advertising. Which companies do you want to analyze? Suggested: Google, Meta, Amazon, Microsoft, Apple, TikTok, Snap, Pinterest.

---

**User:** analyze btwn the top 4

**Assistant:** Top 4 by ad revenue: Google, Meta, Amazon, Microsoft. Presented 6-phase plan: (1) current market share, (2) factor brainstorm, (3) historical data pull, (4) formula design, (5) backtest, (6) forward predictions. Asked for approval.

---

**User:** yeah

**Assistant:** Checked local data files. Found `/equity-research/data/online_advertising_mock_data.csv` — exact match for market and companies. Presented 2024 market share table:
- Google: 26% / $264.6B
- Meta: 21% / $156.4B
- Amazon: 14% / $56.2B
- Microsoft: 4% / $13.5B
- Top-4 total: 65% / $490.7B
Note: data is mock/estimated. Google losing share slowly, Amazon the big gainer.

---

**User:** yeah [to proceed to factor brainstorm]

**Assistant:** Proposed 5 factors: MAU, ad targeting quality, platform investment, commerce/retail media integration, new format monetization.

---

**User:** why don't we focus on user time on platform and ad dollars per time on platform as well as trends in growth / usage rates of users

**Assistant:** Revised factors to: (1) time on platform hrs/user/day, (2) ad revenue per hour on platform, (3) MAU growth rate YoY, (4) time on platform growth rate YoY. Noted local file has MAU and ad revenue but not time-on-platform — would need web search. Asked clarifying questions on MAU level vs growth rate, and daily hours vs total hours.

---

**User:** lets just estimate it based on historical MAU vs ad revenue + assume average growth rates (so whatever the average MAU growth) will continue for the next few years. so each company has a calculated "efficiency" which is MAU vs revenue + MAU growth and we use that to project forward market share

**Assistant:** Proposed simplified formula:
- Efficiency = 2024 Ad Revenue / 2024 MAU ($/user, held constant)
- MAU[Y] = MAU[2024] × (1 + avg_MAU_growth)^(Y-2024)
- Revenue[Y] = MAU[Y] × Efficiency
- Share[Y] = Revenue[Y] / Sum of top-4 Revenue[Y]

Presented inputs table with computed efficiency and avg MAU growth per company. Asked if efficiency should be trended vs held constant.

---

**User:** can you make a table for each company with efficiency and mau growth per year for the data you have and display it. if it is consistent then we can proceed with this formula

**Assistant:** Computed per-year efficiency ($/user) and MAU growth YoY for all 4 companies from the CSV:
- Google: efficiency $58→$110 (steady rise), MAU growth ~3-5% (consistent, one flat year)
- Meta: efficiency $23→$36 (dip in 2022 from iOS 14.5 hit, then recovery), MAU growth volatile
- Amazon: efficiency $47→$70 (smooth), MAU growth decelerating 33%→14% (very consistent)
- Microsoft: flat/noisy efficiency ($24-29), alternating 0%/25% MAU growth (data granularity artifact)
Flagged: Amazon's 5-yr avg of 21.9% likely overstates forward growth given deceleration trend.

---

**User:** okay can we have an average efficiency growth rate for all of these and then proceed using the efficiency growth + mau growth to calculate an estimate for ad revenue and therefore market share for each of the businesses

**Assistant:** Added efficiency growth rate dimension. Per-year efficiency growth table:
- Google avg: +14.3% (inflated by 2021 post-COVID spike of +36%)
- Meta avg: +9.7% (clean except 2022 iOS dip)
- Amazon avg: +8.7% (consistent)
- Microsoft avg: +1.9% (noisy)

Updated formula: Revenue[Y] = MAU[Y] × Efficiency[Y], where both grow at their respective avg rates.

Forward projections (using Amazon 21.9% MAU growth):
- Amazon gains +3.9pp share by 2027 (11.5%→15.4%)
- Google -1.9pp, Meta -1.6pp, Microsoft -0.5pp

---

**User:** lets recalculate using amazons latest growth rate and then include a master table using all the inputs that outputs the smaller estimate table output

**Assistant:** Switched Amazon MAU growth to 14.3% (most recent year, 2024). Presented:

**Master Inputs:**
| Company | 2024 MAU | 2024 Efficiency | MAU Growth | Efficiency Growth |
| Google  | 2.4B     | $110.25         | 3.7%       | 14.3%             |
| Meta    | 4.3B     | $36.37          | 7.5%       | 9.7%              |
| Amazon  | 0.8B     | $70.25          | 14.3%      | 8.7%              |
| MSFT    | 0.5B     | $27.00          | 11.7%      | 1.9%              |

**Projections (revised):**
- Amazon gains only +1.6pp (11.5%→13.1%) — more defensible
- Google: 53.9%→53.4% (-0.5pp), Meta: 31.9%→31.1% (-0.8pp), Microsoft: 2.8%→2.4% (-0.4pp)
- Top-4 total grows $490.7B → $824.6B by 2027

---

## Model Summary

**Formula:**
```
Efficiency[Y] = Efficiency[2024] × (1 + avg_efficiency_growth)^(Y - 2024)
MAU[Y]        = MAU[2024] × (1 + avg_mau_growth)^(Y - 2024)
Revenue[Y]    = MAU[Y] × Efficiency[Y]
Share[Y]      = Revenue[Y] / Σ Revenue[Y] across all 4 companies
```

**Key caveats:**
- Share is expressed as % of top-4 combined (excludes ~35% held by TikTok, Snap, Pinterest, others)
- Data sourced from mock/estimated local CSV — not reported figures
- Google's efficiency growth avg inflated by 2021 post-COVID spike; likely overstates forward efficiency gains
- Microsoft MAU data has granularity artifacts (stored at 0.1B increments) causing noisy growth rates
- Amazon MAU growth conservatively set to most recent year (14.3%) rather than 5-yr avg (21.9%)
