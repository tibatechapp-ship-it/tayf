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
  topUp: string;
  topUpTitle: string;
  topUpHint: string;
  topUpBuy: string;
  topUpBusy: string;
  topUpUnavailable: string;
  topUpErrorPrefix: string;
  close: string;
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
  progressLabel: string;
  stageQueued: string;
  stageProcessing: string;
  stageStoryboard: string;
  stageSafety: string;
  stageKeyframes: string;
  stageComposing: string;
  stageStoring: string;
  stageCompleted: string;
  stageFailed: string;
  stageRejected: string;
  stageCancelled: string;

  // verifiable proof
  proofTitle: string;
  proofShow: string;
  proofHide: string;
  proofVerified: string;
  proofTampered: string;
  proofModel: string;
  proofRuntime: string;
  proofCost: string;
  proofHash: string;
  proofEmpty: string;
  proofAllowed: string;
  proofBlocked: string;
  proofLoading: string;
  proofError: string;

  // human approval gates
  requireApprovals: string;
  approvalTitle: string;
  approvalStoryboard: string;
  approvalAssets: string;
  approvalNote: string;
  approvalApprove: string;
  approvalReject: string;
  approvalBusy: string;
  approvalRejected: string;

  // cost dashboard
  costTitle: string;
  costHint: string;
  costCharged: string;
  costRefunded: string;
  costNet: string;
  costJobs: string;
  costScenes: string;
  costRuntime: string;
  costStages: string;
  costModels: string;
  costStage: string;
  costEvents: string;
  costCredits: string;
  costDuration: string;
  costProvider: string;
  costEmpty: string;
  costLoading: string;
  costRefresh: string;
  costAttribution: string;

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
    topUp: "شحن الرصيد",
    topUpTitle: "اختر حزمة رصيد",
    topUpHint: "تتم إضافة الرصيد تلقائيًا بعد تأكيد Stripe للدفع.",
    topUpBuy: "دفع",
    topUpBusy: "جارٍ فتح صفحة الدفع…",
    topUpUnavailable: "المدفوعات غير مفعّلة على هذا الخادم",
    topUpErrorPrefix: "تعذّر بدء الدفع",
    close: "إغلاق",
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
    progressLabel: "التقدم",
    stageQueued: "في الانتظار",
    stageProcessing: "قيد التنفيذ",
    stageStoryboard: "اللوحة القصصية",
    stageSafety: "فحص المحتوى",
    stageKeyframes: "الإطارات المفتاحية",
    stageComposing: "تجميع الفيديو",
    stageStoring: "حفظ النتائج",
    stageCompleted: "مكتملة",
    stageFailed: "فاشلة",
    stageRejected: "مرفوضة",
    stageCancelled: "ملغاة",

    proofTitle: "إثبات المراحل",
    proofShow: "عرض الإثبات",
    proofHide: "إخفاء الإثبات",
    proofVerified: "سلسلة التحقق سليمة",
    proofTampered: "تحذير: تعارض في سلسلة الإثبات",
    proofModel: "النموذج",
    proofRuntime: "الزمن",
    proofCost: "التكلفة",
    proofHash: "البصمة",
    proofEmpty: "لا توجد مراحل مسجلة لهذه المهمة بعد.",
    proofAllowed: "نجح التحقق",
    proofBlocked: "تم المنع",
    proofLoading: "جارٍ تحميل الإثبات…",
    proofError: "تعذّر تحميل الإثبات",

    requireApprovals: "مراجعة بشرية قبل كل مرحلة",
    approvalTitle: "مراجعة المرحلة",
    approvalStoryboard: "مراجعة النص والوصف",
    approvalAssets: "مراجعة الصور والفيديو",
    approvalNote: "ملاحظة (اختياري)",
    approvalApprove: "موافقة ومتابعة",
    approvalReject: "رفض وإلغاء المهمة",
    approvalBusy: "جارٍ الإرسال…",
    approvalRejected: "تم رفض المرحلة",

    costTitle: "لوحة التكاليف",
    costHint: "الرصيد هو وحدة الدفع؛ الأرقام من دفتر الرصيد وإثبات المراحل.",
    costCharged: "المدفوع",
    costRefunded: "المسترد",
    costNet: "الصافي",
    costJobs: "المهام المحللة",
    costScenes: "المشاهد المولدة",
    costRuntime: "زمن المعالجة",
    costStages: "التكلفة حسب المرحلة",
    costModels: "استهلاك النماذج",
    costStage: "المرحلة",
    costEvents: "المراحل المسجلة",
    costCredits: "الرصيد",
    costDuration: "الزمن",
    costProvider: "المزود",
    costEmpty: "لا توجد بيانات تكلفة بعد.",
    costLoading: "جارٍ تحميل التكاليف…",
    costRefresh: "تحديث التكاليف",
    costAttribution: "تُنسب تكلفة كل مشهد إلى مرحلة توليد المشهد (صور أو فيديو).",

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
    topUp: "Top up",
    topUpTitle: "Choose a credit package",
    topUpHint: "Credits are added automatically after Stripe confirms the payment.",
    topUpBuy: "Pay",
    topUpBusy: "Opening checkout…",
    topUpUnavailable: "Payments are not enabled on this server",
    topUpErrorPrefix: "Could not start checkout",
    close: "Close",
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
    progressLabel: "Progress",
    stageQueued: "Queued",
    stageProcessing: "Starting",
    stageStoryboard: "Storyboard",
    stageSafety: "Safety check",
    stageKeyframes: "Keyframes",
    stageComposing: "Composing video",
    stageStoring: "Saving results",
    stageCompleted: "Completed",
    stageFailed: "Failed",
    stageRejected: "Rejected",
    stageCancelled: "Cancelled",

    proofTitle: "Stage proof",
    proofShow: "Show proof",
    proofHide: "Hide proof",
    proofVerified: "Verification chain intact",
    proofTampered: "Warning: proof chain mismatch",
    proofModel: "Model",
    proofRuntime: "Runtime",
    proofCost: "Cost",
    proofHash: "Hash",
    proofEmpty: "No stages recorded for this job yet.",
    proofAllowed: "Verified",
    proofBlocked: "Blocked",
    proofLoading: "Loading proof…",
    proofError: "Could not load proof",

    requireApprovals: "Human review before each stage",
    approvalTitle: "Stage review",
    approvalStoryboard: "Review text and prompts",
    approvalAssets: "Review images and video",
    approvalNote: "Note (optional)",
    approvalApprove: "Approve and continue",
    approvalReject: "Reject and cancel job",
    approvalBusy: "Sending…",
    approvalRejected: "Stage rejected",

    costTitle: "Cost dashboard",
    costHint: "Credits are the settlement unit; figures come from the ledger and stage proof.",
    costCharged: "Charged",
    costRefunded: "Refunded",
    costNet: "Net",
    costJobs: "Jobs analyzed",
    costScenes: "Scenes generated",
    costRuntime: "Processing time",
    costStages: "Cost by stage",
    costModels: "Model consumption",
    costStage: "Stage",
    costEvents: "Stage events",
    costCredits: "Credits",
    costDuration: "Time",
    costProvider: "Provider",
    costEmpty: "No cost data yet.",
    costLoading: "Loading costs…",
    costRefresh: "Refresh costs",
    costAttribution: "Each scene's credits are attributed to its generation stage (images or video).",

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
