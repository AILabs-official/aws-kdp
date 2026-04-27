# Apply Amazon Ads API for KDP — Setup Guide

End-to-end checklist to wire your KDP account into `scripts/amazon_ads_api.py`.
**Total time: ~5-9 weeks** (mostly waiting for Amazon approval).

---

## Stage 0 — Prerequisites (do these first or you will be rejected)

- [ ] At least **1 KDP book LIVE with ASIN** (not draft, not in review).
- [ ] Amazon Advertising account active. Login at https://advertising.amazon.com using your KDP account.
- [ ] Run **at least 1 manual campaign for 30+ days** before applying. Amazon rejects API applications from accounts with zero ad history.
- [ ] US KDP tax interview completed (if targeting US marketplace).

---

## Stage 1 — Create LWA Security Profile (10 min)

1. Go to https://developer.amazon.com → Sign in with your KDP account.
2. **Settings → Security Profiles → Create a New Security Profile**:
   - Name: `KDP-OS-Ads`
   - Description: `Internal automation for own KDP titles`
   - Consent Privacy URL: any public URL (your GitHub repo, blog, anywhere)
3. After saving → grab the **Client ID** (`amzn1.application-oa2-client...`) and **Client Secret**.
4. **Web Settings tab** → Edit:
   - Allowed Origins: leave blank (we use localhost)
   - Allowed Return URLs: `http://localhost:8765/callback`
   - Save.

> The redirect URI **must match exactly** what you put in `.env` later.

---

## Stage 2 — Apply for Amazon Ads API access (1-3 weeks)

This is the long pole.

1. Go to https://advertising.amazon.com/API/docs/en-us/setting-up/overview
2. Click **"Apply for access"**.
3. Fill the form:

| Field | What to write |
|---|---|
| Company / Individual | Your name (individual is fine) |
| Use case | **"Internal automation tool to manage Sponsored Products campaigns for my own KDP titles. No third-party access. No data resale."** |
| Estimated API calls/day | `100` |
| Marketplaces | Select only the ones you actually sell in (US most likely) |
| Application type | **Advertiser** (NOT Agency, NOT Tool Provider) |

4. Link your Security Profile from Stage 1.
5. Submit.

**Common rejection reasons & fixes:**
| Reason | Fix |
|---|---|
| "Use case unclear" | Reapply with explicit "own books only" language |
| "No advertising history" | Run manual campaigns 30+ days, reapply |
| "Choose Advertiser path" | Re-submit picking Advertiser, not Agency |

Re-applications are usually approved on attempt 2 if rejection 1 had a clear reason.

---

## Stage 3 — Capture refresh_token (5 min, once Amazon approves)

1. Open `.env` and fill in (keep `ADS_API_REFRESH_TOKEN` empty for now):
   ```
   ADS_API_CLIENT_ID=amzn1.application-oa2-client.xxxxxxxxxxxx
   ADS_API_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
   ADS_API_REDIRECT_URI=http://localhost:8765/callback
   ADS_API_REGION=NA
   ```

2. Run the OAuth helper:
   ```bash
   python3 scripts/ads_oauth_helper.py
   ```
   - Browser opens → click **Allow**
   - Script captures the auth code, exchanges for refresh_token, **auto-patches `.env`**

3. Verify:
   ```bash
   grep ADS_API_REFRESH_TOKEN .env
   # ADS_API_REFRESH_TOKEN=Atzr|IwEBI...
   ```

> Refresh tokens **never expire** unless you revoke consent or change Amazon password. One-time setup.

---

## Stage 4 — Find your profileId (2 min)

```bash
python3 scripts/amazon_ads_api.py list-profiles
```

Output will look like:
```json
[
  {
    "profileId": 1234567890,
    "countryCode": "US",
    "currencyCode": "USD",
    "accountInfo": {"type": "author", "name": "Your KDP Name"}
  },
  {"profileId": 9876543210, "countryCode": "UK", ...}
]
```

Copy the US `profileId` (or whichever marketplace you want), set it in `.env`:
```
ADS_API_PROFILE_ID=1234567890
```

---

## Stage 5 — Test connectivity

```bash
python3 scripts/amazon_ads_api.py test-connection
```

Expected output:
```
✓ access_token refreshed (len=300+)
✓ profile 1234567890 → US author
```

If you see ❌ — re-check `.env` values + verify the Security Profile redirect URI matches.

---

## Stage 6 — Launch your first campaign

Two paths:

### Path A — dry run first (no money spent, recommended)

```bash
python3 scripts/amazon_ads_api.py launch \
  --asin B0XXXXXXXX \
  --title "Dinosaur Coloring Book for Kids" \
  --bid 0.12 \
  --budget-auto 5 --budget-exact 10 --budget-phrase 5 \
  --keywords-exact '["dinosaur coloring book","t-rex coloring kids","dinosaur coloring book for kids 4-8"]' \
  --keywords-phrase '["coloring book ages 6-12","kids dinosaur activity book"]' \
  --dry-run
```

Reviews the rows that would be created. No API call.

### Path B — real launch

```bash
python3 scripts/amazon_ads_api.py launch \
  --asin B0XXXXXXXX \
  --title "Dinosaur Coloring Book for Kids" \
  --bid 0.12 \
  --keywords-exact '["dinosaur coloring book","t-rex coloring kids"]' \
  --keywords-phrase '["coloring book ages 6-12"]' \
  --book-id 3
```

Creates 3 live campaigns:
- **Launch Auto** — $5/day, Amazon's auto-targeting, bid $0.108 (= 0.12 × 0.9)
- **Launch Exact** — $10/day, exact-match keywords at $0.12
- **Launch Phrase** — $5/day, phrase-match keywords at $0.108

Plus negatives `free / download / pdf / kindle` on every campaign.

`--book-id` writes `ad_campaigns` rows back to `data/kdp.db` with the real `amazon_campaign_id`.

> **First-time tip**: campaigns start `ENABLED`. If you want to inspect on web console before they spend, comment out the `state` field in `create_campaign` or pause from the web UI right after launch.

---

## Stage 7 — Pull performance reports

```bash
python3 scripts/amazon_ads_api.py report --days 7 --out output/ads_report.json
```

Async report request → poll → download gzipped JSON → save. Default columns:
`campaignName, impressions, clicks, cost, purchases7d, sales7d, acosClicks7d`.

Hook this into `/weekly-cycle` for performance-analyst agent to consume.

---

## Quick reference

| Task | Command |
|---|---|
| OAuth (once after API approved) | `python3 scripts/ads_oauth_helper.py` |
| Find profile | `python3 scripts/amazon_ads_api.py list-profiles` |
| Health check | `python3 scripts/amazon_ads_api.py test-connection` |
| Launch (3 campaigns) | `python3 scripts/amazon_ads_api.py launch --asin X --title Y ...` |
| Pull report | `python3 scripts/amazon_ads_api.py report --days 7` |
| CSV fallback (no API) | `python3 scripts/amazon_ads_api.py bulk-export ...` |

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `missing env vars: ADS_API_*` | `.env` not filled | Fill in Stage 1 + 3 values |
| `token refresh failed: 400 invalid_grant` | refresh_token revoked | Re-run `ads_oauth_helper.py` |
| `401 Unauthorized` on API call | Wrong region or profileId | Check `ADS_API_REGION` matches profile's countryCode region |
| `403 Forbidden` | API access not approved yet | Wait for Amazon approval email |
| Rate limit hit | Too many writes/sec | Add `time.sleep(1)` between bulk operations |
| Campaign created but no ads showing | First-time review by Amazon | Wait 24-72h after launch |

---

## What this stack does NOT do (yet)

- **Sponsored Brands** — KDP profiles can't access SB API, web console only.
- **Sponsored Display** — supported by API but launch flow not wired here.
- **Bid optimization loop** — performance-analyst agent reads the report; iteration logic in `.claude/skills/ads-manager/SKILL.md` is documented but not yet wired into automated PUT calls.
- **Bulk negative harvesting from search-term reports** — TODO.

These are easy follow-ups once the basic launch flow proves stable for a few books.
