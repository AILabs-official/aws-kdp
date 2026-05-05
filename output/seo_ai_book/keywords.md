# Amazon Ads Keyword Set — SEO & AI book

**Book:** SEO & AI: How to Get Your Website to Top 1 in 3 Months — Vincent Do & Tony Trieu
**ASIN (Kindle):** B0DDZP6ZSJ  |  **Paperback:** B0DPTF4PB5
**List:** $9.99 Kindle / ~$12.97 paperback  |  **KU:** Yes  |  **Pages:** 204
**BSR:** #4,188,685 in Kindle Store (#279 Search Engines, #643 Online Advertising, #683 Online Internet Searching)
**Reviews:** 0 — launch-phase book; aim review velocity, not profit

## Bid math (kdp_config)
- Kindle royalty/sale (70% band, $9.99 - $0.06 delivery): **$6.95**
- Break-even ACOS = 100%
- Launch target ACOS = 100-150% (lose-money to seed BSR + reviews)
- Mature target ACOS = 35-50%
- **Max launch CPC** @ ACOS 150%, CVR 6% = **$0.63**
- **Max mature CPC** @ ACOS 50%, CVR 6% = **$0.21**

> Anh dùng cuốn này tốc độ cao trong 60 ngày đầu để build review, sau đó bid xuống.

---

## Campaign 1 — EXACT (Tier 1 high-intent)
**Strategy:** Manual targeting, exact match, "Dynamic bids - down only".
**Default bid:** **$0.75** | **Budget:** $10/d | **Placement boost:** Top of search +50%

### Core SEO+AI (premium intent — match book promise)
- seo with ai
- seo and ai
- ai for seo
- ai seo guide
- ai seo book
- seo using ai
- ai search engine optimization
- chatgpt seo
- seo chatgpt
- chatgpt for seo
- seo ai 2024
- seo ai 2025
- modern seo
- seo 2025

### SEO Book (broader buyer intent)
- seo book
- seo guide
- seo guide book
- seo for beginners
- seo for beginners book
- seo for entrepreneurs
- seo for small business
- search engine optimization book
- search engine optimization guide
- step by step seo
- seo step by step
- advanced seo
- seo strategy book

### AI Marketing (cross-niche)
- ai marketing book
- ai digital marketing
- chatgpt for marketing
- chatgpt for business
- ai for marketing
- ai marketing guide

### Outcome-driven (high-buying-intent long-tail)
- rank google ai
- google ranking guide
- increase website traffic
- get website to top of google
- website seo guide
- website ranking book

---

## Campaign 2 — PHRASE / BROAD (Tier 2 discovery)
**Strategy:** Manual targeting, phrase + broad match. **Bid:** **$0.50** | **Budget:** $7/d

### Phrase
- "seo ai"
- "ai seo"
- "seo book"
- "chatgpt marketing"
- "seo for beginners"
- "ai marketing"
- "search engine optimization"
- "google ranking"
- "seo strategies"
- "blog seo"
- "ecommerce seo"
- "small business seo"
- "online marketing book"
- "digital marketing book"
- "internet marketing"

### Broad
- seo ai
- ai chatgpt seo
- seo google ranking
- learn seo
- seo techniques
- seo basics
- ai marketing tools
- chatgpt business
- digital marketing 2025
- online business book
- make money online seo

---

## Campaign 3 — AUTO + Product Targeting
**Strategy:** Sponsored Products Auto, all 4 close/loose/substitute/complement match. **Bid:** **$0.45** | **Budget:** $5/d

### + Product Targeting (competitor ASINs — separate manual ad group)
**Bid:** **$0.65** (premium for competitor real estate)

| ASIN | Title | Why |
|---|---|---|
| B019URI064 | A Complete Beginner's Guide to SEO | Direct beginner overlap |
| B0C3XRY817 | Advanced SEO (2025 Edition) | Same year + advanced overlap |
| B00ELRTNAQ | Step-By-Step SEO (Davidson) | Same "step-by-step" angle |
| B0GT6P3F8H | Amazon KDP SEO | KDP-author cross-buy |
| B0DM8XVXNZ | Beginner-to-Expert SEO Journey 2024 | Direct competitor 2024 |
| B00T8XN29Q | Kindle SEO (Carlin) | Author cross-buy |
| B01N6QL10U | SEO Step By Step Beginners (De Vries) | Title overlap |
| B0CLD4RTNC | 30-Minute SEO | Same outcome promise |

> Sau 30 ngày, pull search-term report → ASIN nào convert thì pull lên Manual ad group bid $0.85, ASIN dead → negative.

---

## Negative Keywords (BẮT BUỘC apply ở cả 3 campaigns)

Tránh đốt budget vào traffic không mua sách.

```
free
free seo
seo course
udemy
youtube
seo software
seo tool
seo tools
seo agency
seo service
seo services
seo company
seo audit
seo checker
seo analyzer
backlink
backlinks
keyword tool
google analytics
ahrefs
semrush
moz
shopify seo
wordpress seo
yoast
```

## Negative ASINs

```
B0DDZP6ZSJ   (own ASIN — never bid on self)
B0DPTF4PB5   (own paperback variant)
```

---

## Launch checklist

1. **Pause** campaign "Launch Auto - AI Publishing Profits" (CTR 0.03% tuần qua = đốt impr).
2. **Tạo 3 campaigns** ở trên với bid + budget trong file này.
3. **Chạy 14 ngày** rồi pull report → cắt keyword nào ACOS > 250% sau ≥ 10 clicks.
4. **Mục tiêu 60 ngày:** 5-10 reviews + BSR < 500K → bid sẽ xuống được.
5. **Long-term:** sau 100 reviews → bid drop 30%, target ACOS 50%.

## CLI launch (khi anh đã quyết)

Edit `scripts/amazon_ads_api.py` launch payload với các keyword trên rồi:

```bash
python3 scripts/amazon_ads_api.py launch \
  --asin B0DDZP6ZSJ \
  --title "SEO and AI" \
  --kw-tier1-file output/seo_ai_book/kw_tier1.txt \
  --kw-tier2-file output/seo_ai_book/kw_tier2.txt \
  --bid 0.75 \
  --budget-auto 5 --budget-exact 10 --budget-phrase 7
```

(Em sẽ tạo 2 file kw_tier1.txt + kw_tier2.txt nếu anh đồng ý launch.)
