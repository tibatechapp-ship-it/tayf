import { useState } from "react";
import { copy, type Lang } from "../i18n/dictionary";
import {
  login as apiLogin,
  register as apiRegister,
  setToken,
  type TokenResponse,
} from "../services/api";

interface Props {
  lang: Lang;
  onAuthenticated: (data: TokenResponse) => void;
  onLangSwitch: () => void;
}

export default function AuthView({ lang, onAuthenticated, onLangSwitch }: Props) {
  const t = copy[lang];
  const [mode, setMode] = useState<"login" | "register">("register");
  const [identifier, setIdentifier] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const data =
        mode === "register"
          ? await apiRegister({ email, username, password })
          : await apiLogin({ username_or_email: identifier, password });
      setToken(data.access_token);
      onAuthenticated(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <header className="auth-header">
        <h1 className="brand">{t.brand}</h1>
        <p className="tagline">{t.tagline}</p>
        <button type="button" className="link" onClick={onLangSwitch}>
          {t.switchLabel}
        </button>
      </header>

      <section className="card auth-card" aria-label={mode === "login" ? t.loginTitle : t.registerTitle}>
        <div className="tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            className={mode === "register" ? "tab active" : "tab"}
            onClick={() => setMode("register")}
          >
            {t.registerTitle}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "tab active" : "tab"}
            onClick={() => setMode("login")}
          >
            {t.loginTitle}
          </button>
        </div>

        <form onSubmit={submit} className="stack">
          {mode === "register" ? (
            <>
              <label className="field">
                <span>{t.email}</span>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  dir="ltr"
                />
              </label>
              <label className="field">
                <span>{t.username}</span>
                <input
                  type="text"
                  required
                  minLength={3}
                  maxLength={32}
                  pattern="[a-zA-Z0-9_]+"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  dir="ltr"
                />
              </label>
            </>
          ) : (
            <label className="field">
              <span>{t.identifier}</span>
              <input
                type="text"
                required
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder={t.identifierPlaceholder}
                autoComplete="username"
                dir="ltr"
              />
            </label>
          )}

          <label className="field">
            <span>{t.password}</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              dir="ltr"
            />
          </label>

          {error && (
            <p className="panel panel-error" role="alert">
              {t.authErrorPrefix}: {error}
            </p>
          )}

          <button type="submit" className="primary" disabled={busy} data-testid="auth-submit">
            {busy ? t.generating : mode === "register" ? t.register : t.login}
          </button>
        </form>

        <button
          type="button"
          className="link center"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? t.needAccount : t.haveAccount}
        </button>
      </section>

      <section className="card honesty-card">
        <h2>{t.honestyTitle}</h2>
        <p>{t.honestyBody}</p>
      </section>
    </main>
  );
}
