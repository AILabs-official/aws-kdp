# Hướng dẫn kết nối Amazon Ads API cho KDP

Tài liệu này dắt bạn đi từ **chưa có gì** → **chạy được lệnh `python3 scripts/amazon_ads_api.py launch`** để tự động tạo 3 chiến dịch Sponsored Products cho 1 quyển sách KDP của bạn.

> **Tổng thời gian thực tế:** 5–9 tuần. Trong đó ~95% là chờ Amazon duyệt đơn (Stage 2). Các bước còn lại (cài đặt, OAuth, test) chỉ mất ~30 phút.

> **Đối tượng:** tác giả KDP đã có ít nhất 1 sách live và muốn tự động hoá ads cho chính sách của mình. Không phù hợp với agency hoặc tool provider — quy trình duyệt sẽ khác.

---

## Lộ trình tổng quan

| Stage | Việc cần làm | Thời gian | Bạn làm | Amazon làm |
|---|---|---|---|---|
| 0 | Chuẩn bị KDP + lịch sử ads | 30+ ngày | ✅ | — |
| 1 | Tạo LWA Security Profile | 10 phút | ✅ | — |
| 2 | Nộp đơn Ads API access | 5 phút nộp + 1–3 tuần chờ | ✅ | ⏳ duyệt |
| 3 | Lấy `refresh_token` qua OAuth | 5 phút | ✅ | — |
| 4 | Lấy `profileId` | 2 phút | ✅ | — |
| 5 | Test kết nối | 1 phút | ✅ | — |
| 6 | Launch chiến dịch đầu tiên | 5 phút | ✅ | — |
| 7 | Kéo report về DB | 2 phút | ✅ | — |

---

## Stage 0 — Chuẩn bị (BẮT BUỘC làm trước khi nộp đơn)

Amazon **rất nghiêm** ở khâu duyệt. Nếu thiếu các điều kiện sau, đơn của bạn 99% bị từ chối:

- [ ] **≥ 1 sách KDP đã LIVE** (có ASIN, không phải draft, không phải in-review). Kiểm tra: vào KDP Bookshelf → trạng thái phải là **"Live"**.
- [ ] **Amazon Advertising account đã bật.** Đăng nhập [advertising.amazon.com](https://advertising.amazon.com) bằng tài khoản KDP → nếu thấy dashboard Sponsored Products là OK.
- [ ] **Đã chạy ≥ 1 chiến dịch thủ công, ≥ 30 ngày, có chi tiêu thực tế.** Đây là điều kiện ngầm — Amazon từ chối account chưa từng chạy ads. Tối thiểu spend $30–50.
- [ ] **Đã hoàn thành Tax Interview** (nếu target market US).
- [ ] **Email tài khoản KDP có thể nhận mail** (đơn duyệt + token noti gửi qua mail này).

**Cách kiểm tra ad history:** [advertising.amazon.com](https://advertising.amazon.com) → Reports → Last 60 days. Nếu trống ⇒ chưa đủ điều kiện.

---

## Stage 1 — Tạo LWA Security Profile (10 phút)

LWA = **Login With Amazon**. Đây là "ứng dụng OAuth" mà KDP-OS sẽ dùng để xin quyền truy cập ad account của bạn.

### 1.1 Vào Developer Console

1. Mở https://developer.amazon.com
2. Bấm **Sign In** ở góc phải → đăng nhập **bằng đúng email KDP** (nếu khác email, account ads sau này sẽ không link được).
3. Sau khi đăng nhập, vào **Settings** (góc phải trên) → **Security Profiles**.
4. Bấm nút xanh **"Create a New Security Profile"**.

### 1.2 Điền thông tin Security Profile

| Field | Giá trị nên điền |
|---|---|
| Security Profile Name | `KDP-OS-Ads` (hoặc tên gì cũng được, chỉ bạn thấy) |
| Security Profile Description | `Internal automation for own KDP titles` |
| Consent Privacy Notice URL | URL công khai bất kỳ — GitHub repo, blog, Notion page. Bắt buộc phải có nhưng Amazon **không** kiểm tra nội dung. |

Bấm **Save**.

### 1.3 Lấy Client ID + Client Secret

Sau khi save, bạn quay về danh sách Security Profiles. Tại profile vừa tạo, bấm **Show Client ID and Client Secret**:

```
Client ID:     amzn1.application-oa2-client.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Client Secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Copy cả 2 giá trị này, lưu vào notepad tạm.** Sẽ paste vào `.env` ở Stage 3.

### 1.4 Set Allowed Return URLs

Đây là bước **dễ quên nhất** — quên cái này thì Stage 3 (OAuth) sẽ fail với lỗi `invalid_redirect_uri`.

1. Vẫn ở Security Profile vừa tạo, bấm tab **Web Settings** → **Edit**.
2. **Allowed Origins**: để trống (KDP-OS dùng localhost, không cần CORS).
3. **Allowed Return URLs**: paste chính xác:
   ```
   http://localhost:8765/callback
   ```
4. Bấm **Save**.

> **Lưu ý:** URL phải khớp **chính xác từng ký tự** với `ADS_API_REDIRECT_URI` trong `.env` (Stage 3). Nếu bạn đổi cổng (port), nhớ đổi cả 2 chỗ.

---

## Stage 2 — Nộp đơn xin Ads API access (1–3 tuần chờ)

Đây là khâu **dài nhất**. Cứ làm xong Stage 1 thì nộp luôn — đừng chờ Stage 3.

### 2.1 Mở form nộp đơn

1. Vào https://advertising.amazon.com/API/docs/en-us/setting-up/overview
2. Bấm **"Apply for access"** (nút xanh, thường ở giữa trang).
3. Đăng nhập bằng đúng email KDP nếu được hỏi.

### 2.2 Điền form

| Field | Giá trị | Ghi chú |
|---|---|---|
| Company Name | Tên cá nhân hoặc tên brand KDP | Cá nhân OK, đừng bịa pháp nhân không tồn tại |
| Country | Nước bạn | Phải khớp tax interview KDP |
| Application Type | **Advertiser** | ⚠ KHÔNG chọn "Tool Provider" hay "Agency" — quy trình duyệt khác hoàn toàn |
| Use Case | Paste đoạn dưới ⬇ | Quan trọng nhất |
| API calls/day estimate | `100` | Số nhỏ để không bị soi |
| Marketplaces | Chỉ chọn nơi bạn thực sự bán | Thường chỉ US |
| Security Profile | Chọn `KDP-OS-Ads` từ Stage 1 | Dropdown |

**Use Case mẫu** (copy-paste, đã được duyệt nhiều lần):

> Internal automation tool to manage Sponsored Products campaigns for my own KDP (Kindle Direct Publishing) titles. The tool will be used solely by me as the account owner — no third-party access, no data resale, no client management. It will create campaigns, adjust bids based on ACOS performance, harvest converting search terms, and pull reports for personal analysis.

### 2.3 Submit + chờ

- Sau khi submit, Amazon gửi mail xác nhận **trong 24h**.
- Email duyệt/từ chối thường về sau **1–3 tuần**.
- Nếu được duyệt: email tiêu đề kiểu *"Your Amazon Advertising API application has been approved"*.

### 2.4 Nếu bị từ chối — cách xử lý

| Lý do từ chối | Cách fix |
|---|---|
| *"Use case unclear"* / *"Need more detail"* | Reapply, paste thêm 1 câu: "All advertising activity is for my own published books listed under my KDP author account. No external client work." |
| *"No advertising history"* | Quay lại Stage 0, chạy thêm ads thủ công 30 ngày, reapply |
| *"Please choose Advertiser path"* | Bạn lỡ chọn Agency/Tool Provider — reapply chọn Advertiser |
| *"Marketplace mismatch"* | Marketplace bạn chọn không có sách live — chọn lại đúng marketplace |

**Tỷ lệ thực tế:** lần 1 từ chối, lần 2 sửa lại theo gợi ý ⇒ 90% được duyệt.

---

## Stage 3 — Lấy `refresh_token` (5 phút sau khi Amazon duyệt)

### 3.1 Điền `.env`

Mở file `.env` ở repo root, thêm 4 dòng (lúc này **chưa** có `ADS_API_REFRESH_TOKEN`):

```bash
# Amazon Ads API — KDP automation
ADS_API_CLIENT_ID=amzn1.application-oa2-client.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADS_API_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADS_API_REDIRECT_URI=http://localhost:8765/callback
ADS_API_REGION=NA
```

| Biến | Giá trị | Lấy từ đâu |
|---|---|---|
| `ADS_API_CLIENT_ID` | `amzn1.application-oa2-client...` | Stage 1.3 |
| `ADS_API_CLIENT_SECRET` | Chuỗi 64 ký tự | Stage 1.3 |
| `ADS_API_REDIRECT_URI` | `http://localhost:8765/callback` | **Phải khớp** Stage 1.4 |
| `ADS_API_REGION` | `NA` (Bắc Mỹ) / `EU` / `FE` (Far East) | Marketplace của bạn |

> **Region map:** US/CA/MX → `NA`; UK/DE/FR/IT/ES/NL/SE/PL → `EU`; JP/AU/SG/AE → `FE`. Sai region ⇒ token refresh OK nhưng mọi API call đều `401`.

### 3.2 Cài dependencies (nếu chưa)

```bash
pip install -r requirements.txt
```

### 3.3 Chạy OAuth helper

```bash
python3 scripts/ads_oauth_helper.py
```

Bạn sẽ thấy:

```
────────────────────────────────────────────────────────────
Opening browser for Amazon LWA consent...
If browser doesn't open, paste this URL manually:
  https://www.amazon.com/ap/oa?client_id=...
────────────────────────────────────────────────────────────
Waiting for callback on http://localhost:8765/callback ...
```

**Trình duyệt tự mở** trang Amazon consent. Nếu không tự mở, copy URL ở terminal paste vào browser.

### 3.4 Trên trang Amazon

1. Đăng nhập **bằng email KDP** (cùng email Stage 1).
2. Bạn thấy màn hình *"KDP-OS-Ads is requesting permission to manage your Amazon Advertising campaigns"*.
3. Bấm **"Allow"**.
4. Browser tự redirect về `http://localhost:8765/callback?code=...` → trang sẽ hiện *"OK - you can close this tab."*
5. Đóng tab, **quay về terminal**.

### 3.5 Verify

Terminal in:

```
✓ Got authorization code, exchanging for refresh_token...

============================================================
✅ SUCCESS
============================================================
refresh_token: Atzr|IwEBI...  (chuỗi rất dài, ~300+ ký tự)
✓ Auto-patched .env with ADS_API_REFRESH_TOKEN

Next: python3 scripts/amazon_ads_api.py list-profiles
```

Kiểm tra `.env` đã được patch:

```bash
grep ADS_API_REFRESH_TOKEN .env
# Output: ADS_API_REFRESH_TOKEN=Atzr|IwEBI...
```

> **Refresh token KHÔNG hết hạn** trừ khi bạn (a) đổi password Amazon, (b) revoke consent ở developer.amazon.com, hoặc (c) account bị khoá. Một lần setup là xong.

---

## Stage 4 — Lấy `profileId` (2 phút)

`profileId` định danh **một marketplace cụ thể** trong account của bạn. Mỗi marketplace = 1 profile riêng (US, UK, DE...).

```bash
python3 scripts/amazon_ads_api.py list-profiles
```

Output mẫu:

```json
[
  {
    "profileId": 1234567890123456,
    "countryCode": "US",
    "currencyCode": "USD",
    "dailyBudget": 0,
    "timezone": "America/Los_Angeles",
    "accountInfo": {
      "marketplaceStringId": "ATVPDKIKX0DER",
      "id": "A2EUQ1WTGCTBG2",
      "type": "author",
      "name": "Your KDP Pen Name"
    }
  },
  {
    "profileId": 9876543210987654,
    "countryCode": "UK",
    "currencyCode": "GBP",
    ...
  }
]

Set ADS_API_PROFILE_ID in .env to one of the profileId values above.
For US KDP ads, look for countryCode=US.
```

**Chọn profile bạn muốn chạy ads** (thường là `US`), copy `profileId` (số 16 chữ số), paste vào `.env`:

```bash
ADS_API_PROFILE_ID=1234567890123456
```

> **Quan trọng:** `accountInfo.type` phải là `"author"` (KDP). Nếu thấy `"vendor"` hay `"seller"` ⇒ bạn đang vào nhầm account.

---

## Stage 5 — Test kết nối (1 phút)

```bash
python3 scripts/amazon_ads_api.py test-connection
```

Output mong muốn:

```
✓ access_token refreshed (len=312)
✓ profile 1234567890123456 → US author
```

Nếu thấy 2 dấu ✓ ⇒ **xong**. Đi tiếp Stage 6.

### Nếu thấy ❌

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `missing env vars: ADS_API_CLIENT_ID, ...` | `.env` thiếu biến | Quay lại Stage 3.1 |
| `token refresh failed: 400 invalid_grant` | refresh_token sai/đã revoke | Chạy lại `ads_oauth_helper.py` |
| `token refresh failed: 401 invalid_client` | Client ID hoặc Secret sai | Kiểm tra Stage 1.3, copy lại |
| `unknown ADS_API_REGION='X'` | Region không phải NA/EU/FE | Sửa `.env` |
| `profile XYZ not found in your account list` | profileId sai hoặc thuộc account khác | Chạy lại `list-profiles` |

---

## Stage 6 — Launch chiến dịch đầu tiên

Cú pháp `launch` tạo **3 chiến dịch** một lúc cho 1 ASIN:

| Campaign | Loại | Budget mặc định | Bid | Mục đích |
|---|---|---|---|---|
| Launch Auto | AUTO targeting | $5/ngày | bid × 0.9 | Để Amazon tự khám phá keywords mới |
| Launch Exact | MANUAL exact-match | $10/ngày | bid × 1.0 | Bid mạnh vào từ khoá đã verify |
| Launch Phrase | MANUAL phrase-match | $5/ngày | bid × 0.9 | Mở rộng từ root keyword |

Tất cả đều có **negative keywords mặc định**: `free`, `download`, `pdf`, `kindle` (chặn click rác).

### 6A — Dry-run trước (KHUYẾN NGHỊ — không tốn tiền)

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

Output:

```
DRY RUN — would create 27 bulk-sheet rows for ASIN B0XXXXXXXX
  Campaign: Launch Auto — Dinosaur Coloring Book for Kids
  Ad Group: Launch Auto — Dinosaur Coloring Book for Kids
  Product Ad: Launch Auto — Dinosaur Coloring Book for Kids
  Campaign: Launch Exact — Dinosaur Coloring Book for Kids
  Ad Group: Launch Exact — Dinosaur Coloring Book for Kids
  Product Ad: Launch Exact — Dinosaur Coloring Book for Kids
  ... +21 more rows
```

Không có API call nào. Chỉ in ra plan. Nếu thấy plan OK, chạy thật.

### 6B — Launch thật

Bỏ `--dry-run`, thêm `--book-id` để ghi vào DB:

```bash
python3 scripts/amazon_ads_api.py launch \
  --asin B0XXXXXXXX \
  --title "Dinosaur Coloring Book for Kids" \
  --bid 0.12 \
  --keywords-exact '["dinosaur coloring book","t-rex coloring kids"]' \
  --keywords-phrase '["coloring book ages 6-12"]' \
  --book-id 3
```

Output thành công:

```
🚀 Launching ads for ASIN B0XXXXXXXX (Dinosaur Coloring Book for Kids)...

============================================================
✅ LAUNCH COMPLETE
============================================================
  [auto  ] campaign=523456789012345 adGroup=412345678901234 ad=312345678901234 keywords=0
  [exact ] campaign=623456789012345 adGroup=512345678901234 ad=412345678901234 keywords=2
  [phrase] campaign=723456789012345 adGroup=612345678901234 ad=512345678901234 keywords=1
✓ wrote 3 ad_campaigns rows for book_id=3
```

### 6C — Cờ tham số

| Flag | Default | Ghi chú |
|---|---|---|
| `--asin` | (bắt buộc) | ASIN sách KDP |
| `--title` | (bắt buộc) | Tên hiển thị trong campaign name (cắt còn 40 ký tự) |
| `--bid` | `0.10` | Default bid USD. Auto = bid×0.9; Exact = bid; Phrase = bid×0.9 |
| `--budget-auto` | `5.0` | $/ngày Auto campaign |
| `--budget-exact` | `10.0` | $/ngày Exact campaign |
| `--budget-phrase` | `5.0` | $/ngày Phrase campaign |
| `--keywords-exact` | (bắt buộc) | JSON array, ≥ 5 từ khoá |
| `--keywords-phrase` | (optional) | JSON array, có thể bỏ |
| `--book-id` | (optional) | Nếu set, ghi `ad_campaigns` rows vào `data/kdp.db` |
| `--dry-run` | off | Chỉ in plan, không gọi API |

### 6D — Sau khi launch

- Campaigns vào trạng thái **`ENABLED`** ngay lập tức.
- Amazon **review nội bộ 24–72h** trước khi ads thật sự hiển thị.
- Trong 24h đầu impressions thường = 0, đó là bình thường.
- Nếu muốn pause để xem trước: vào [advertising.amazon.com](https://advertising.amazon.com) → Campaigns → tick → Pause. Hoặc sửa code `create_campaign` trong `scripts/amazon_ads_api.py:154` đổi `"state": "ENABLED"` → `"PAUSED"`.

---

## Stage 7 — Kéo report về DB

```bash
# Last 7 days, in 10 rows đầu ra terminal
python3 scripts/amazon_ads_api.py report --days 7

# Last 14 days, save vào file JSON
python3 scripts/amazon_ads_api.py report --days 14 --out output/ads_report.json

# Last 7 days, ghi thẳng vào ad_performance table
python3 scripts/amazon_ads_api.py report --days 7 --write-db

# Custom range (cho audit lịch sử)
python3 scripts/amazon_ads_api.py report --start-date 2026-03-01 --end-date 2026-03-31 --write-db
```

### Giới hạn quan trọng

- **Tối đa 31 ngày/request** (giới hạn của Amazon SP API). Nếu cần > 31 ngày, chạy nhiều lần với `--start-date`/`--end-date`. Script sẽ báo lỗi sớm nếu `--days > 31`.
- **Report là async**: request → polling 15s/lần → tải gzipped JSON. Tổng ~30s–3 phút tuỳ tải Amazon.
- **Columns mặc định**: `campaignName, campaignId, impressions, clicks, cost, purchases7d, sales7d, acosClicks14d`.

### Cờ tham số

| Flag | Default | Ghi chú |
|---|---|---|
| `--days` | `7` | Last N days (max 31) |
| `--start-date` | — | YYYY-MM-DD, override `--days` |
| `--end-date` | — | YYYY-MM-DD, override `--days` |
| `--out` | — | Path JSON file để dump full rows |
| `--write-db` | off | Ghi vào `ad_performance` table (cho `/weekly-cycle` agent đọc) |

### Tích hợp với agent

Sau khi `--write-db`, agent **performance-analyst** ([.claude/agents/performance-analyst.md](.claude/agents/performance-analyst.md)) sẽ đọc `ad_performance` để classify book Winner/Promising/Stuck/Dead và sinh actions cho CEO. Thường lập lịch chạy:

```bash
# Daily morning brief
python3 scripts/amazon_ads_api.py report --days 1 --write-db

# Weekly deep-dive
python3 scripts/amazon_ads_api.py report --days 7 --write-db
```

---

## Quick reference — câu lệnh hay dùng

| Việc | Lệnh |
|---|---|
| OAuth lần đầu (sau khi Amazon duyệt) | `python3 scripts/ads_oauth_helper.py` |
| List profiles | `python3 scripts/amazon_ads_api.py list-profiles` |
| Health check | `python3 scripts/amazon_ads_api.py test-connection` |
| Dry-run launch | `python3 scripts/amazon_ads_api.py launch --asin X --title Y --bid 0.12 --keywords-exact '[...]' --dry-run` |
| Launch thật + ghi DB | `python3 scripts/amazon_ads_api.py launch ... --book-id N` |
| Pull report 7d → DB | `python3 scripts/amazon_ads_api.py report --days 7 --write-db` |
| Pull report custom range | `python3 scripts/amazon_ads_api.py report --start-date 2026-03-01 --end-date 2026-03-31 --out report.json` |
| Bulk CSV (no API, fallback) | `python3 scripts/amazon_ads_api.py bulk-export --asin X --title Y --out plan.csv` |

---

## Troubleshooting đầy đủ

### Lỗi auth / token

| Error | Nguyên nhân | Fix |
|---|---|---|
| `missing env vars: ADS_API_*` | `.env` thiếu biến | Quay lại Stage 3.1 |
| `token refresh failed: 400 invalid_grant` | Refresh token sai hoặc đã revoke (đổi password, thu hồi consent) | Chạy lại `python3 scripts/ads_oauth_helper.py` |
| `token refresh failed: 401 invalid_client` | Client ID/Secret sai | Copy lại từ Stage 1.3, để ý dấu cách thừa khi paste |
| OAuth helper báo `invalid_redirect_uri` | URL trong Stage 1.4 ≠ `ADS_API_REDIRECT_URI` | Sửa cho khớp **chính xác từng ký tự** (kể cả trailing slash) |
| OAuth helper kẹt ở "Waiting for callback..." | Port 8765 bị process khác chiếm | `lsof -i :8765` → kill process, hoặc đổi `ADS_API_REDIRECT_URI=http://localhost:9876/callback` (nhớ update Stage 1.4) |

### Lỗi profile / region

| Error | Nguyên nhân | Fix |
|---|---|---|
| `401 Unauthorized` trên mọi API call | Region sai | Vd: profile `countryCode=DE` nhưng `ADS_API_REGION=NA` ⇒ đổi sang `EU` |
| `403 Forbidden` | API access chưa được duyệt | Chờ email duyệt từ Stage 2 |
| `profile XYZ not found in your account list` | profileId thuộc account khác hoặc đã đóng | Chạy lại `list-profiles`, paste lại |
| `accountInfo.type = vendor` không có `author` | Đăng nhập nhầm account | OAuth lại bằng email KDP |

### Lỗi launch

| Error | Nguyên nhân | Fix |
|---|---|---|
| `--keywords-exact required` | Quên flag | Thêm `--keywords-exact '["kw1","kw2"]'` |
| `could not extract campaignId from response` | Amazon trả về error trong success block | In raw response ra (sửa `_extract_id` thêm `print(resp)`) — thường do duplicate campaign name, đổi `--title` |
| `422 Unprocessable Entity` | Body sai schema (vd. bid quá thấp) | Bid tối thiểu Sponsored Products là $0.02. Tăng `--bid 0.02` trở lên |
| Campaign tạo xong nhưng "no impressions" 24h+ | Đang trong review của Amazon | Bình thường. Đợi 72h |
| Negative keyword fail nhưng campaign vẫn tạo | API negative keyword đôi khi flaky | Script đã `try/except` → không fail toàn bộ launch. Add manual sau ở web console |

### Lỗi report

| Error | Nguyên nhân | Fix |
|---|---|---|
| `Amazon SP reports max 31 days/request` | `--days > 31` | Dùng `--start-date` + `--end-date`, chạy nhiều chunks |
| `report failed: {...}` khi polling | Amazon backend lỗi | Retry sau 5–10 phút |
| `report COMPLETED but no download URL` | Không có data trong khoảng | Mở rộng date range, check campaign đã có spend chưa |
| `TimeoutError: report XXX not ready after 600s` | Report quá nặng | Giảm khoảng ngày, hoặc tăng `max_wait_s` trong `poll_report` |

### Rate limits

Amazon SP API: **5 requests/sec** mặc định. Launch 1 sách = ~7 calls (3 campaigns × {campaign + adGroup + productAd} + keywords + negatives) ⇒ OK.

Nếu chạy batch nhiều sách: thêm `time.sleep(1)` giữa các sách hoặc giới hạn parallel cap = 5 (đã set ở [.claude/agents/ads-manager.md](.claude/agents/ads-manager.md)).

---

## Những gì stack này CHƯA làm

- **Sponsored Brands API** — KDP author profiles không có quyền truy cập (Amazon limitation). Chỉ tạo được qua web console.
- **Sponsored Display API** — schema đã support nhưng launch flow chưa wire ở `amazon_ads_api.py`.
- **Bid optimization tự động** — `performance-analyst` đọc report nhưng PUT update bid về Amazon chưa wire (xem TODO trong [.claude/skills/ads-manager/SKILL.md](.claude/skills/ads-manager/SKILL.md)).
- **Bulk negative harvesting** từ search-term reports — TODO. Hiện chỉ có 4 negative cứng (`free`/`download`/`pdf`/`kindle`).

Đây là follow-ups dễ làm sau khi 5–10 sách launch ổn định.

---

## Phụ lục — Cấu trúc `.env` đầy đủ sau setup

```bash
# Amazon Ads API
ADS_API_CLIENT_ID=amzn1.application-oa2-client.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADS_API_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADS_API_REFRESH_TOKEN=Atzr|IwEBI...                    # tự fill bởi ads_oauth_helper.py
ADS_API_REDIRECT_URI=http://localhost:8765/callback
ADS_API_REGION=NA                                       # NA | EU | FE
ADS_API_PROFILE_ID=1234567890123456                     # Stage 4
```

**TUYỆT ĐỐI không** commit `.env` lên git. File `.gitignore` đã chặn sẵn — kiểm tra: `git check-ignore .env` phải in ra `.env`.

---

## Phụ lục — Endpoints mà script gọi

| Action | Method | Endpoint | Content-Type |
|---|---|---|---|
| Refresh token | POST | `https://api.amazon.com/auth/o2/token` | `application/x-www-form-urlencoded` |
| List profiles | GET | `/v2/profiles` | — |
| Create campaign | POST | `/sp/campaigns` | `application/vnd.spCampaign.v3+json` |
| Create ad group | POST | `/sp/adGroups` | `application/vnd.spAdGroup.v3+json` |
| Create product ad | POST | `/sp/productAds` | `application/vnd.spProductAd.v3+json` |
| Create keywords | POST | `/sp/keywords` | `application/vnd.spKeyword.v3+json` |
| Create negative keywords | POST | `/sp/negativeKeywords` | `application/vnd.spNegativeKeyword.v3+json` |
| Request report | POST | `/reporting/reports` | `application/vnd.createasyncreportrequest.v3+json` |
| Poll report | GET | `/reporting/reports/{reportId}` | same |

Base URL theo region:
- `NA` → `https://advertising-api.amazon.com`
- `EU` → `https://advertising-api-eu.amazon.com`
- `FE` → `https://advertising-api-fe.amazon.com`

Tất cả đều cần 3 headers:
- `Authorization: Bearer <access_token>`
- `Amazon-Advertising-API-ClientId: <client_id>`
- `Amazon-Advertising-API-Scope: <profile_id>` (trừ `/v2/profiles`)
