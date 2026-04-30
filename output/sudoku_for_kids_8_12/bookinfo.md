<!-- BOOKINFO_DATA — pipeline reads the JSON below. Regenerate via:
     python3 scripts/migrate_to_bookinfo.py --apply --force --book sudoku_for_kids_8_12
     Edits to the markdown body further down do NOT propagate back to this fence. -->
```json
{
  "theme_key": "sudoku_for_kids_8_12",
  "title": "Sudoku for Kids Ages 8-12",
  "subtitle": "120 Fun Brain Games for Kids — Easy to Medium Puzzles to Boost Logic, Focus, and Confidence — Includes Sticker Reward Pages and Solutions",
  "author": "BrainCraft Publishing",
  "book_type": "sudoku",
  "style": "sudoku",
  "page_size": "8.5x11",
  "audience": "kids_8_12",
  "large_print": false,
  "puzzles_per_page": 1,
  "solutions_section": true,
  "difficulty_distribution": {
    "easy": 70,
    "medium": 50,
    "hard": 0,
    "expert": 0
  },
  "puzzle_count": 120,
  "target_page_count": 110,
  "list_price_usd": 7.99,
  "seed": 813,
  "niche_id": 6,
  "primary_keyword": "sudoku for kids ages 8-12",
  "secondary_keywords": [
    "sudoku kids",
    "sudoku for children",
    "brain games for kids",
    "sudoku 8-12",
    "kids puzzle book",
    "sudoku for beginners kids",
    "logic puzzles for children"
  ],
  "cover_prompt": "Front cover for a kid-friendly Sudoku puzzle book for ages 8-12. Bright cheerful colors (yellow, blue, green, orange). Cartoon-style smiling pencil and eraser characters next to a sudoku grid. Bold rounded sans-serif title at top. Playful but not babyish — confident tween aesthetic. Background suggests a desk with notebook and crayon. NO realistic faces, NO copyrighted characters, NO frames. Family-friendly Highlights / Scholastic / Brainstorm Press style.",
  "differentiator": "Difficulty ladder narrative (intro 4x4-style aspirational; v1 ships easy 9x9), sticker reward pages between sections",
  "front_color_scheme": "blue",
  "front_year_text": "2026",
  "front_levels_text": "120 PUZZLES",
  "front_audience_tag": "FUN BRAIN GAMES · AGES 8-12",
  "imprint": "BrainCraft Publishing",
  "ip_risk_notes": "Avoid 'Highlights', 'Scholastic', 'Brainstorm', 'Will Shortz' branding cues. Generic kid puzzle imagery only.",
  "ladder_note_v1": "Ladder support (4x4 / 6x6) requires generate_sudoku.py extension; v1 ships 100% 9x9 easy/medium per pipeline note.",
  "actual_page_count": 168,
  "recommended_categories_2026": {
    "_book_format": "PAPERBACK (8.5x11, 168p) — Books tree (zgbs/books). KIDS audience requires Children's Books subtree, not adult Puzzles & Games.",
    "_selection_criteria": "Topic match (sudoku/puzzle/logic for KIDS) + paperback + age-appropriate subtree. Adult Puzzles & Games > Sudoku is also valid because Amazon Sudoku leaf accepts kid editions, but PRIMARY should be Children's tree to anchor in age-appropriate browse.",
    "primary": {
      "kdp_path": "Books > Children's Books > Activities, Crafts & Games > Activity Books > Puzzle Books",
      "amazon_node_id": "3390",
      "amazon_url": "https://www.amazon.com/Best-Sellers-Books/zgbs/books/3390",
      "top_bsr": 2159,
      "top_monthly_royalty_usd": 4009,
      "topic_match": "DIRECT — sudoku is a puzzle, kids 8-12 audience locked.",
      "weakness_assessment": "HARD — top is 'Logic Workbook for Gritty Kids' (multi-puzzle workbook); BSR 2K is competitive but our 1-puzzle-per-page sudoku format differentiates.",
      "rationale": "Anchors book in kids browse. Most parents shop Children's section, not adult Sudoku."
    },
    "secondary": {
      "kdp_path": "Books > Humor & Entertainment > Puzzles & Games > Sudoku",
      "amazon_node_id": "15756641",
      "amazon_url": "https://www.amazon.com/Best-Sellers-Books/zgbs/books/15756641",
      "top_bsr": 44208,
      "top_monthly_royalty_usd": 1143,
      "topic_match": "DIRECT — Sudoku leaf accepts both adult + kid editions.",
      "rationale": "Adult Sudoku leaf has WEAKEST top bestseller in puzzle space ($1,143/mo). Kid sudoku books regularly rank here. Easier to dethrone than Children's Puzzle Books."
    },
    "tertiary": {
      "kdp_path": "Books > Children's Books > Education & Reference > Mathematics > Arithmetic",
      "amazon_node_id": "3256",
      "amazon_url": "https://www.amazon.com/Best-Sellers-Books/zgbs/books/3256",
      "top_bsr": 2159,
      "top_monthly_royalty_usd": 4009,
      "topic_match": "STRONG — sudoku is number-logic, math-adjacent for kids.",
      "rationale": "Captures parents shopping for math/STEM gifts (homeschool, summer learning, tutor recommendations)."
    },
    "rejected_options": {
      "childrens_word_games_3394": "REJECT — sudoku is NUMBER logic, not word game. Topic mismatch.",
      "childrens_action_adventure": "REJECT — total topic mismatch.",
      "adult_logic_brain_teasers_4436": "REJECT — adult-segment leaf, KDP may flag because audience is kids 8-12.",
      "kindle_kids_sudoku": "REJECT — paperback book; puzzle UX broken on Kindle."
    },
    "post_publish_category_requests": [
      "Books > Children's Books > Education & Reference > Study Aids (if exists) — sudoku helps focus + logic skills",
      "Books > Children's Books > Activities, Crafts & Games > Activity Books (parent of Puzzle Books) — only if KDP rejects 3390 leaf"
    ]
  },
  "kdp_listing": {
    "_intent": "Single source of truth for KDP upload form. Paste fields directly into kdp.amazon.com → Paperback → Add Title.",
    "title": "Sudoku for Kids Ages 8-12",
    "subtitle": "120 Fun Brain Games for Kids — Easy to Medium Puzzles to Boost Logic, Focus, and Confidence — Includes Sticker Reward Pages and Solutions",
    "author": {
      "first_name": "BrainCraft",
      "last_name": "Publishing"
    },
    "imprint": "BrainCraft Publishing",
    "description_html": "<h3>The Brain-Boosting Puzzle Book That Kids Actually Finish</h3>\n<p><b>Sudoku for Kids Ages 8-12</b> turns logic into a game your child wants to play. With 120 carefully crafted puzzles (every one solvable without guessing), kids build focus, patience, and number-sense the fun way &mdash; <b>screen-free</b> and proudly so.</p>\n<h3>What's Inside</h3>\n<ul>\n<li><b>120 puzzles built for young brains</b> &mdash; 70 Easy &middot; 50 Medium</li>\n<li><b>Confidence-first progression</b> &mdash; every kid wins their first puzzle, then earns harder ones</li>\n<li><b>One puzzle per page</b> &mdash; clear grids with plenty of space for pencil work</li>\n<li><b>Sticker reward placeholder pages</b> between sections to celebrate progress</li>\n<li><b>Full solutions in the back</b> &mdash; for self-checking or parent-spotting</li>\n<li><b>How-to-play guide</b> with kid-friendly examples</li>\n<li><b>8.5 x 11 inch</b> generous size &mdash; thick paper, no bleed-through</li>\n</ul>\n<h3>Why Parents and Teachers Love It</h3>\n<ul>\n<li>A real <b>screen-free</b> alternative for long car rides, plane trips, rainy days, and waiting rooms</li>\n<li>Quietly builds working memory, logical reasoning, and patience &mdash; sneaky <b>STEM</b> practice in disguise</li>\n<li>Confidence ladder: easy puzzles first, so kids don't quit on page two</li>\n<li>Independent play &mdash; kids can do it alone, leaving parents and teachers free to breathe</li>\n<li>Fits naturally into <b>homeschool</b> morning routines, afterschool quiet time, and rainy-day activity boxes</li>\n</ul>\n<h3>Perfect For</h3>\n<p>Birthday gifts, back-to-school season, road trips, holidays, summer break, rainy weekends, <b>homeschool curriculum</b> add-ons, classroom indoor-recess bins, and any tween who needs a smart break from YouTube. A genuine <b>rainy day activity</b> that holds attention longer than another tablet game.</p>\n<h3>Built for Tween Confidence</h3>\n<p>The hardest part of teaching a kid sudoku isn't the rules &mdash; it's keeping them in their seat after the first failed puzzle. We solved that with a confidence-first ladder: the first 70 puzzles are gently easy so every reader gets early wins, then 50 medium puzzles push their thinking just enough to feel proud, never frustrated. <b>Tween confidence</b>, one grid at a time.</p>\n<h3>A Gift That Earns Its Keep</h3>\n<p>Slip it into a birthday bag, a Christmas stocking, an Easter basket, or a summer-camp going-away kit. Add it to your homeschool order. Toss it in the road-trip bag. Scroll up and add it to your cart &mdash; and watch a kid choose pencil-and-paper logic over a screen for an hour straight.</p>\n<p><i>Logic. Focus. Confidence. One puzzle at a time.</i></p>",
    "keywords_7": [
      "sudoku homeschool stem kids elementary",
      "sudoku kids puzzle book",
      "brain games for kids 8 9 10 11 12",
      "sudoku for children beginners",
      "logic puzzles for tweens",
      "sudoku for kids easy medium",
      "kids activity book sudoku"
    ],
    "categories_paperback_2026": {
      "primary": "Books > Children's Books > Activities, Crafts & Games > Activity Books > Puzzle Books",
      "secondary": "Books > Humor & Entertainment > Puzzles & Games > Sudoku",
      "tertiary": "Books > Children's Books > Education & Reference > Mathematics > Arithmetic",
      "_full_block_with_node_ids": "see recommended_categories_2026 above for amazon_node_id + URL + weakness analysis"
    },
    "primary_audience": {
      "sexually_explicit": false,
      "low_content_book": true,
      "large_print_book": false,
      "reading_age_min": 8,
      "reading_age_max": 12,
      "audience_label": "kids_8_12"
    },
    "print_options": {
      "ink_paper": "Black & white interior with white paper",
      "trim_size": "8.5 x 11 in",
      "bleed": "No Bleed",
      "cover_finish": "Matte"
    },
    "pricing": {
      "list_price_usd": 7.99,
      "list_price_gbp": 7.59,
      "list_price_eur": 7.99,
      "list_price_cad": 10.79,
      "list_price_aud": 12.78,
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

# Sudoku for Kids Ages 8-12

> Single-file source of truth for **sudoku_for_kids_8_12**. Copy fields below directly into kdp.amazon.com → Paperback → Add Title.

---

## 📌 Title (≤ 200 chars)

```
Sudoku for Kids Ages 8-12
```

## 📌 Subtitle (≤ 200 chars)

```
120 Fun Brain Games for Kids — Easy to Medium Puzzles to Boost Logic, Focus, and Confidence — Includes Sticker Reward Pages and Solutions
```

## ✍️ Author / Imprint

- **First name:** `BrainCraft`
- **Last name:** `Publishing`
- **Imprint:** `BrainCraft Publishing`

## 📝 Description (HTML — paste into KDP description box)

```html
<h3>The Brain-Boosting Puzzle Book That Kids Actually Finish</h3>
<p><b>Sudoku for Kids Ages 8-12</b> turns logic into a game your child wants to play. With 120 carefully crafted puzzles (every one solvable without guessing), kids build focus, patience, and number-sense the fun way &mdash; <b>screen-free</b> and proudly so.</p>
<h3>What's Inside</h3>
<ul>
<li><b>120 puzzles built for young brains</b> &mdash; 70 Easy &middot; 50 Medium</li>
<li><b>Confidence-first progression</b> &mdash; every kid wins their first puzzle, then earns harder ones</li>
<li><b>One puzzle per page</b> &mdash; clear grids with plenty of space for pencil work</li>
<li><b>Sticker reward placeholder pages</b> between sections to celebrate progress</li>
<li><b>Full solutions in the back</b> &mdash; for self-checking or parent-spotting</li>
<li><b>How-to-play guide</b> with kid-friendly examples</li>
<li><b>8.5 x 11 inch</b> generous size &mdash; thick paper, no bleed-through</li>
</ul>
<h3>Why Parents and Teachers Love It</h3>
<ul>
<li>A real <b>screen-free</b> alternative for long car rides, plane trips, rainy days, and waiting rooms</li>
<li>Quietly builds working memory, logical reasoning, and patience &mdash; sneaky <b>STEM</b> practice in disguise</li>
<li>Confidence ladder: easy puzzles first, so kids don't quit on page two</li>
<li>Independent play &mdash; kids can do it alone, leaving parents and teachers free to breathe</li>
<li>Fits naturally into <b>homeschool</b> morning routines, afterschool quiet time, and rainy-day activity boxes</li>
</ul>
<h3>Perfect For</h3>
<p>Birthday gifts, back-to-school season, road trips, holidays, summer break, rainy weekends, <b>homeschool curriculum</b> add-ons, classroom indoor-recess bins, and any tween who needs a smart break from YouTube. A genuine <b>rainy day activity</b> that holds attention longer than another tablet game.</p>
<h3>Built for Tween Confidence</h3>
<p>The hardest part of teaching a kid sudoku isn't the rules &mdash; it's keeping them in their seat after the first failed puzzle. We solved that with a confidence-first ladder: the first 70 puzzles are gently easy so every reader gets early wins, then 50 medium puzzles push their thinking just enough to feel proud, never frustrated. <b>Tween confidence</b>, one grid at a time.</p>
<h3>A Gift That Earns Its Keep</h3>
<p>Slip it into a birthday bag, a Christmas stocking, an Easter basket, or a summer-camp going-away kit. Add it to your homeschool order. Toss it in the road-trip bag. Scroll up and add it to your cart &mdash; and watch a kid choose pencil-and-paper logic over a screen for an hour straight.</p>
<p><i>Logic. Focus. Confidence. One puzzle at a time.</i></p>
```

## 🔑 Keywords (7 backend, ≤ 50 chars each)

1. sudoku homeschool stem kids elementary
2. sudoku kids puzzle book
3. brain games for kids 8 9 10 11 12
4. sudoku for children beginners
5. logic puzzles for tweens
6. sudoku for kids easy medium
7. kids activity book sudoku

## 🗂️ Categories — Paperback Browse Paths (3 picks)

| Tier | KDP Browse Path | Node ID | Top BSR | Top $/mo |
|---|---|---|---|---|
| 🥇 Primary | `Books > Children's Books > Activities, Crafts & Games > Activity Books > Puzzle Books` | `3390` | 2159 | 4009 |
| 🥈 Secondary | `Books > Humor & Entertainment > Puzzles & Games > Sudoku` | `15756641` | 44208 | 1143 |
| 🥉 Tertiary | `Books > Children's Books > Education & Reference > Mathematics > Arithmetic` | `3256` | 2159 | 4009 |

> Selection rule: topic match (sudoku/puzzle/logic) > paperback format > Blue Ocean weakness > audience overlap. See `recommended_categories_2026.rejected_options` in the JSON above for what was deliberately excluded.

## 👤 Primary Audience

- **Sexually Explicit:** `No`
- **Low-content book:** `Yes`
- **Large-print book:** `No`
- **Reading age:** 8–12
- **Audience label (internal):** `kids_8_12`

## 🖨️ Print Options

- **Ink & paper:** Black & white interior with white paper
- **Trim size:** 8.5 x 11 in
- **Bleed:** No Bleed
- **Cover finish:** Matte

## 💰 Pricing

| Market | Price |
|---|---|
| 🇺🇸 USD | $7.99 |
| 🇬🇧 GBP | £7.59 |
| 🇪🇺 EUR | €7.99 |
| 🇨🇦 CAD | CA$10.79 |
| 🇦🇺 AUD | AU$12.78 |

## 📁 Files to Upload

- **Interior PDF:** `output/sudoku_for_kids_8_12/interior.pdf`
- **Cover PDF:** `output/sudoku_for_kids_8_12/cover.pdf`

## ✅ Launch Checklist

- [ ] Enroll in **KDP Select** (Yes)
- [ ] Enable **Expanded Distribution** (Yes)
- [ ] Cover includes barcode? **No (KDP adds one)**
- [ ] After live: request 4th–5th categories via KDP support (see `recommended_categories_2026.post_publish_category_requests` in JSON)
