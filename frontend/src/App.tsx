import { useEffect, useState } from "react";
import { copy, type Lang } from "./i18n/dictionary";
import {
  fetchVersion,
  logoutRequest,
  refreshSession,
  setToken,
  type TokenResponse,
} from "./services/api";
import AuthView from "./views/AuthView";
import StudioView from "./views/StudioView";

export default function App() {
  const [lang, setLang] = useState<Lang>(() =>
    localStorage.getItem("tayf.lang") === "en" ? "en" : "ar",
  );
  const t = copy[lang];

  // Persist the language choice and keep the document metadata in sync.
  useEffect(() => {
    localStorage.setItem("tayf.lang", lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = t.dir;
  }, [lang, t.dir]);

  const [ready, setReady] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [plan, setPlan] = useState("free");
  const [balance, setBalance] = useState(0);
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    // Public endpoint: powers the version chip in the footer; failure is benign.
    fetchVersion()
      .then((info) => setVersion(info.version))
      .catch(() => setVersion(null));
  }, []);

  useEffect(() => {
    // No token in localStorage: restore the session from the HttpOnly cookie.
    refreshSession()
      .then((data) => {
        setToken(data.access_token);
        setUsername(data.user.username);
        setPlan(data.user.plan ?? "free");
        setBalance(data.balance);
      })
      .catch(() => setToken(null))
      .finally(() => setReady(true));
  }, []);

  function handleAuthenticated(data: TokenResponse) {
    setUsername(data.user.username);
    setPlan(data.user.plan ?? "free");
    setBalance(data.balance);
  }

  function handleLogout() {
    logoutRequest()
      .catch(() => undefined)
      .finally(() => {
        setToken(null);
        setUsername(null);
        setPlan("free");
        setBalance(0);
      });
  }

  function handleLangSwitch() {
    setLang((current) => (current === "ar" ? "en" : "ar"));
  }

  if (!ready) {
    return <main className="auth-page loading" />;
  }

  return (
    <div dir={t.dir} lang={lang} className="app-root">
      {username ? (
        <StudioView
          lang={lang}
          username={username}
          plan={plan}
          balance={balance}
          onBalanceChange={setBalance}
          onLogout={handleLogout}
          onLangSwitch={handleLangSwitch}
        />
      ) : (
        <AuthView lang={lang} onAuthenticated={handleAuthenticated} onLangSwitch={handleLangSwitch} />
      )}
      <footer className="app-footer">
        <span className="footer-brand" dir="ltr">
          {t.brand}{version ? ` · v${version}` : ""}
        </span>
        <span className="muted">{t.footerNote}</span>
      </footer>
    </div>
  );
}
