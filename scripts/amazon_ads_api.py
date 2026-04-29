#!/usr/bin/env python3
"""Amazon Ads API client for KDP OS — Sponsored Products v3.

Capabilities:
  test-connection           — verify creds + list profiles
  list-profiles             — GET /v2/profiles
  launch                    — create 3-campaign launch (auto + exact + phrase)
                              for one book; writes amazon_campaign_id back to DB
  bulk-export               — generate CSV (legacy fallback when no creds)
  report                    — request perf report, poll, dump rows to DB

OAuth: refresh_token (long-lived) → access_token (60 min TTL).
       Use ads_oauth_helper.py once to capture refresh_token.

Endpoints (v3 unless noted):
  POST /v2/profiles                     list ad accounts
  POST /sp/campaigns                    Content-Type: application/vnd.spCampaign.v3+json
  POST /sp/adGroups                     Content-Type: application/vnd.spAdGroup.v3+json
  POST /sp/productAds                   Content-Type: application/vnd.spProductAd.v3+json
  POST /sp/keywords                     Content-Type: application/vnd.spKeyword.v3+json
  POST /sp/negativeKeywords             Content-Type: application/vnd.spNegativeKeyword.v3+json
  POST /reporting/reports               request async report
  GET  /reporting/reports/{reportId}    poll status
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from env_loader import env  # noqa: E402

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

REGION_ENDPOINTS = {
    "NA": "https://advertising-api.amazon.com",
    "EU": "https://advertising-api-eu.amazon.com",
    "FE": "https://advertising-api-fe.amazon.com",
}

BULK_HEADERS = [
    "Product", "Entity", "Operation", "Campaign Id", "Ad Group Id", "Portfolio Id",
    "Ad Id", "Keyword Id", "Product Targeting Id", "Campaign Name", "Ad Group Name",
    "Start Date", "End Date", "Targeting Type", "State", "Daily Budget", "SKU", "ASIN",
    "Ad Group Default Bid", "Bid", "Keyword Text", "Match Type", "Bidding Strategy",
    "Placement", "Percentage", "Product Targeting Expression",
]

DEFAULT_NEGATIVES = ["free", "download", "pdf", "kindle"]


# ────────────────────────────────────────────────────────────────────────────
# Auth + low-level HTTP
# ────────────────────────────────────────────────────────────────────────────

class AdsClient:
    """Thin wrapper that auto-refreshes the access token + injects Ads headers."""

    def __init__(self) -> None:
        if requests is None:
            raise RuntimeError("requests not installed — run: pip install -r requirements.txt")
        self.client_id = env("ADS_API_CLIENT_ID")
        self.client_secret = env("ADS_API_CLIENT_SECRET")
        self.refresh_token = env("ADS_API_REFRESH_TOKEN")
        self.profile_id = env("ADS_API_PROFILE_ID")
        region = env("ADS_API_REGION", "NA") or "NA"
        self.endpoint = REGION_ENDPOINTS.get(region.upper())
        if not self.endpoint:
            raise RuntimeError(f"unknown ADS_API_REGION={region!r} — must be NA/EU/FE")
        self._access_token: str | None = None
        self._access_expires: float = 0.0

    def _missing(self) -> list[str]:
        missing = []
        for k in ("ADS_API_CLIENT_ID", "ADS_API_CLIENT_SECRET", "ADS_API_REFRESH_TOKEN"):
            if not env(k):
                missing.append(k)
        return missing

    def access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_expires - 60:
            return self._access_token
        missing = self._missing()
        if missing:
            raise RuntimeError(f"missing env vars: {', '.join(missing)} — see .env")
        resp = requests.post(
            LWA_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"token refresh failed: {resp.status_code} {resp.text}")
        data = resp.json()
        self._access_token = data["access_token"]
        self._access_expires = now + int(data.get("expires_in", 3600))
        return self._access_token

    def _headers(self, content_type: str | None = None, require_profile: bool = True) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.access_token()}",
            "Amazon-Advertising-API-ClientId": self.client_id or "",
        }
        if require_profile:
            if not self.profile_id:
                raise RuntimeError("ADS_API_PROFILE_ID not set — run `list-profiles` first")
            h["Amazon-Advertising-API-Scope"] = self.profile_id
        if content_type:
            h["Content-Type"] = content_type
            h["Accept"] = content_type
        return h

    def request(self, method: str, path: str, *, json_body=None, content_type=None,
                require_profile=True, params=None) -> requests.Response:
        url = path if path.startswith("http") else f"{self.endpoint}{path}"
        resp = requests.request(
            method, url,
            headers=self._headers(content_type=content_type, require_profile=require_profile),
            json=json_body, params=params, timeout=60,
        )
        return resp

    # ---- High-level helpers ----

    def list_profiles(self) -> list[dict]:
        r = self.request("GET", "/v2/profiles", require_profile=False)
        r.raise_for_status()
        return r.json()

    def create_campaign(self, name: str, daily_budget: float, targeting_type: str,
                        start_date: str, dynamic_bidding: dict | None = None) -> dict:
        body = {
            "campaigns": [{
                "name": name,
                "targetingType": targeting_type,  # AUTO | MANUAL
                "state": "ENABLED",
                "dynamicBidding": dynamic_bidding or {"strategy": "LEGACY_FOR_SALES"},
                "budget": {"budgetType": "DAILY", "budget": round(daily_budget, 2)},
                "startDate": start_date,
            }]
        }
        r = self.request("POST", "/sp/campaigns",
                         json_body=body,
                         content_type="application/vnd.spCampaign.v3+json")
        r.raise_for_status()
        return r.json()

    def create_ad_group(self, campaign_id: str, name: str, default_bid: float) -> dict:
        body = {
            "adGroups": [{
                "name": name,
                "campaignId": campaign_id,
                "defaultBid": round(default_bid, 2),
                "state": "ENABLED",
            }]
        }
        r = self.request("POST", "/sp/adGroups",
                         json_body=body,
                         content_type="application/vnd.spAdGroup.v3+json")
        r.raise_for_status()
        return r.json()

    def create_product_ad(self, campaign_id: str, ad_group_id: str, asin: str) -> dict:
        body = {
            "productAds": [{
                "campaignId": campaign_id,
                "adGroupId": ad_group_id,
                "asin": asin,
                "state": "ENABLED",
            }]
        }
        r = self.request("POST", "/sp/productAds",
                         json_body=body,
                         content_type="application/vnd.spProductAd.v3+json")
        r.raise_for_status()
        return r.json()

    def create_keywords(self, campaign_id: str, ad_group_id: str, keywords: list[str],
                        match_type: str, bid: float) -> dict:
        body = {
            "keywords": [{
                "campaignId": campaign_id,
                "adGroupId": ad_group_id,
                "keywordText": kw,
                "matchType": match_type.upper(),  # EXACT | PHRASE | BROAD
                "state": "ENABLED",
                "bid": round(bid, 2),
            } for kw in keywords]
        }
        r = self.request("POST", "/sp/keywords",
                         json_body=body,
                         content_type="application/vnd.spKeyword.v3+json")
        r.raise_for_status()
        return r.json()

    def create_negative_keywords(self, campaign_id: str, ad_group_id: str,
                                 keywords: list[str], match_type: str = "NEGATIVE_EXACT") -> dict:
        body = {
            "negativeKeywords": [{
                "campaignId": campaign_id,
                "adGroupId": ad_group_id,
                "keywordText": kw,
                "matchType": match_type,  # NEGATIVE_EXACT | NEGATIVE_PHRASE
                "state": "ENABLED",
            } for kw in keywords]
        }
        r = self.request("POST", "/sp/negativeKeywords",
                         json_body=body,
                         content_type="application/vnd.spNegativeKeyword.v3+json")
        r.raise_for_status()
        return r.json()

    def update_campaign_state(self, campaign_id, state: str) -> dict:
        """Pause / resume / archive an existing campaign. Amazon expects campaignId as string."""
        body = {"campaigns": [{"campaignId": str(campaign_id), "state": state.upper()}]}
        r = self.request("PUT", "/sp/campaigns",
                         json_body=body,
                         content_type="application/vnd.spCampaign.v3+json")
        r.raise_for_status()
        return r.json()

    def update_campaign_budget(self, campaign_id, daily_budget: float) -> dict:
        """Update daily budget. Amazon expects campaignId as string."""
        body = {"campaigns": [{
            "campaignId": str(campaign_id),
            "budget": {"budget": round(daily_budget, 2), "budgetType": "DAILY"},
        }]}
        r = self.request("PUT", "/sp/campaigns",
                         json_body=body,
                         content_type="application/vnd.spCampaign.v3+json")
        r.raise_for_status()
        return r.json()

    def list_campaigns(self, states: list[str] | None = None, asin_filter: str | None = None) -> list[dict]:
        """List SP campaigns, optionally filtered by state or by which ASIN they target."""
        body = {"stateFilter": {"include": states or ["ENABLED","PAUSED","ARCHIVED"]}, "maxResults": 100}
        r = self.request("POST", "/sp/campaigns/list",
                         json_body=body,
                         content_type="application/vnd.spCampaign.v3+json")
        r.raise_for_status()
        camps = r.json().get("campaigns", [])
        if not asin_filter:
            return camps
        # Filter to campaigns whose productAds include the given ASIN
        out = []
        for camp in camps:
            cid = camp["campaignId"]
            pa = self.request("POST", "/sp/productAds/list",
                              json_body={"campaignIdFilter": {"include": [cid]}, "maxResults": 50},
                              content_type="application/vnd.spProductAd.v3+json")
            if pa.status_code == 200:
                if asin_filter in {a.get("asin") for a in pa.json().get("productAds", [])}:
                    out.append(camp)
        return out

    def request_report(self, start_date: str, end_date: str, ad_product: str = "SPONSORED_PRODUCTS",
                       group_by: str | None = None,
                       metrics: list[str] | None = None) -> str:
        """Request an async report. Returns reportId."""
        body = {
            "name": f"kdp-os-{ad_product.lower()}-{start_date}-{end_date}",
            "startDate": start_date,
            "endDate": end_date,
            "configuration": {
                "adProduct": ad_product,
                "groupBy": [group_by or "campaign"],
                "columns": metrics or [
                    "campaignName", "campaignId", "impressions", "clicks", "cost",
                    "purchases7d", "sales7d", "acosClicks14d",
                ],
                "reportTypeId": "spCampaigns",
                "timeUnit": "SUMMARY",
                "format": "GZIP_JSON",
            },
        }
        r = self.request("POST", "/reporting/reports",
                         json_body=body,
                         content_type="application/vnd.createasyncreportrequest.v3+json")
        r.raise_for_status()
        return r.json()["reportId"]

    def poll_report(self, report_id: str, max_wait_s: int = 300) -> dict:
        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            r = self.request("GET", f"/reporting/reports/{report_id}",
                             content_type="application/vnd.createasyncreportrequest.v3+json")
            r.raise_for_status()
            data = r.json()
            status = data.get("status")
            if status == "COMPLETED":
                return data
            if status == "FAILED":
                raise RuntimeError(f"report failed: {data}")
            time.sleep(15)
        raise TimeoutError(f"report {report_id} not ready after {max_wait_s}s")


# ────────────────────────────────────────────────────────────────────────────
# Bulk CSV (legacy / no-creds fallback)
# ────────────────────────────────────────────────────────────────────────────

def build_launch_plan(asin: str, title: str, keywords_tier1: list[str], keywords_tier2: list[str],
                      default_bid: float, daily_budget_auto: float = 5.0,
                      daily_budget_exact: float = 10.0, daily_budget_phrase: float = 5.0) -> list[dict]:
    plan: list[dict] = []
    campaigns = [
        ("Launch Auto — " + title[:40], "auto", daily_budget_auto, default_bid * 0.9),
        ("Launch Exact — " + title[:40], "manual", daily_budget_exact, default_bid),
        ("Launch Phrase — " + title[:40], "manual", daily_budget_phrase, default_bid * 0.9),
    ]
    for camp_name, camp_type, budget, bid in campaigns:
        plan.append({"Product": "Sponsored Products", "Entity": "Campaign", "Operation": "Create",
                     "Campaign Name": camp_name, "Targeting Type": "Auto" if camp_type == "auto" else "Manual",
                     "State": "enabled", "Daily Budget": f"{budget:.2f}",
                     "Bidding Strategy": "Dynamic bids - down only"})
        plan.append({"Product": "Sponsored Products", "Entity": "Ad Group", "Operation": "Create",
                     "Campaign Name": camp_name, "Ad Group Name": "AG1", "State": "enabled",
                     "Ad Group Default Bid": f"{bid:.2f}"})
        plan.append({"Product": "Sponsored Products", "Entity": "Product Ad", "Operation": "Create",
                     "Campaign Name": camp_name, "Ad Group Name": "AG1", "State": "enabled", "ASIN": asin})
        if camp_type == "auto":
            continue
        kws = keywords_tier1 if "Exact" in camp_name else keywords_tier2
        match = "exact" if "Exact" in camp_name else "phrase"
        for kw in kws:
            plan.append({"Product": "Sponsored Products", "Entity": "Keyword", "Operation": "Create",
                         "Campaign Name": camp_name, "Ad Group Name": "AG1", "State": "enabled",
                         "Bid": f"{bid:.2f}", "Keyword Text": kw, "Match Type": match})
    for neg in DEFAULT_NEGATIVES:
        for camp_name, *_ in campaigns:
            plan.append({"Product": "Sponsored Products", "Entity": "Campaign Negative Keyword",
                         "Operation": "Create", "Campaign Name": camp_name, "State": "enabled",
                         "Keyword Text": neg, "Match Type": "negativeExact"})
    return plan


def write_bulk_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=BULK_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ────────────────────────────────────────────────────────────────────────────
# Launch flow (API path)
# ────────────────────────────────────────────────────────────────────────────

def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def launch_book(client: AdsClient, asin: str, title: str,
                keywords_exact: list[str], keywords_phrase: list[str],
                default_bid: float,
                budget_auto: float = 5.0, budget_exact: float = 10.0, budget_phrase: float = 5.0,
                negatives: list[str] | None = None) -> dict:
    """Create 3 campaigns end-to-end via API. Returns dict of created entities."""
    if negatives is None:
        negatives = DEFAULT_NEGATIVES
    start = _today()
    short = title[:40]

    def _extract_id(resp: dict, key: str) -> str:
        # v3 returns {success: [{...,id}], error: [...]} per entity type
        success = resp.get("campaigns", resp.get("adGroups", resp.get("productAds", resp.get("keywords", resp.get("negativeKeywords", {}))))) if isinstance(resp, dict) else None
        # safer: dig success list
        for k in ("campaigns", "adGroups", "productAds", "keywords", "negativeKeywords"):
            block = resp.get(k)
            if isinstance(block, dict):
                ok = block.get("success") or []
                if ok:
                    item = ok[0]
                    return item.get(key) or item.get(key + "Id") or item.get("id") or ""
            elif isinstance(block, list) and block:
                return block[0].get(key) or block[0].get("id") or ""
        # surface errors
        raise RuntimeError(f"could not extract {key} from response: {json.dumps(resp)[:500]}")

    out: dict[str, Any] = {"campaigns": []}

    plan = [
        {"label": "auto", "name": f"Launch Auto — {short}", "type": "AUTO",
         "budget": budget_auto, "bid": round(default_bid * 0.9, 2)},
        {"label": "exact", "name": f"Launch Exact — {short}", "type": "MANUAL",
         "budget": budget_exact, "bid": round(default_bid, 2),
         "keywords": keywords_exact, "match": "EXACT"},
        {"label": "phrase", "name": f"Launch Phrase — {short}", "type": "MANUAL",
         "budget": budget_phrase, "bid": round(default_bid * 0.9, 2),
         "keywords": keywords_phrase, "match": "PHRASE"},
    ]

    for c in plan:
        camp_resp = client.create_campaign(c["name"], c["budget"], c["type"], start)
        camp_id = _extract_id(camp_resp, "campaignId")
        ag_resp = client.create_ad_group(camp_id, "AG1", c["bid"])
        ag_id = _extract_id(ag_resp, "adGroupId")
        pa_resp = client.create_product_ad(camp_id, ag_id, asin)
        pa_id = _extract_id(pa_resp, "adId")
        kw_ids: list[str] = []
        if c["type"] == "MANUAL" and c.get("keywords"):
            kw_resp = client.create_keywords(camp_id, ag_id, c["keywords"], c["match"], c["bid"])
            block = kw_resp.get("keywords", {})
            if isinstance(block, dict):
                kw_ids = [item.get("keywordId") or item.get("id") for item in block.get("success", [])]
        if negatives:
            try:
                client.create_negative_keywords(camp_id, ag_id, negatives, "NEGATIVE_EXACT")
            except requests.HTTPError as e:
                # don't fail entire launch on negatives
                print(f"  ⚠ failed to add negatives: {e}", file=sys.stderr)
        out["campaigns"].append({
            "label": c["label"], "name": c["name"], "campaignId": camp_id,
            "adGroupId": ag_id, "productAdId": pa_id, "keywordIds": kw_ids,
        })
    return out


# ────────────────────────────────────────────────────────────────────────────
# CLI commands
# ────────────────────────────────────────────────────────────────────────────

def cmd_test_connection(args) -> int:
    try:
        client = AdsClient()
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    missing = client._missing()
    if missing:
        print(f"❌ missing env vars: {', '.join(missing)}", file=sys.stderr)
        print("   Run: python3 scripts/ads_oauth_helper.py", file=sys.stderr)
        return 1
    try:
        token = client.access_token()
    except Exception as e:
        print(f"❌ token refresh failed: {e}", file=sys.stderr)
        return 1
    print(f"✓ access_token refreshed (len={len(token)})")
    if not client.profile_id:
        print("⚠ ADS_API_PROFILE_ID not set — run: list-profiles")
        return 0
    try:
        profiles = client.list_profiles()
        match = next((p for p in profiles if str(p.get("profileId")) == str(client.profile_id)), None)
        if match:
            print(f"✓ profile {client.profile_id} → {match.get('countryCode')} {match.get('accountInfo',{}).get('type')}")
        else:
            print(f"⚠ profile {client.profile_id} not found in your account list")
    except Exception as e:
        print(f"❌ profile list failed: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_list_profiles(args) -> int:
    client = AdsClient()
    profiles = client.list_profiles()
    print(json.dumps(profiles, indent=2))
    print()
    print("Set ADS_API_PROFILE_ID in .env to one of the profileId values above.")
    print("For US KDP ads, look for countryCode=US.")
    return 0


def cmd_launch(args) -> int:
    client = AdsClient()

    keywords_exact = json.loads(args.keywords_exact) if args.keywords_exact else []
    keywords_phrase = json.loads(args.keywords_phrase) if args.keywords_phrase else []
    if not keywords_exact:
        print("❌ --keywords-exact required (JSON array of 5+ exact-match keywords)", file=sys.stderr)
        return 1

    if args.dry_run:
        plan = build_launch_plan(args.asin, args.title, keywords_exact, keywords_phrase, args.bid,
                                 args.budget_auto, args.budget_exact, args.budget_phrase)
        print(f"DRY RUN — would create {len(plan)} bulk-sheet rows for ASIN {args.asin}")
        for row in plan[:6]:
            print(f"  {row.get('Entity')}: {row.get('Campaign Name','')} {row.get('Keyword Text','')}".strip())
        print(f"  ... +{max(0, len(plan)-6)} more rows")
        return 0

    print(f"🚀 Launching ads for ASIN {args.asin} ({args.title[:40]})...")
    out = launch_book(
        client, args.asin, args.title, keywords_exact, keywords_phrase,
        default_bid=args.bid,
        budget_auto=args.budget_auto, budget_exact=args.budget_exact, budget_phrase=args.budget_phrase,
    )

    print()
    print("=" * 60)
    print("✅ LAUNCH COMPLETE")
    print("=" * 60)
    for c in out["campaigns"]:
        print(f"  [{c['label']:6}] campaign={c['campaignId']} adGroup={c['adGroupId']} ad={c['productAdId']} keywords={len(c['keywordIds'])}")

    if args.book_id:
        # write back to DB
        try:
            from db import db_create  # type: ignore
        except Exception:
            db_create = None
        for c in out["campaigns"]:
            payload = {
                "book_id": args.book_id,
                "campaign_name": c["name"],
                "campaign_type": c["label"],
                "amazon_campaign_id": c["campaignId"],
                "budget_daily_usd": (args.budget_auto if c["label"] == "auto"
                                     else args.budget_exact if c["label"] == "exact"
                                     else args.budget_phrase),
                "default_bid_usd": args.bid,
                "status": "ACTIVE",
                "launched_at": _today(),
            }
            cmd = ["python3", str(HERE / "db.py"), "ad_campaigns", "create", json.dumps(payload)]
            import subprocess
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                print(f"  ⚠ DB write failed for {c['label']}: {e.stderr}", file=sys.stderr)
        print(f"✓ wrote {len(out['campaigns'])} ad_campaigns rows for book_id={args.book_id}")

    return 0


def cmd_bulk_export(args) -> int:
    keywords_tier1 = json.loads(args.keywords_exact) if args.keywords_exact else []
    keywords_tier2 = json.loads(args.keywords_phrase) if args.keywords_phrase else []
    plan = build_launch_plan(
        asin=args.asin, title=args.title,
        keywords_tier1=keywords_tier1, keywords_tier2=keywords_tier2,
        default_bid=args.bid, daily_budget_auto=args.budget_auto,
        daily_budget_exact=args.budget_exact, daily_budget_phrase=args.budget_phrase,
    )
    out = Path(args.out)
    write_bulk_csv(plan, out)
    print(f"✅ Wrote {len(plan)} bulk-sheet rows to {out}")
    print("   Upload at advertising.amazon.com → Bulk operations")
    return 0


def cmd_report(args) -> int:
    if args.days > 31:
        print(f"ERROR: Amazon SP reports max 31 days/request. Got --days {args.days}.", file=sys.stderr)
        print("       Use --start-date / --end-date for older data, or run multiple 31-day chunks.", file=sys.stderr)
        return 2
    client = AdsClient()
    if args.start_date and args.end_date:
        start, end = args.start_date, args.end_date
    else:
        end = _today()
        start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - args.days * 86400))
    print(f"Requesting Sponsored Products campaigns report {start} → {end}...")
    report_id = client.request_report(start, end)
    print(f"  reportId={report_id} — polling...")
    data = client.poll_report(report_id, max_wait_s=600)
    url = data.get("url")
    if not url:
        print(f"⚠ report COMPLETED but no download URL: {data}", file=sys.stderr)
        return 1
    import gzip
    raw = requests.get(url, timeout=60).content
    rows = json.loads(gzip.decompress(raw).decode())
    print(f"✓ {len(rows)} rows")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2))
        print(f"  saved to {args.out}")
    if args.write_db and rows:
        import subprocess
        wrote = 0
        for r in rows:
            cost = float(r.get("cost") or 0)
            sales = float(r.get("sales7d") or 0)
            clicks = int(r.get("clicks") or 0)
            impressions = int(r.get("impressions") or 0)
            orders = int(r.get("purchases7d") or 0)
            acos = float(r.get("acosClicks14d") or 0)
            ctr = (clicks / impressions * 100) if impressions else 0
            cvr = (orders / clicks * 100) if clicks else 0
            payload = {
                "book_id": 0,
                "campaign_id": 0,
                "amazon_campaign_id": str(r.get("campaignId", "")),
                "campaign_name": r.get("campaignName", ""),
                "date": end,
                "impressions": impressions,
                "clicks": clicks,
                "spend_usd": cost,
                "sales_usd": sales,
                "orders": orders,
                "acos_pct": acos,
                "ctr_pct": round(ctr, 2),
                "cvr_pct": round(cvr, 2),
            }
            cmd = ["python3", str(HERE / "db.py"), "ad_performance", "create", json.dumps(payload)]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                wrote += 1
            except subprocess.CalledProcessError as e:
                print(f"  ⚠ DB write failed: {e.stderr}", file=sys.stderr)
        print(f"✓ wrote {wrote}/{len(rows)} rows into ad_performance")
    elif not args.out:
        for r in rows[:10]:
            print(f"  {r}")
    return 0


def cmd_pause(args) -> int:
    client = AdsClient()
    res = client.update_campaign_state(args.campaign_id, "PAUSED")
    errors = res.get("campaigns", {}).get("error", [])
    if errors:
        print(f"⚠ errors: {errors}", file=sys.stderr)
        return 1
    print(f"✓ paused campaign {args.campaign_id}")
    return 0


def cmd_resume(args) -> int:
    client = AdsClient()
    res = client.update_campaign_state(args.campaign_id, "ENABLED")
    if res.get("campaigns", {}).get("error"):
        print(f"⚠ {res['campaigns']['error']}", file=sys.stderr)
        return 1
    print(f"✓ resumed campaign {args.campaign_id}")
    return 0


def cmd_update_budget(args) -> int:
    client = AdsClient()
    res = client.update_campaign_budget(args.campaign_id, args.budget)
    if res.get("campaigns", {}).get("error"):
        print(f"⚠ {res['campaigns']['error']}", file=sys.stderr)
        return 1
    print(f"✓ updated campaign {args.campaign_id} budget → ${args.budget}/day")
    return 0


def cmd_list_campaigns(args) -> int:
    client = AdsClient()
    states = args.states.split(",") if args.states else None
    camps = client.list_campaigns(states=states, asin_filter=args.asin)
    if args.json:
        print(json.dumps(camps, indent=2, default=str))
        return 0
    print(f"{'STATE':<9} {'BUDGET':>8}  {'ID':<18} NAME")
    for c in camps:
        print(f"{c.get('state','?'):<9} ${c.get('budget',{}).get('budget','?'):>6}/d  {c.get('campaignId','?'):<18} {c.get('name','')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Amazon Ads API client for KDP")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("test-connection", help="verify credentials + token refresh")

    sub.add_parser("list-profiles", help="GET /v2/profiles")

    lcamp = sub.add_parser("list-campaigns", help="list SP campaigns (with optional ASIN filter)")
    lcamp.add_argument("--states", help="comma-separated: ENABLED,PAUSED,ARCHIVED (default: all)")
    lcamp.add_argument("--asin", help="only show campaigns whose productAds target this ASIN")
    lcamp.add_argument("--json", action="store_true", help="output JSON instead of table")

    p = sub.add_parser("pause", help="pause an existing SP campaign")
    p.add_argument("--campaign-id", dest="campaign_id", required=True)

    rs = sub.add_parser("resume", help="resume a paused SP campaign")
    rs.add_argument("--campaign-id", dest="campaign_id", required=True)

    ub = sub.add_parser("update-budget", help="change daily budget of an existing SP campaign")
    ub.add_argument("--campaign-id", dest="campaign_id", required=True)
    ub.add_argument("--budget", type=float, required=True, help="new daily budget in USD")

    lc = sub.add_parser("launch", help="create 3-campaign launch via API")
    lc.add_argument("--asin", required=True)
    lc.add_argument("--title", required=True)
    lc.add_argument("--bid", type=float, default=0.10)
    lc.add_argument("--budget-auto", type=float, default=5.0)
    lc.add_argument("--budget-exact", type=float, default=10.0)
    lc.add_argument("--budget-phrase", type=float, default=5.0)
    lc.add_argument("--keywords-exact", help="JSON array of exact-match keywords", required=True)
    lc.add_argument("--keywords-phrase", help="JSON array of phrase-match keywords")
    lc.add_argument("--book-id", type=int, help="if set, write ad_campaigns rows back to DB")
    lc.add_argument("--dry-run", action="store_true", help="preview rows without API calls")

    b = sub.add_parser("bulk-export", help="generate bulk CSV (legacy / no-creds)")
    b.add_argument("--asin", required=True)
    b.add_argument("--title", required=True)
    b.add_argument("--bid", type=float, default=0.10)
    b.add_argument("--budget-auto", type=float, default=5.0)
    b.add_argument("--budget-exact", type=float, default=10.0)
    b.add_argument("--budget-phrase", type=float, default=5.0)
    b.add_argument("--keywords-exact", help="JSON array")
    b.add_argument("--keywords-phrase", help="JSON array")
    b.add_argument("--out", required=True)

    r = sub.add_parser("report", help="pull SP campaigns report")
    r.add_argument("--days", type=int, default=7, help="last N days (max 31, Amazon limit)")
    r.add_argument("--start-date", dest="start_date", help="YYYY-MM-DD (overrides --days)")
    r.add_argument("--end-date", dest="end_date", help="YYYY-MM-DD (overrides --days)")
    r.add_argument("--out", help="dump rows to JSON file")
    r.add_argument("--write-db", action="store_true", help="insert rows into ad_performance table")

    args = parser.parse_args()
    cmd_map = {
        "test-connection": cmd_test_connection,
        "list-profiles": cmd_list_profiles,
        "list-campaigns": cmd_list_campaigns,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "update-budget": cmd_update_budget,
        "launch": cmd_launch,
        "bulk-export": cmd_bulk_export,
        "report": cmd_report,
    }
    return cmd_map[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
