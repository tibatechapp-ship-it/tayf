import { useEffect, useState } from "react";
import { copy, type Lang } from "./i18n/dictionary";
import {
  fetchMe,
  fetchVersion,
  getToken,
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
  const [balance, setBalance] = useState(0);
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    // Public endpoint: powers the version chip in the footer; failure is benign.
    fetchVersion()
      .then((info) => setVersion(info.version))
      .catch(() => setVersion(null));
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setReady(true);
      return;
    }
    fetchMe(token)
      .then((me) => {
        setUsername(me.user.username);
        setBalance(me.balance);
      })
      .catch(() => setToken(null))
      .finally(() => setReady(true));
  }, []);

  function handleAuthenticated(data: TokenResponse) {
    setUsername(data.user.username);
    setBalance(data.balance);
  }

  function handleLogout() {
    setToken(null);
    setUsername(null);
    setBalance(0);
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
          {t.brand} Studio{version ? ` · v${version}` : ""}
        </span>
        <span className="muted">{t.footerNote}</span>
      </footer>
    </div>
  );
}
