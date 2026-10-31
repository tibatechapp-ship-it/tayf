/** Bilingual copy (AR default / EN) — every UI string lives here. */

export type Lang = "ar" | "en";

export interface Copy {
  dir: "rtl" | "ltr";
  brand: string;
  tagline: string;
  switchLabel: string;

  // auth
  loginTitle: string;
  registerTitle: string;
  identifier: string;
  identifierPlaceholder: string;
  email: string;
  username: string;
  password: string;
  login: string;
  register: string;
  haveAccount: string;
  needAccount: string;
  authErrorPrefix: string;

  // shell
  logout: string;
  balance: string;
  creditsUnit: string;
  serverError: string;

  // projects
  projects: string;
  newProject: string;
  projectName: string;
  projectNamePlaceholder: string;
  projectDescription: string;
  projectDescriptionPlaceholder: string;
  create: string;
  archive: string;
  archivedTag: string;
  showArchived: string;
  noProjects: string;
  jobsCount: string;
  backToProjects: string;

  // jobs
  newJob: string;
  promptLabel: string;
  promptPlaceholder: string;
  scenes: string;
  aspect: string;
  style: string;
  cost: string;
  generate: string;
  generating: string;
  noJobs: string;
  jobsTitle: string;
  simulatedBadge: string;
  realBadge: string;
  rejection: string;
  jobError: string;
  videoLabel: string;
  storyboard: string;
  durationSeconds: string;
  selectProjectHint: string;
  insufficient: string;

  // ledger + cancellation
  ledgerTitle: string;
  ledgerEmpty: string;
  ledgerSignup: string;
  ledgerCharge: string;
  ledgerRefundFailed: string;
  ledgerRefundCancelled: string;
  ledgerOther: string;
  cancel: string;
  cancelling: string;

  // statuses
  status_pending: string;
  status_processing: string;
  status_completed: string;
  status_failed: string;
  status_rejected: string;
  status_cancelled: string;

  honestyTitle: string;
  honestyBody: string;
  footerNote: string;
  featureHonest: string;
  featureCredits: string;
  featureSafety: string;
}

export const copy: Record<Lang, Copy> = {
  ar: {
    dir: "rtl",
    brand: "طيف",
    tagline: "استوديو توليد الفيديو بالذكاء الاصطناعي",
    switchLabel: "English",

    loginTitle: "تسجيل الدخول",
    registerTitle: "حساب جديد",
    identifier: "البريد الإلكتروني أو اسم المستخدم",
    identifierPlaceholder: "you@example.com أو username",
    email: "البريد الإلكتروني",
    username: "اسم المستخدم",
    password: "كلمة المرور",
    login: "دخول",
    register: "إنشاء الحساب",
    haveAccount: "لدي حساب بالفعل",
    needAccount: "ليس لدي حساب",
    authErrorPrefix: "تعذّر إكمال العملية",

    logout: "خروج",
    balance: "الرصيد",
    creditsUnit: "رصيد",
    serverError: "تعذر الاتصال بالخادم",

    projects: "المشاريع",
    newProject: "مشروع جديد",
    projectName: "اسم المشروع",
    projectNamePlaceholder: "مثال: إعلان مقهى الحرم",
    projectDescription: "الوصف (اختياري)",
    projectDescriptionPlaceholder: "فكرة قصيرة عن المشروع",
    create: "إنشاء",
    archive: "أرشفة",
    archivedTag: "مؤرشف",
    showArchived: "إظهار المؤرشفة",
    noProjects: "لا مشاريع بعد — أنشئ مشروعك الأول.",
    jobsCount: "مهمة",
    backToProjects: "كل المشاريع",

    newJob: "مهمة توليد جديدة",
    promptLabel: "وصف الفيديو المطلوب",
    promptPlaceholder:
      "مثال: لقطة سينمائية بطيئة لمقهى عربي عند الفجر، بخار يتصاعد من فنجان القهوة",
    scenes: "عدد المشاهد",
    aspect: "أبعاد الإطار",
    style: "النمط",
    cost: "التكلفة",
    generate: "توليد",
    generating: "جارٍ الإرسال…",
    noJobs: "لا مهام بعد في هذا المشروع.",
    jobsTitle: "المهام",
    simulatedBadge: "محاكاة — ليس توليدًا حقيقيًا",
    realBadge: "توليد حقيقي",
    rejection: "سبب الرفض",
    jobError: "سبب الفشل (رُدّ الرصيد)",
    videoLabel: "الفيديو الناتج",
    storyboard: "اللوحة القصصية",
    durationSeconds: "ث",
    selectProjectHint: "اختر مشروعًا من القائمة لعرض مهامه وإنشاء مهمة جديدة.",
    insufficient: "الرصيد غير كافٍ — كل مشهد يكلف رصيدًا واحدًا",

    ledgerTitle: "دفتر الرصيد",
    ledgerEmpty: "لا حركات بعد.",
    ledgerSignup: "مكافأة التسجيل",
    ledgerCharge: "تكلفة توليد",
    ledgerRefundFailed: "استرداد (فشل)",
    ledgerRefundCancelled: "استرداد (إلغاء)",
    ledgerOther: "حركة أخرى",
    cancel: "إلغاء",
    cancelling: "جارٍ الإلغاء…",

    status_pending: "في الانتظار",
    status_processing: "قيد التنفيذ",
    status_completed: "مكتملة",
    status_failed: "فاشلة",
    status_rejected: "مرفوضة",
    status_cancelled: "ملغاة",

    honestyTitle: "ما الذي يعمل فعلًا؟",
    honestyBody:
      "كل شيء هنا حقيقي: حسابات بـ Argon2id، رصيد قابل للتدقيق، تخزين فعلي، وتجميع MP4 بـ ffmpeg. المزود الافتراضي (mock) ينتج لوحات ومؤثرات وهمية موسومة بوضوح بـ SIMULATED. لتفعيل التوليد الحقيقي شغّل بوابة ai-gateway أو اضبط مزودًا متوافقًا مع OpenAI في ‎.env.",

    footerNote: "كل ناتج محاكاة موسوم بوضوح — والفشل يُرجِع رصيدك تلقائيًا.",
    featureHonest: "صدق مطلق: كل مخرج محاكاة يحمل وسم SIMULATED ظاهرًا",
    featureCredits: "رصيد قابل للتدقيق يُرد تلقائيًا عند أي فشل",
    featureSafety: "فلترة محتوى قبل التوليد وبعده",
  },
  en: {
    dir: "ltr",
    brand: "Tayf",
    tagline: "AI video generation studio",
    switchLabel: "العربية",

    loginTitle: "Sign in",
    registerTitle: "Create account",
    identifier: "Email or username",
    identifierPlaceholder: "you@example.com or username",
    email: "Email",
    username: "Username",
    password: "Password",
    login: "Sign in",
    register: "Create account",
    haveAccount: "I already have an account",
    needAccount: "I need an account",
    authErrorPrefix: "The request failed",

    logout: "Sign out",
    balance: "Balance",
    creditsUnit: "credits",
    serverError: "Cannot reach the server",

    projects: "Projects",
    newProject: "New project",
    projectName: "Project name",
    projectNamePlaceholder: "e.g. Café dawn commercial",
    projectDescription: "Description (optional)",
    projectDescriptionPlaceholder: "A short idea for this project",
    create: "Create",
    archive: "Archive",
    archivedTag: "archived",
    showArchived: "Show archived",
    noProjects: "No projects yet — create your first one.",
    jobsCount: "jobs",
    backToProjects: "All projects",

    newJob: "New generation job",
    promptLabel: "Describe the video you want",
    promptPlaceholder:
      "e.g. slow cinematic shot of an Arabic café at dawn, steam rising from the coffee cup",
    scenes: "Scenes",
    aspect: "Aspect",
    style: "Style",
    cost: "Cost",
    generate: "Generate",
    generating: "Submitting…",
    noJobs: "No jobs in this project yet.",
    jobsTitle: "Jobs",
    simulatedBadge: "SIMULATED — not real AI output",
    realBadge: "Real generation",
    rejection: "Rejection reason",
    jobError: "Failure reason (credits refunded)",
    videoLabel: "Resulting video",
    storyboard: "Storyboard",
    durationSeconds: "s",
    selectProjectHint: "Pick a project from the list to view its jobs and create a new one.",
    insufficient: "Insufficient balance — each scene costs 1 credit",

    ledgerTitle: "Credit ledger",
    ledgerEmpty: "No movements yet.",
    ledgerSignup: "Signup bonus",
    ledgerCharge: "Generation charge",
    ledgerRefundFailed: "Refund (failure)",
    ledgerRefundCancelled: "Refund (cancellation)",
    ledgerOther: "Other movement",
    cancel: "Cancel",
    cancelling: "Cancelling…",

    status_pending: "Pending",
    status_processing: "Processing",
    status_completed: "Completed",
    status_failed: "Failed",
    status_rejected: "Rejected",
    status_cancelled: "Cancelled",

    honestyTitle: "What actually works",
    honestyBody:
      "Everything here is real: Argon2id accounts, an auditable credit ledger, real storage and real MP4 composition via ffmpeg. The default provider (mock) fabricates storyboards and keyframes clearly stamped SIMULATED. To enable real generation, run the ai-gateway sidecar or configure an OpenAI-compatible provider in .env.",

    footerNote: "Every simulated output is clearly labeled — failures refund your credits automatically.",
    featureHonest: "Absolute honesty: simulated output is always stamped SIMULATED",
    featureCredits: "Auditable credits, refunded automatically on any failure",
    featureSafety: "Content safety screening before and after generation",
  },
};

export const STYLES = [
  "cinematic",
  "anime",
  "3d_render",
  "watercolor",
  "photorealistic",
  "noir",
] as const;

export const ASPECTS = ["16:9", "9:16", "1:1"] as const;
