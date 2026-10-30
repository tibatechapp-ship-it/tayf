import { useCallback, useState } from "react";

import { copy, type Lang } from "./i18n/dictionary";
import { ApiError, checkHealth, type HealthResponse } from "./services/api";

type Status = "idle" | "loading" | "success" | "error";

export default function App() {
  const [lang, setLang] = useState<Lang>("ar");
  const [status, setStatus] = useState<Status>("idle");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const t = copy[lang];
  const dir = lang === "ar" ? "rtl" : "ltr";

  const handleCheck = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const result = await checkHealth();
      setHealth(result);
      setStatus("success");
    } catch (caught) {
      setHealth(null);
      setError(caught instanceof ApiError ? caught.message : "خطأ غير متوقع");
      setStatus("error");
    }
  }, []);

  return (
    <div className="page" dir={dir} lang={lang}>
      <header className="header">
        <div>
          <h1>{t.brand}</h1>
          <p className="tagline">{t.tagline}</p>
          <p className="muted">{t.subtitle}</p>
        </div>
        <button
          type="button"
          className="ghost"
          onClick={() => setLang(lang === "ar" ? "en" : "ar")}
        >
          {t.switchLabel}
        </button>
      </header>

      <main className="card">
        <button
          type="button"
          className="primary"
          onClick={handleCheck}
          disabled={status === "loading"}
          data-testid="check-server"
        >
          {status === "loading" ? t.checking : t.check}
        </button>

        <p
          className={`status ${status}`}
          role="status"
          aria-live="polite"
          data-testid="health-status"
        >
          {status === "idle" && t.idle}
          {status === "loading" && t.checking}
          {status === "success" && t.success}
          {status === "error" && `${t.error}: ${error}`}
        </p>

        {health && (
          <section>
            <h2>{t.lastResponse}</h2>
            <pre data-testid="health-json">{JSON.stringify(health, null, 2)}</pre>
          </section>
        )}
      </main>

      <aside className="card honesty">
        <h2>{t.honestyTitle}</h2>
        <p className="muted">{t.honestyBody}</p>
      </aside>
    </div>
  );
}
