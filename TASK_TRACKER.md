# TASK_TRACKER.md — Tayf Studio (unified)

> **مصدر الحقيقة الوحيد** لحالة المشروع. لا يُعلَن أي نجاح إلا بمقابلة معايير القبول
> وتنفيذ اختبار فعلي. الحالات المسموح بها فقط:
> `NOT_STARTED` / `IN_PROGRESS` / `IMPLEMENTED` / `TESTED` / `BLOCKED`

| ID | Stage | Task | Status | Acceptance Criteria | Notes/Evidence |
|----|-------|------|--------|---------------------|----------------|
| T-00 | 0 | Project audit & env check | TESTED | Audit doc exists | `docs/AUDIT_PHASE_0.md` (clean start; Python 3.12 / Node 24 / git 2.47) |
| T-01 | 1 | Skeleton: FE ↔ BE health wiring | TESTED | Real 200 through Vite proxy; pytest green | Stage-1 suite + `e2e_smoke.py` |
| T-02 | 1 | Git & clean structure, no secrets | TESTED | Clean history, `.env` ignored | MIT license; staged-file audits clean |
| T-03 | 2 | Data model + migrations | TESTED | Alembic up/down + drift guard | `a347dd0c8c67` + `c3d9e5f81a42`; `test_migrations.py` |
| T-04 | 4 | Auth (Argon2id + JWT on UUIDs) | TESTED | register/login/me pass; no plaintext | `test_auth.py` + `test_user_creation.py` |
| T-05 | 4 | AI provider abstraction + honest mock | TESTED | Mock deterministic + stamped SIMULATED; real providers separated | `test_providers.py`; `docs/AI_PROVIDERS.md` |
| T-06 | 4 | Storage (local/S3) + TTL cleanup | TESTED | Roundtrip, traversal blocked, cleanup deletes expired | `test_storage.py`, `test_files.py` |
| T-07 | 4 | Content safety (pre/post) | TESTED | Rejected-input enforced + documented | `test_safety.py`; rejected job never charged |
| T-08 | 4 | Credits ledger (append-only) | TESTED | Balance = SUM(delta); refunds on failure | `test_credits.py`; charge rows carry job_id |
| T-09 | 4 | Generation pipeline (storyboard→keyframes→MP4) | TESTED | Real playable MP4 via API; failed jobs refund | `test_pipeline.py` (real ffmpeg in tests) |
| T-10 | 4 | Unified schema migration 0002 | TESTED | up/down/up clean on populated DB; models↔migrations no drift | `test_migrations.py` |
| T-11 | 4 | Frontend product UI (AR/EN, RTL-first) | TESTED | Register/project/job/credits flows; zero mock data | `npm run build` clean; browser E2E PASS |
| T-12 | 4 | Browser E2E of the full loop | TESTED | register→project→job→completed video in real Chromium | `scripts/e2e_smoke.py` → `RESULT: PASS`, 0 JS errors |
| T-13 | 4 | **Real AI generation** via zai_gateway | TESTED | `simulated=false` artifacts: real storyboard + JPEG keyframes + MP4 | 2026-10-31: MP4 2.59MB/10.5s from LLM storyboard + 2 real keyframes (wall ≈126s) |
| T-14 | 4 | ai-gateway sidecar (localhost-only) | TESTED | `/health` + real `/v1/chat` answer; token optional | `GATEWAY-OK` round-trip verified |
| T-15 | 4 | CI restored (trigger bug fix) | TESTED | `on.push.branches=[main]` valid; ffmpeg installed for compose tests | was `branches: ain]` → CI never ran on main |
| T-16 | 5 | WebSocket/SSE live progress | NOT_STARTED | UI updates without polling | replaces 4s poll |
| T-17 | 5 | Dedicated worker + queue | NOT_STARTED | multi-process jobs survive restarts | swap `background_tasks.add_task` call site |
| T-18 | 5 | Real video provider (text-to-video) | NOT_STARTED | same interface, `simulated=false` MP4 from vendor model | behind `services/ai/base.py` |
| T-19 | 5 | Payments/top-ups on the ledger | NOT_STARTED | purchase → `grant` with receipt reason | ledger already audit-ready |
| T-20 | 5 | Moderation API + rate limiting | NOT_STARTED | external screening beside local term list | safety layer is the seam |

## سجل الأدلة (Evidence Log)

> كل تحديث حالة يسجّل سطرًا: التاريخ، ما الذي اختُبر فعليًا، وملاحظات.

- **2026-10-31 — الدمج الموحد (T-04…T-15):** دمج خطّي VisionForge (ميزات المرحلة 2 غير المُرحّلة) داخل مستودع tayf القياسي:
  - **خط الأساس الحقيقي قبل الدمج:** suite الفكرة (visionforge) = 44 ✓ / 4 ✗ (خلل `asyncio.create_task` في معالج متزامن). tayf كان CI الخاص به معطلًا (`branches: ain]`) واختباراته تتعطل مع `DATABASE_URL` غير صالح يسرَب من بيئة الاستضافة — أصبح conftest يضبط البيئة قبل أي استيراد.
  - **الإصلاحات الجوهرية أثناء الدمج:**
    1. جدولة الـ pipeline عبر `BackgroundTasks` (يعمل تحت uvicorn وTestClient) — أصل 4 إخفاقات.
    2. عمود JSON والقوائم المشتركة: إسناد `storyboard` يحتاج `copy.deepcopy` عند كل خطوة وإلا يختفي `image_url` بصمت (قيمة قديمة == جديدة بنيويًا) — مكتشف عبر قراءة SQLite الخام.
    3. `username` يُخزن بحروف صغيرة قياسية لضمان تفرد غير حساس لحالة الأحرف على SQLite وPostgreSQL.
    4. ربط قيد الخصم بمعرف المهمة (المعاملة: insert→flush→charge→commit).
    5. `sniff_image_format` من البايتات الفعلية (نموذج الصور يعيد JPEG فعلًا).
  - **الحزمة الموحدة:** `pytest` → **95 passed** (≈234s، تشمل تركيب MP4 حقيقي).
  - **الواجهة:** React 19 + Vite 8 + TS strict — بناء نظيف (74.7KB gzip)، AR/EN، RTL-first.
  - **E2E بمتصفح حقيقي:** `RESULT: PASS` — تسجيل → مشروع → مهمة → `مكتملة` مع فيديو حقيقي، الرصيد 96/100 بعد مهمة 4 مشاهد، شارة «محاكاة» ظاهرة، صفر أخطاء JS. لقطة: `docs/ui-unified.png`.
  - **توليد حقيقي (zai_gateway):** قصة من LLM (مشهدان بالوصف الكامل) + إطاران JPEG حقيقيان (186KB/196KB) + MP4 حقيقي 2.59MB/10.5 ثانية، `simulated=false`، زمن ≈126s. الأدلة: MP4 + keyframes + JSON في أرشيف المالك.
  - **فشل صادق مُوثق أيضًا:** تجربة ببوابة متوقفة أنتجت `failed` برسالة واضحة واستردادًا كاملًا (`credits_charged=0`) — السلوك المطلوب.
  - **CI:** أُصلح مشغل `push` وأُضيف ffmpeg لاختبارات التركيب.
  - **أمان:** لا أسرار في المستودع (`.env` مثال فقط بقيم وهمية؛ `JWT_SECRET` مطلوب في production).

## ملاحظات التشغيل على Termux

- `pkg install ffmpeg` مطلوب لتركيب الفيديو؛ `uvicorn` العادي فقط (لا uvloop).
- TypeScript مثبت على 5.x (لا يوجد بناء android-arm64 لـ TS 7).
- إذا فشل بناء `argon2-cffi`/`pillow`: `pkg install clang python-pillow`.
- S3 اختياري (`requirements-s3.txt`) — boto3 ثقيل، والكود يعطي خطأ صادقًا إن طُلب بدون تثبيت.
