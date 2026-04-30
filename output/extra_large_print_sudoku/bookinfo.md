<!-- BOOKINFO_DATA — pipeline reads the JSON below. Regenerate via:
     python3 scripts/migrate_to_bookinfo.py --apply --force --book extra_large_print_sudoku
     Edits to the markdown body further down do NOT propagate back to this fence. -->
```json
{
  "theme_key": "extra_large_print_sudoku",
  "title": "Extra Large Print Sudoku Puzzle Book",
  "subtitle": "100 Easy to Hard Puzzles with Giant 30-Point Numbers — One Puzzle Per Page, Solutions Included — Easy-on-the-Eyes Brain Games for Seniors and Low-Vision Adults",
  "author": "BrainCraft Publishing",
  "book_type": "sudoku",
  "style": "sudoku",
  "page_size": "8.5x11",
  "audience": "seniors_low_vision",
  "large_print": true,
  "font_size_pt": 30,
  "puzzles_per_page": 1,
  "solutions_section": true,
  "difficulty_distribution": {
    "easy": 35,
    "medium": 40,
    "hard": 25,
    "expert": 0
  },
  "puzzle_count": 100,
  "target_page_count": 110,
  "list_price_usd": 9.99,
  "seed": 2742,
  "niche_id": 27,
  "primary_keyword": "extra large print sudoku puzzle book",
  "secondary_keywords": [
    "extra large print sudoku",
    "large print sudoku for seniors",
    "low vision sudoku",
    "giant print sudoku puzzle book",
    "sudoku large print easy",
    "sudoku for elderly low vision",
    "big number sudoku book"
  ],
  "cover_prompt": "Front cover for an Extra Large Print Sudoku puzzle book. Clean modern minimal design, calm and dignified, age-appropriate for seniors and low-vision adults. Large 9x9 sudoku grid in upper-center with a few giant numbers visible (4, 7, 2). Bold readable sans-serif title at top. Soft warm gradient background (cream-to-soft-blue or warm parchment). High contrast text. NO clutter, NO cartoon characters, NO frames. Professional puzzle-book aesthetic similar to AARP / dover / brainstorm imprints.",
  "differentiator": "24-30pt numerals, 1 puzzle per page, puzzle completion stickers placeholder",
  "front_color_scheme": "green",
  "front_year_text": "2026",
  "front_levels_text": "3 LEVELS",
  "front_audience_tag": "LARGE PRINT FOR ADULTS & SENIORS",
  "back_extra_badge": "GIFT EDITION",
  "imprint": "BrainCraft Publishing",
  "ip_risk_notes": "Sudoku is generic. Avoid 'Will Shortz', 'Penny Press', 'KAPPA', 'New York Times' style branding.",
  "actual_page_count": 128,
  "recommended_categories_2026": {
    "_book_format": "PAPERBACK (8.5x11, 128p) — uses Amazon Books tree (zgbs/books). NOT a Kindle eBook (puzzle books don't work on Kindle, separate node tree zgbs/digital-text would apply if it did).",
    "_selection_criteria": "All 3 must satisfy: (1) topic match — describe what the book IS (sudoku/logic/puzzle), not who buys it. (2) format match — paperback nodes only. (3) Blue Ocean weakness — top BSR > 20K + royalty < $2K preferred. Audience signals (seniors, large print) belong in subtitle/keywords, NEVER in category selection.",
    "primary": {
      "kdp_path": "Books > Humor & Entertainment > Puzzles & Games > Sudoku",
      "amazon_node_id": "15756641",
      "amazon_url": "https://www.amazon.com/Best-Sellers-Books/zgbs/books/15756641",
      "top_bsr": 44208,
      "top_monthly_royalty_usd": 1143,
      "topic_match": "DIRECT — book IS sudoku.",
      "weakness_assessment": "WEAK_LEADER — top is 'Sassy Woman's Retirement Activity Book' (a multi-puzzle activity book, not pure sudoku); BSR 44K means low absolute sales. Easiest target in puzzle subtree.",
      "rationale": "Tier-1 pick. Lowest royalty bar (~$50-80/day ads gets to top 5)."
    },
    "secondary": {
      "kdp_path": "Books > Humor & Entertainment > Puzzles & Games > Logic & Brain Teasers",
      "amazon_node_id": "4436",
      "amazon_url": "https://www.amazon.com/Best-Sellers-Books/zgbs/books/4436",
      "top_bsr": 8527,
      "top_monthly_royalty_usd": 1698,
      "topic_match": "STRONG — sudoku is a logic puzzle / brain teaser by definition.",
      "weakness_assessment": "MEDIUM_LEADER — top is 'Tricky Logic Puzzles for Adults' (hard logic, different segment). No large-print sudoku at top = uncontested angle.",
      "rationale": "Tier-2 pick. Same Puzzles & Games parent, valid topic, weak large-print presence."
    },
    "tertiary": {
      "kdp_path": "Books > Humor & Entertainment > Puzzles & Games > Puzzles",
      "amazon_node_id": "4439",
      "amazon_url": "https://www.amazon.com/Best-Sellers-Books/zgbs/books/4439",
      "top_bsr": 8527,
      "top_monthly_royalty_usd": 1698,
      "topic_match": "STRONG — sudoku is a puzzle.",
      "weakness_assessment": "MEDIUM_LEADER — same level as Logic & Brain Teasers. Top is 'Tricky Logic Puzzles' (shared bestseller across both leaves).",
      "rationale": "Tier-3 pick. Wider net — captures buyers browsing 'Puzzles' generic, not just sudoku-searchers."
    },
    "rejected_options": {
      "health_fitness_aging": "REJECT — audience match only, NOT topic match. Sudoku is not a health/aging book. Amazon will move category and may flag listing.",
      "self_help_memory_improvement": "REJECT — same audience-only mismatch + top BSR 506 / $22,867 mo royalty (VERY_HARD). Topic mismatch + budget infeasible.",
      "puzzles_games_parent_4402": "REJECT — KDP requires leaf categories, not parents. Top BSR 1368 / $11,291 mo also too competitive.",
      "crossword_puzzles_4416": "REJECT — different topic (word vs number). Top BSR 350 / $67,939 mo (NYT Games dominates).",
      "kindle_sudoku_16232543011": "REJECT — wrong tree. This is the Kindle digital-text node. Our book is paperback only; puzzle books have poor Kindle UX (readers can't pencil in numbers)."
    },
    "post_publish_category_requests": [
      "Books > Humor & Entertainment > Puzzles & Games > Brain Teasers (if exists as separate leaf from Logic & Brain Teasers — file KDP ticket to verify + add)",
      "Books > Crafts, Hobbies & Home > Crafts & Hobbies > Reference (some sudoku books rank here historically)"
    ]
  },
  "kdp_listing": {
    "_intent": "Single source of truth for KDP upload form. Paste fields directly into kdp.amazon.com → Paperback → Add Title.",
    "title": "Extra Large Print Sudoku Puzzle Book",
    "subtitle": "100 Easy to Hard Puzzles with Giant 30-Point Numbers — One Puzzle Per Page, Solutions Included — Easy-on-the-Eyes Brain Games for Seniors and Low-Vision Adults",
    "author": {
      "first_name": "BrainCraft",
      "last_name": "Publishing"
    },
    "imprint": "BrainCraft Publishing",
    "description_html": "<h3>Sudoku You Can Actually See &mdash; Designed for Comfortable Reading</h3>\n<p>If small numbers in standard sudoku books leave you squinting, this <b>Extra Large Print Sudoku Puzzle Book</b> is built for you. Every numeral is printed in <b>oversized 30-point font</b>, with one puzzle per page so the grid never feels cramped. Truly <b>easy on the eyes</b> &mdash; no more eye strain, no more reading glasses on top of magnifiers, no more giving up halfway through.</p>\n<h3>What's Inside</h3>\n<ul>\n<li><b>100 hand-verified puzzles</b> &mdash; every puzzle has a unique solution (no guessing required)</li>\n<li><b>Three skill levels:</b> 35 Easy &middot; 40 Medium &middot; 25 Hard</li>\n<li><b>One puzzle per page</b> &mdash; thick paper, no bleed-through, plenty of writing room</li>\n<li><b>Giant 30-point numbers</b> &mdash; readable without a magnifier, clear under any lighting</li>\n<li><b>Complete solutions section</b> at the back for self-checking</li>\n<li><b>8.5 x 11 inch</b> generous trim &mdash; lays flat on the table or lap</li>\n</ul>\n<h3>Made for Aging Eyes</h3>\n<p>Specifically designed with <b>low-vision adults</b> in mind &mdash; readers managing <b>macular degeneration</b>, <b>glaucoma</b>, <b>cataracts</b>, or simply tired eyes after a long day. The oversized digits, generous white space, and clean uncluttered layout mean the puzzles stay readable in soft lamp light, on the porch, in the car, or beside the hospital bed.</p>\n<h3>A Thoughtful Gift</h3>\n<p>The kind of present that gets used, not shelved. Perfect for <b>Mother's Day, Father's Day, Christmas stockings, birthdays, get-well baskets, retirement parties, and care-package boxes</b>. A daily brain workout that respects your loved one's eyesight &mdash; great for parents, grandparents, mom, dad, grandma, and grandpa.</p>\n<h3>Why This Book Stands Out</h3>\n<p>Most \"large print\" sudoku books still cram four puzzles per page with 14&minus;18 point numbers. This one goes further: <b>true extra-large 30-point digits</b>, generous margins, and a clean uncluttered layout. The way sudoku should be printed when comfort matters more than crowding more puzzles onto a page.</p>\n<h3>Daily Brain Wellness, the Gentle Way</h3>\n<p>Make it part of your morning coffee, your afternoon quiet hour, your bedtime wind-down. Logic puzzles are linked to sharper memory, focus, and calm &mdash; and with comfortable big numbers, you can keep solving without the headache. Scroll up and add a copy to your cart for yourself or someone whose eyes deserve a break.</p>\n<p><i>Sharpen your mind. Relax your eyes. One puzzle at a time.</i></p>",
    "keywords_7": [
      "sudoku gift seniors elderly grandparents",
      "large print sudoku for seniors",
      "low vision sudoku book",
      "giant print sudoku for elderly",
      "easy sudoku large print one per page",
      "big number sudoku puzzle book",
      "brain games sudoku seniors low vision"
    ],
    "categories_paperback_2026": {
      "primary": "Books > Humor & Entertainment > Puzzles & Games > Sudoku",
      "secondary": "Books > Humor & Entertainment > Puzzles & Games > Logic & Brain Teasers",
      "tertiary": "Books > Humor & Entertainment > Puzzles & Games > Puzzles",
      "_full_block_with_node_ids": "see recommended_categories_2026 above for amazon_node_id + URL + weakness analysis"
    },
    "primary_audience": {
      "sexually_explicit": false,
      "low_content_book": true,
      "large_print_book": true,
      "reading_age_min": null,
      "reading_age_max": null,
      "audience_label": "seniors_low_vision"
    },
    "print_options": {
      "ink_paper": "Black & white interior with white paper",
      "trim_size": "8.5 x 11 in",
      "bleed": "No Bleed",
      "cover_finish": "Matte"
    },
    "pricing": {
      "list_price_usd": 9.99,
      "list_price_gbp": 9.49,
      "list_price_eur": 9.99,
      "list_price_cad": 13.49,
      "list_price_aud": 15.98,
      "_note": "Pricing matrix — adjust per current FX. KDP enforces min/max per market."
    },
    "files": {
      "interior_pdf": "interior.pdf",
      "cover_pdf": "cover.pdf",
      "front_artwork": "front_artwork.png"
    },
    "kdp_select_enrollment": true,
    "expanded_distribution": true,
    "barcode_on_cover": false
  }
}
```

<!-- END_BOOKINFO_DATA -->

---

# Extra Large Print Sudoku Puzzle Book

> Single-file source of truth for **extra_large_print_sudoku**. Copy fields below directly into kdp.amazon.com → Paperback → Add Title.

---

## 📌 Title (≤ 200 chars)

```
Extra Large Print Sudoku Puzzle Book
```

## 📌 Subtitle (≤ 200 chars)

```
100 Easy to Hard Puzzles with Giant 30-Point Numbers — One Puzzle Per Page, Solutions Included — Easy-on-the-Eyes Brain Games for Seniors and Low-Vision Adults
```

## ✍️ Author / Imprint

- **First name:** `BrainCraft`
- **Last name:** `Publishing`
- **Imprint:** `BrainCraft Publishing`

## 📝 Description (HTML — paste into KDP description box)

```html
<h3>Sudoku You Can Actually See &mdash; Designed for Comfortable Reading</h3>
<p>If small numbers in standard sudoku books leave you squinting, this <b>Extra Large Print Sudoku Puzzle Book</b> is built for you. Every numeral is printed in <b>oversized 30-point font</b>, with one puzzle per page so the grid never feels cramped. Truly <b>easy on the eyes</b> &mdash; no more eye strain, no more reading glasses on top of magnifiers, no more giving up halfway through.</p>
<h3>What's Inside</h3>
<ul>
<li><b>100 hand-verified puzzles</b> &mdash; every puzzle has a unique solution (no guessing required)</li>
<li><b>Three skill levels:</b> 35 Easy &middot; 40 Medium &middot; 25 Hard</li>
<li><b>One puzzle per page</b> &mdash; thick paper, no bleed-through, plenty of writing room</li>
<li><b>Giant 30-point numbers</b> &mdash; readable without a magnifier, clear under any lighting</li>
<li><b>Complete solutions section</b> at the back for self-checking</li>
<li><b>8.5 x 11 inch</b> generous trim &mdash; lays flat on the table or lap</li>
</ul>
<h3>Made for Aging Eyes</h3>
<p>Specifically designed with <b>low-vision adults</b> in mind &mdash; readers managing <b>macular degeneration</b>, <b>glaucoma</b>, <b>cataracts</b>, or simply tired eyes after a long day. The oversized digits, generous white space, and clean uncluttered layout mean the puzzles stay readable in soft lamp light, on the porch, in the car, or beside the hospital bed.</p>
<h3>A Thoughtful Gift</h3>
<p>The kind of present that gets used, not shelved. Perfect for <b>Mother's Day, Father's Day, Christmas stockings, birthdays, get-well baskets, retirement parties, and care-package boxes</b>. A daily brain workout that respects your loved one's eyesight &mdash; great for parents, grandparents, mom, dad, grandma, and grandpa.</p>
<h3>Why This Book Stands Out</h3>
<p>Most "large print" sudoku books still cram four puzzles per page with 14&minus;18 point numbers. This one goes further: <b>true extra-large 30-point digits</b>, generous margins, and a clean uncluttered layout. The way sudoku should be printed when comfort matters more than crowding more puzzles onto a page.</p>
<h3>Daily Brain Wellness, the Gentle Way</h3>
<p>Make it part of your morning coffee, your afternoon quiet hour, your bedtime wind-down. Logic puzzles are linked to sharper memory, focus, and calm &mdash; and with comfortable big numbers, you can keep solving without the headache. Scroll up and add a copy to your cart for yourself or someone whose eyes deserve a break.</p>
<p><i>Sharpen your mind. Relax your eyes. One puzzle at a time.</i></p>
```

## 🔑 Keywords (7 backend, ≤ 50 chars each)

1. sudoku gift seniors elderly grandparents
2. large print sudoku for seniors
3. low vision sudoku book
4. giant print sudoku for elderly
5. easy sudoku large print one per page
6. big number sudoku puzzle book
7. brain games sudoku seniors low vision

## 🗂️ Categories — Paperback Browse Paths (3 picks)

| Tier | KDP Browse Path | Node ID | Top BSR | Top $/mo |
|---|---|---|---|---|
| 🥇 Primary | `Books > Humor & Entertainment > Puzzles & Games > Sudoku` | `15756641` | 44208 | 1143 |
| 🥈 Secondary | `Books > Humor & Entertainment > Puzzles & Games > Logic & Brain Teasers` | `4436` | 8527 | 1698 |
| 🥉 Tertiary | `Books > Humor & Entertainment > Puzzles & Games > Puzzles` | `4439` | 8527 | 1698 |

> Selection rule: topic match (sudoku/puzzle/logic) > paperback format > Blue Ocean weakness > audience overlap. See `recommended_categories_2026.rejected_options` in the JSON above for what was deliberately excluded.

## 👤 Primary Audience

- **Sexually Explicit:** `No`
- **Low-content book:** `Yes`
- **Large-print book:** `Yes`
- **Reading age:** Leave blank (adult audience)
- **Audience label (internal):** `seniors_low_vision`

## 🖨️ Print Options

- **Ink & paper:** Black & white interior with white paper
- **Trim size:** 8.5 x 11 in
- **Bleed:** No Bleed
- **Cover finish:** Matte

## 💰 Pricing

| Market | Price |
|---|---|
| 🇺🇸 USD | $9.99 |
| 🇬🇧 GBP | £9.49 |
| 🇪🇺 EUR | €9.99 |
| 🇨🇦 CAD | CA$13.49 |
| 🇦🇺 AUD | AU$15.98 |

## 📁 Files to Upload

- **Interior PDF:** `output/extra_large_print_sudoku/interior.pdf`
- **Cover PDF:** `output/extra_large_print_sudoku/cover.pdf`

## ✅ Launch Checklist

- [ ] Enroll in **KDP Select** (Yes)
- [ ] Enable **Expanded Distribution** (Yes)
- [ ] Cover includes barcode? **No (KDP adds one)**
- [ ] After live: request 4th–5th categories via KDP support (see `recommended_categories_2026.post_publish_category_requests` in JSON)
