# KDP Coloring Book Generator

End-to-end pipeline để sản xuất sách tô màu bán trên **Amazon Kindle Direct Publishing (KDP)** cho cả người lớn và trẻ em. Dự án gồm hai lớp:

1. **Python toolbox** ở [scripts/](scripts/) — xử lý ảnh, PDF, cover, QC, ads, reports.
2. **Agent/skill orchestration** ở [.claude/](.claude/) — driver bằng Claude Code qua slash command `/kdp-create-book`.

Một quyển sách đi qua pipeline: `ideas/*.md` → plan (SEO + page prompts) → images → interior PDF → cover → KDP pre-flight QC → listing → ads → analytics.

---

## Luồng chính

```
ideas/*.md
   │
   ▼
plan.json (SEO + page prompts + cover prompt)
   │
   ▼
images/page_NN.png  ← renderer (ai33 | bimai | kie | nanopic)
   │
   ▼
interior.pdf        ← build_pdf.py (gutter auto theo page count)
   │
   ▼
cover.pdf           ← generate_cover.py (spine math theo KDP)
   │
   ▼
pdf_qc.py           ← pre-flight KDP (trim, bleed, line weight, …)
   │
   ▼
✅ sẵn sàng upload lên KDP
```

---

## Cài đặt

### 1. Clone + dependencies

```bash
git clone <this-repo>
cd aws-kdp-ai
pip install -r requirements.txt
```

### 2. Tạo file `.env`

Repo có sẵn [`.env.example`](.env.example) — copy ra `.env` rồi điền giá trị thật:

```bash
cp .env.example .env
# rồi mở .env bằng editor, thay placeholder bằng key thật
```

> ⚠️ **`.env` đã được .gitignore** — TUYỆT ĐỐI không commit token thật. Nếu lỡ commit thì rotate ngay (xem hướng dẫn rotate ở từng provider bên dưới).

### 3. Block cấu hình theo nhu cầu

`.env.example` chia thành 4 block, mỗi block bật/tắt độc lập:

| Block | Bắt buộc khi nào | Setup time |
|-------|------------------|-----------|
| **1. Image Renderer** (`AI33_KEY` / `BIMAI_KEY` / `KIE_API_KEY` / `NANOPIC_ACCESS_TOKEN`) | Chạy `generate_images.py` hoặc `cover-designer` | 5 phút |
| **2. Author Info** (`AUTHOR_FIRST_NAME`, `AUTHOR_LAST_NAME`) | Chạy `build_pdf.py` / `generate_cover.py` (mọi pipeline) | 10 giây |
| **3. Apify** (`APIFY_API_TOKEN`) | Niche research deep-dive (`niche-hunter`) — fallback WebSearch nếu không có | 5 phút (free tier) |
| **4. Amazon Ads API** (6 vars `ADS_API_*`) | Auto-launch ads (`ads-manager`) — bỏ qua nếu chưa lên sách | **1–3 tuần** (Amazon review) |

### Renderer nào nên dùng?

| Renderer | Giá / ảnh | Tốc độ | Quality coloring | Khi dùng |
|----------|-----------|--------|------------------|----------|
| `ai33` | ~$0.005 | Trung bình | ★★★☆☆ ổn định | Default. Rẻ, batch được. |
| `nanopic` | ~$0.01 | Nhanh nhất (token pool) | ★★★★☆ | Khi cần tốc độ + có nhiều token |
| `bimai` | ~$0.02 | Trung bình | ★★★★★ | Cover quality cao, ít page |
| `kie` | ~$0.015 | Trung bình | ★★★★☆ | Backup khi 3 cái trên rate-limit |

Đổi renderer chỉ cần đổi `IMAGE_RENDERER=` trong `.env` — không cần code change.

### Setup Amazon Ads API (chi tiết)

Block 4 trong `.env.example` đã có comment từng bước. Tóm tắt 5 bước:

1. **LWA Security Profile** ([developer.amazon.com](https://developer.amazon.com) → Settings → Security Profiles) → lấy `CLIENT_ID` + `CLIENT_SECRET`
2. **Apply Ads API access** ([advertising.amazon.com/API](https://advertising.amazon.com/API/docs/en-us/setting-up/overview)) → chờ 1-3 tuần
3. **Refresh token**: `python3 scripts/ads_oauth_helper.py` → browser tự mở → Allow → token in ra console
4. **Profile ID**: `python3 scripts/amazon_ads_api.py list-profiles` → copy profileId của marketplace US (hoặc marketplace bạn bán)
5. **Verify**: `python3 scripts/amazon_ads_api.py test-connection` → in `✅ Connected`

> 📌 Tip: chưa có Ads API access vẫn chạy `ads-manager` được — agent sẽ output CSV để upload thủ công vào KDP Ads dashboard.

### Verify cài đặt

```bash
# Test image renderer (1 ảnh smoke test)
python3 scripts/test_ai33.py        # hoặc test_nanopic.py

# Test Amazon Ads (nếu có)
python3 scripts/amazon_ads_api.py test-connection

# Test Apify (nếu có)
python3 -c "import os; from apify_client import ApifyClient; ApifyClient(os.getenv('APIFY_API_TOKEN')).user('me').get(); print('✅ Apify OK')"
```

---

## Chạy pipeline

### 1. Tạo 1 quyển thủ công (chạy từ repo root)

```bash
python scripts/plan_book.py       --concept "cozy cats in a cafe" --audience adults --pages 30 --theme-key cozy_cat_cafe
python scripts/generate_images.py --plan output/cozy_cat_cafe/plan.json --count 30
python scripts/build_pdf.py       --theme cozy_cat_cafe --author "BoBo Art"
python scripts/generate_cover.py  --theme cozy_cat_cafe --author "BoBo Art"
python scripts/pdf_qc.py          --pdf output/cozy_cat_cafe/interior.pdf --trim 8.5x11 --require-even-pages
```

### 2. Batch nhiều quyển

```bash
python scripts/batch_generate_images.py [--book <theme_key>] [--ai33-only|--nanopic-only] [--dry-run]
python scripts/batch_rebuild_interior.py
python scripts/batch_rebuild_cover.py [renderer] [--regenerate]
```

### 3. End-to-end qua agent (khuyến nghị)

Chạy trong Claude Code:

```
/kdp-create-book "concept here"   # interview → plan → image → review → assemble
/kdp-batch-planner                # 1 plan cho mỗi ideas/*.md
/kdp-batch-assembler              # generate + assemble cho mọi sách đã có plan.json
```

---

## Kiến trúc

### Data layout

Mỗi quyển sách sống trong `output/{theme_key}/`:

```
output/{theme_key}/
├── plan.json           # SEO + cover_prompt + page_prompts[] + page_size + audience
├── prompts.txt         # page prompts (compat với luồng cũ)
├── images/page_NN.png  # line art grayscale 300 DPI
├── front_artwork.png   # front cover artwork (reuse khi rebuild)
├── interior.pdf        # file upload interior lên KDP
├── cover.png           # cover preview
└── cover.pdf           # file upload cover lên KDP
```

Briefs ban đầu nằm ở [ideas/](ideas/) (markdown + YAML frontmatter: `topic`, `audience`, `style`, `season`, `score`, `status`). Idea đã xử lý chuyển sang `ideas/done/`.

### Config

Có **hai module config** với chức năng tách biệt:

| Module | Mục đích |
|--------|----------|
| [scripts/config.py](scripts/config.py) | Runtime image pipeline: DPI, page dims, safe area, aspect ratio/renderer, path helpers, `BASE_PROMPT`. Hỗ trợ trim `8.5x11` & `8.5x8.5`. `get_gutter_margin(page_count)` theo KDP (0.375″ @ 24p → 0.875″ @ 701p+). |
| [scripts/kdp_config.py](scripts/kdp_config.py) | Domain math (no I/O): `spine_width_inches()`, `full_cover_dims()`, `printing_cost_usd()`, `royalty_per_sale_usd()`, `break_even_acos_pct()`, `bsr_to_daily_sales()`, `opportunity_score()`, Blue-Ocean niche framework, `LIMITS`, `SEASONS`. |

> `config.THEMES` là `_ThemesProxy`: tự discover mọi `output/{theme_key}/plan.json` khi access — **không cần đăng ký theme ở đâu cả**.

### Image generation

- [scripts/image_providers.py](scripts/image_providers.py) — abstraction cho 4 renderer: `ai33`, `bimai`, `kie`, `nanopic`. NanoPic dùng token pool thread-safe (round-robin).
- [scripts/generate_images.py](scripts/generate_images.py) — post-process: grayscale, contrast/brightness, fit safe area (`ImageOps.contain`), center trên page trắng 300 DPI. Parallel 6 worker. `--start N` để resume sau khi fail.
- [scripts/batch_generate_images.py](scripts/batch_generate_images.py) — fleet-level: chạy 2 provider pool đồng thời (`nanopic` + `ai33`).

### PDF assembly

- [scripts/build_pdf.py](scripts/build_pdf.py) — title → copyright → coloring pages (odd + blank back) → thank-you. Force even page count. Gutter scale theo page count.
- [scripts/generate_cover.py](scripts/generate_cover.py) — full wrap cover (front + spine + back). Spine width = `0.002252″ × page_count` + bleed 0.125″ bốn cạnh. `--regenerate` để buộc AI vẽ lại front.
- [scripts/pdf_qc.py](scripts/pdf_qc.py) — pre-flight validator. Exit non-zero nếu có CRITICAL violation.

### Agent / skill layer

Slash command `/kdp-create-book` spawn agent `kdp-book-creator`, chain:

```
kdp-plan-writer → kdp-image-worker (generate → review → regen loop) → kdp-assembly-worker (build_pdf + cover + qc)
```

Batch agents: `kdp-batch-planner` (ideas → plans), `kdp-batch-assembler` (plans → books).

8 agent tổng thể ("phòng ban"):

| # | Agent | Vai trò |
|---|-------|---------|
| 01 | niche-hunter | Blue-Ocean niche research + Opportunity Score |
| 02 | manuscript-generator | Tạo interior PDF |
| 03 | cover-designer | Front + spine + back |
| 04 | listing-copywriter | Title/subtitle/description/keywords/categories |
| 05 | quality-reviewer | Audit PDF + cover + listing → GO/NO-GO |
| 06 | ads-manager | Amazon Ads Sponsored Products |
| 07 | performance-analyst | Sales/royalty/KENP → weekly action plan |
| 08 | master-orchestrator | CEO — kết nối 7 agent vào pipeline |

### Database (multi-agent state)

[scripts/db.py](scripts/db.py) là SQLite CLI tại `data/kdp.db` — shared state store cho hệ 8 agent (niches, books, manuscripts, covers, listings, qa_reports, ad_campaigns, royalties, actions, pipelines). Agents cần persist giữa các conversation phải đi qua CLI này, không dùng JSON ad-hoc.

---

## KDP rules bắt buộc

- **Images**: ≥ 300 DPI.
- **Interior**: grayscale, outside margin 0.25″, gutter theo `get_gutter_margin()`, even page count, max 4 blank body pages liên tiếp / 10 trailing.
- **Line thickness** ≥ 0.75pt (0.01″). **Fonts** ≥ 7pt. **Gray fills** ≥ 10%.
- Không crop mark / bookmark / annotation / encryption. Flatten transparency. ≤ 650 MB.
- **Metadata phải khớp tuyệt đối** giữa title page / copyright / cover / spine — đây là nguyên nhân reject số 1.
- **Spine text** chỉ cho phép khi ≥ 79 page (`MIN_SPINE_FOR_TEXT_IN = 0.125″`). Luôn check `spine_can_have_text` từ `full_cover_dims()`.
- Metadata **cấm**: "spiral bound", "leather bound", "hard bound", "calendar".
- **Publishing limit**: 10 title / format / tuần.

### Prompt style

- **Adults**: cute-cozy medium-detail, layered fg/mg/bg, shapes lớn stylized, kawaii. KHÔNG cluster chi tiết dày đặc.
- **Kids 6-12**: outline dày đậm sạch, single centered subject. KHÔNG shading / gradient / border / frame.
- Mọi prompt phải có mệnh đề `no border / no enclosing rectangle / no frame` — vì image models rất thích tự vẽ viền.

---

## Conventions

- **Theme key** phải match `^[a-z][a-z0-9_]*$` (snake_case). Validate trong `plan_book.py`. Theme key = folder dưới `output/` = ID duy nhất của một quyển.
- `generate_images.py --start N` skip file `page_NN.png` đã tồn tại — an toàn để rerun.
- `build_pdf.py` / `generate_cover.py` reuse `page_size` từ `plan.json`; `--size` chỉ là override.
- Cover reuse `front_artwork.png` mặc định — pass `--regenerate` để trả tiền renderer thêm một lần.
- `batch_rebuild_cover.py` chạy 6 book song song; arg 1 = renderer, arg 2 = `--regenerate` (optional).

---

## Tài liệu liên quan

- [CLAUDE.md](CLAUDE.md) — hướng dẫn chi tiết cho Claude Code agent.
- [AGENTS.md](AGENTS.md) — operator brief (VN + EN).
- [PRODUCTION_PLAN_100_BOOKS.md](PRODUCTION_PLAN_100_BOOKS.md) — kế hoạch sản xuất 100 sách.
