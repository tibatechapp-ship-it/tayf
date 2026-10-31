<div align="center">

# طيف — Tayf Studio

**استوديو توليد الفيديو بالذكاء الاصطناعي — عربي أولًا، شفافية مطلقة، يعمل حتى على هاتفك.**

AI video generation studio — Arabic-first (AR/EN), self-hostable, radically honest.
Describe a scene → get a storyboard, keyframes and a real MP4 — with an auditable
credit system and content-safety screening.

[![CI](https://github.com/tibatechapp-ship-it/tayf/actions/workflows/ci.yml/badge.svg)](https://github.com/tibatechapp-ship-it/tayf/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](backend/requirements.txt)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61dafb.svg)](frontend/package.json)
[![Tests](https://img.shields.io/badge/tests-128%20passing-3fb950.svg)](backend/tests)

</div>

![Studio UI](docs/ui-unified.png)

---

## لماذا طيف؟

| | |
|---|---|
| **شفافية مطلقة** | كل مخرج محاكاة موسوم `SIMULATED` من قاعدة البيانات حتى شارة الواجهة وختم الصورة — لا نجاح مزيف إطلاقًا، والفشل **يُرجع رصيدك تلقائيًا**. |
| **عربي أولًا** | واجهة RTL أصلية (لا ترجمة مُلصقة)، موجّهات ومحتوى عربي، i18n عربي/إنجليزي. |
| **خفيف بلا رحمة** | يعمل على Termux/هاتف وجهاز ضعيف: `uvicorn` عادي، SQLite افتراضيًا، صفر أطر CSS ثقيلة. |
| **ملكية كاملة** | ذاتي الاستضافة بالكامل؛ بياناتك لا تغادر سيطرتك. PostgreSQL بنقلة إعداد واحدة. |

## ما الذي يعمل فعلًا (كل سطر خلفه اختبار)

| الجزء | الدليل |
|---|---|
| تسجيل/دخول/جلسة — Argon2id + JWT | `tests/test_auth.py` |
| مشاريع CRUD بعزل ملكية (404 لا 403) | `tests/test_api_projects.py`, `tests/test_project_crud.py` |
| مهام: فلترة أمان ← خصم رصيد ← خط إنتاج خلفي | `tests/test_pipeline.py` |
| تجميع MP4 حقيقي (ffmpeg: zoompan + xfade + علامة مائية) | `tests/test_compose.py` |
| رصيد: دفتر غير قابل للتعديل + مكافأة تسجيل + ردود فشل | `tests/test_credits.py` |
| تخزين محلي أو S3 متوافق + تنظيف TTL | `tests/test_storage.py`, `tests/test_files.py` |
| أمان محتوى قبل/بعد التوليد | `tests/test_safety.py` |
| هجرات مزدوجة الاتجاه + حراسة انحراف المخطط | `tests/test_migrations.py` |
| رؤوس أمنية + `X-Request-ID` + نقطة `/version` | `tests/test_system.py` |
| تحديد معدل الطلبات (429 + Retry-After) على الدخول وإنشاء المهام | `tests/test_ratelimit.py` |
| رموز تحديث مع تدوير تلقائي للجلسة | `tests/test_refresh.py` |
| روابط ملفات موقعة HMAC قصيرة العمر | `tests/test_files.py` |
| إلغاء المهام مع ردّ الرصيد | `tests/test_cancel.py` |
| مقاييس Prometheus (بلا بيانات مستخدمين) | `tests/test_metrics.py` |
| **المجموعة الكاملة** | `pytest` → **128 ناجحًا** |
| واجهة React 19 + Vite 8 + TS صارم | `npm run build` نظيف |
| **E2E متصفح حقيقي**: تسجيل ← مشروع ← مهمة ← فيديو مكتمل | `scripts/e2e_smoke.py` → `RESULT: PASS`, 0 أخطاء JS |
| **توليد AI حقيقي** (لوحة قصصية + إطارات + MP4) | `docs/AI_PROVIDERS.md` — مخرجات `simulated=false` مؤرشفة |

## التشغيل السريع

```bash
cp .env.example .env            # اختياري؛ الإعدادات الافتراضية تعمل
./scripts/dev.sh start          # alembic upgrade head + API :8000 + UI :5173
./scripts/dev.sh status
```

افتح <http://127.0.0.1:5173>، أنشئ حسابًا (تحصل على 100 رصيد)، أنشئ مشروعًا،
وولّد. المزود الافتراضي `mock` يعمل بلا أي مفاتيح وكل مخرجاته موسومة بوضوح.

### التوليد الحقيقي (خياران)

```bash
# الخيار أ: البوابة الجانبية المرفقة (LLM حقيقي + نموذج صور حقيقي)
./scripts/dev.sh gateway        # sidecar على 127.0.0.1:3030
# ثم في .env:  AI_PROVIDER=zai_gateway

# الخيار ب: مفتاحك الخاص (أي API متوافق مع OpenAI)
#   AI_PROVIDER=openai_compatible
#   OPENAI_BASE_URL=...  OPENAI_API_KEY=...
```

التفاصيل ومصفوفة الصدق: `docs/AI_PROVIDERS.md`.

## التحقق (ما يستشهد به المتتبع)

```bash
cd backend && python -m pytest -q            # 128 passed
cd frontend && npm run build                 # typecheck + bundle
./scripts/run_e2e.sh                         # دورة متصفح كاملة → RESULT: PASS
cd backend && ruff check .                   # lint نظيف

# إثبات المخطط
cd backend && alembic upgrade head && alembic downgrade base && alembic upgrade head
```

## واجهة API

| Method | Path | الحالة |
|---|---|---|
| GET | `/api/v1/health` | منفذة |
| GET | `/api/v1/version` (نسخة + بيئة + مزود) | منفذة |
| POST | `/api/v1/auth/register` → `201` توكن + 100 رصيد | منفذة |
| POST | `/api/v1/auth/login` → `200` توكن | منفذة |
| POST | `/api/v1/auth/refresh` → تدوير زوج الرموز | منفذة |
| GET | `/api/v1/auth/me` | منفذة (JWT) |
| GET/POST | `/api/v1/projects` | منفذة (JWT) |
| GET/PATCH/DELETE | `/api/v1/projects/{id}` | منفذة (الحذف = أرشفة) |
| POST | `/api/v1/projects/{id}/jobs` → `202` | منفذة (`402` عند نقص الرصيد، `429` عند تجاوز الحد) |
| POST | `/api/v1/jobs/{id}/cancel` | منفذة (إلغاء + ردّ الرصيد) |
| GET | `/api/v1/projects/{id}/jobs`, `/api/v1/jobs/{id}` | منفذة |
| GET | `/api/v1/credits/me` | منفذة (رصيد + دفتر) |
| GET | `/api/v1/files/{key}` | منفذة (روابط موقعة HMAC / presign لـ S3) |
| GET | `/api/v1/metrics` | منفذة (عدادات Prometheus) |
| GET | `/docs`, `/openapi.json` | منفذة (FastAPI) |

كل الاستجابات تحمل رؤوسًا دفاعية (`nosniff`, `DENY`, `no-referrer`) و`X-Request-ID`.
الدخول وإنشاء المهام محميان بتحديد معدل (`429 + Retry-After`)، وروابط الملفات موقعة
HMAC قصيرة العمر، والجلسات تتجدد تلقائيًا عبر رموز التحديث.

## البنية

```
backend/app/
  main.py                 تطبيق FastAPI + دورة تنظيف TTL + وسائط أمنية
  api/deps.py             تبعية JWT bearer
  api/v1/endpoints/       auth, projects, jobs, credits, files
  core/                   config (.env), security (Argon2id+JWT), safety, middleware
  db/session.py           مصنع المحرك، SQLite FK+WAL pragmas
  models/                 Base + mixins, User, Project, GenerationJob, CreditLedger
  repositories/           user, project, job (الملكية مفروضة على مستوى الاستعلام)
  schemas/                عقود pydantic السلكية
  services/ai/            عقد أساسي + mock | zai_gateway | openai_compatible
  services/               credits (دفتر), pipeline, compose (ffmpeg)
  services/storage/       base + local + s3 + factory, تنظيف TTL
  migrations/             Alembic: a347dd0c8c67 → c3d9e5f81a42
ai-gateway/               بوابة Node جانبية: LLM حقيقي + نموذج صور (localhost فقط)
frontend/src/             React 19 + Vite 8، i18n عربي/إنجليزي، واجهة داكنة RTL أولًا
scripts/                  dev.sh (start/gateway/stop/status), run_e2e.sh, e2e_smoke.py
docs/                     ARCHITECTURE, DATA_MODEL, AI_PROVIDERS, ENGINEERING_REVIEW
```

## النشر

**Docker (إنتاج):** ثلاث صور مبنية فعليًا (غير root + healthchecks): خلفية بنقاط هجرة تلقائية،
واجهة nginx غير مميّزة مع وكيل `/api` بنفس الأصل، وبوابة AI جانبية. السر إجباري:

```bash
cp .env.example .env                 # ثم اضبط JWT_SECRET أولاً (لا يقلع بدونه)
docker compose up --build            # الواجهة :8080 — API :8080/api/v1
```

**Termux:** `pkg install ffmpeg` مطلوب للتجميع؛ `uvicorn` العادي فقط (لا uvloop)؛
إن فشل بناء `argon2-cffi`/`pillow`: `pkg install clang python-pillow`.
**PostgreSQL:** المخطط محايد للمحرك:

```bash
# .env
DATABASE_URL=postgresql+psycopg://tayf:secret@localhost:5432/tayf
pip install "psycopg[binary]" && cd backend && alembic upgrade head
```

## خارطة الطريق

الأولويات المتبقية (TTS عربي، طابور مهام مستقل، استرجاع كلمة مرور، تقدم لحظي SSE،
معاينة مشاهد وقوالب) موثقة بمنهجية وفي مصفوفة تنافسية كاملة في
**[docs/ENGINEERING_REVIEW.md](docs/ENGINEERING_REVIEW.md)**.
المنجز في 0.5.0: تحديد معدل، رموز تحديث، مقاييس، إلغاء مهام، روابط موقعة،
حاويات إنتاج، وlint في CI.

## الوثائق

`ARCHITECTURE.md` · `DATA_MODEL.md` · `AI_PROVIDERS.md` · `ENGINEERING_REVIEW.md` · `SECURITY.md` · `CONTRIBUTING.md` · `CODE_OF_CONDUCT.md` · `CHANGELOG.md`

## القواعد غير القابلة للتفاوض

1. لا نجاح مزيف — لكل ادعاء أعلاه اختبار أو أثر يثبته.
2. المخرجات المحاكاة **موسومة دائمًا** (`simulated=true` → شارة واجهة + ختم).
3. الأسرار في `.env` فقط (لا تدخل المستودع أبدًا)؛ الإنتاج يتطلب `JWT_SECRET`.
4. يعمل على Termux/الأجهزة ضعيفة الموارد — بلا اعتماديات مُجمَّعة إجبارية.
5. `TASK_TRACKER.md` هو المصدر الوحيد للحقيقة.

## License

[MIT](LICENSE)

---

<div align="center"><em>English summary: self-hosted, Arabic-first AI video studio —
real auth (Argon2id + JWT access/refresh rotation), rate limiting, HMAC-signed
artifact URLs, auditable credits with automatic refunds, job cancellation,
content-safety screening, Prometheus metrics, pluggable AI providers
(mock / gateway / OpenAI-compatible), local or S3 storage with TTL cleanup,
real ffmpeg MP4 composition. 128 passing tests, browser E2E proven, non-root
Docker images, runs on a phone. See the table above for test-backed features.</em></div>
