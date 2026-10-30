/** Bilingual copy for the shell. Real i18n wiring (locale provider) comes in Stage 6. */

export type Lang = "ar" | "en";

interface Copy {
  brand: string;
  subtitle: string;
  check: string;
  checking: string;
  idle: string;
  success: string;
  error: string;
  lastResponse: string;
  honestyTitle: string;
  honestyBody: string;
  switchLabel: string;
}

export const copy: Record<Lang, Copy> = {
  ar: {
    brand: "VisionForge Studio",
    subtitle: "هيكل التطبيق الأولي — المرحلة 1",
    check: "فحص اتصال الخادم",
    checking: "جارٍ الفحص…",
    idle: "لم يتم إجراء فحص بعد",
    success: "الاتصال بالخادم ناجح",
    error: "فشل الاتصال بالخادم",
    lastResponse: "آخر استجابة من الخادم",
    honestyTitle: "حالة الوظائف",
    honestyBody:
      "هذه المرحلة تُثبت الربط بين الواجهة والخادم فقط. لا يوجد حتى الآن توليد فيديو أو حساب مستخدم — أي زر آخر لم يُبنَ بعد.",
    switchLabel: "English",
  },
  en: {
    brand: "VisionForge Studio",
    subtitle: "Application skeleton — Stage 1",
    check: "Check server connection",
    checking: "Checking…",
    idle: "No check performed yet",
    success: "Server connection succeeded",
    error: "Server connection failed",
    lastResponse: "Last server response",
    honestyTitle: "What actually works",
    honestyBody:
      "This stage only proves the frontend ↔ backend wiring. There is no video generation and no user account yet — nothing else has been built.",
    switchLabel: "العربية",
  },
};
