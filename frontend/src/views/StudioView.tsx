import { useCallback, useEffect, useRef, useState } from "react";
import { ASPECTS, copy, STYLES, type Lang } from "../i18n/dictionary";
import {
  archiveProject,
  createJob,
  createProject,
  fetchCredits,
  fetchJob,
  getToken,
  listJobs,
  listProjects,
  type Job,
  type Project,
} from "../services/api";

interface Props {
  lang: Lang;
  username: string;
  balance: number;
  onBalanceChange: (balance: number) => void;
  onLogout: () => void;
  onLangSwitch: () => void;
}

const ACTIVE_STATUSES = new Set(["pending", "processing"]);
const POLL_MS = 4000;

export default function StudioView({
  lang,
  username,
  balance,
  onBalanceChange,
  onLogout,
  onLangSwitch,
}: Props) {
  const t = copy[lang];
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // project creation form
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);

  // job creation form
  const [prompt, setPrompt] = useState("");
  const [numScenes, setNumScenes] = useState(4);
  const [aspect, setAspect] = useState<string>("16:9");
  const [style, setStyle] = useState<string>("cinematic");
  const [creatingJob, setCreatingJob] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);

  const token = getToken() ?? "";
  const pollTimer = useRef<number | null>(null);

  const refreshProjects = useCallback(
    async (keepSelection: boolean) => {
      try {
        const data = await listProjects(token, { include_archived: showArchived });
        setProjects(data);
        setLoadError(null);
        setSelectedId((current) => {
          if (keepSelection && current && data.some((p) => p.id === current)) return current;
          return data.find((p) => p.status !== "archived")?.id ?? null;
        });
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : String(err));
      }
    },
    [token, showArchived],
  );

  const refreshJobs = useCallback(async () => {
    if (!selectedId) return;
    try {
      const data = await listJobs(token, selectedId);
      setJobs(data);
      const active = data.some((job) => ACTIVE_STATUSES.has(job.status));
      if (!active) {
        const credits = await fetchCredits(token);
        onBalanceChange(credits.balance);
      }
    } catch {
      /* transient poll errors are non-fatal; the next tick retries */
    }
  }, [token, selectedId, onBalanceChange]);

  useEffect(() => {
    void refreshProjects(false);
  }, [refreshProjects]);

  useEffect(() => {
    if (!selectedId) {
      setJobs([]);
      return;
    }
    void refreshJobs();
    if (pollTimer.current) window.clearInterval(pollTimer.current);
    pollTimer.current = window.setInterval(() => {
      void refreshJobs();
    }, POLL_MS);
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
    };
  }, [selectedId, refreshJobs]);

  async function handleCreateProject(event: React.FormEvent) {
    event.preventDefault();
    if (!newName.trim() || creatingProject) return;
    setCreatingProject(true);
    try {
      const project = await createProject(token, {
        name: newName,
        description: newDescription.trim() ? newDescription : null,
      });
      setNewName("");
      setNewDescription("");
      await refreshProjects(true);
      setSelectedId(project.id);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingProject(false);
    }
  }

  async function handleArchive(projectId: string) {
    try {
      await archiveProject(token, projectId);
      await refreshProjects(true);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleCreateJob(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedId || !prompt.trim() || creatingJob) return;
    setCreatingJob(true);
    setJobError(null);
    try {
      await createJob(token, selectedId, {
        prompt,
        num_scenes: numScenes,
        aspect,
        style,
      });
      setPrompt("");
      onBalanceChange(balance - numScenes);
      await refreshJobs();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setJobError(message.includes("رصيد") || message.toLowerCase().includes("credit")
        ? t.insufficient
        : message);
    } finally {
      setCreatingJob(false);
    }
  }

  const selected = projects.find((p) => p.id === selectedId) ?? null;

  return (
    <main className="studio-page">
      <header className="topbar" data-testid="topbar">
        <div className="brand-row">
          <h1 className="brand">{t.brand}</h1>
          <span className="username" dir="ltr">@{username}</span>
        </div>
        <div className="topbar-actions">
          <span className="balance-chip" title={t.balance} data-testid="balance">
            {t.balance}: <strong>{balance}</strong> {t.creditsUnit}
          </span>
          <button type="button" className="ghost" onClick={onLangSwitch}>
            {t.switchLabel}
          </button>
          <button type="button" className="ghost" onClick={onLogout}>
            {t.logout}
          </button>
        </div>
      </header>

      {loadError && (
        <p className="panel panel-error" role="alert">
          {loadError}
        </p>
      )}

      <div className="columns">
        <aside className="sidebar">
          <h2>{t.projects}</h2>
          <form onSubmit={handleCreateProject} className="stack compact">
            <label className="field">
              <span>{t.projectName}</span>
              <input
                type="text"
                required
                maxLength={100}
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                data-testid="project-name"
                placeholder={t.projectNamePlaceholder}
              />
            </label>
            <label className="field">
              <span>{t.projectDescription}</span>
              <input
                type="text"
                maxLength={500}
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder={t.projectDescriptionPlaceholder}
              />
            </label>
            <button type="submit" className="primary" disabled={creatingProject} data-testid="project-submit">
              {t.newProject}
            </button>
          </form>

          <label className="check">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
            <span>{t.showArchived}</span>
          </label>

          <ul className="project-list">
            {projects.length === 0 && <li className="empty">{t.noProjects}</li>}
            {projects.map((project) => (
              <li key={project.id} className={project.id === selectedId ? "selected" : ""}>
                <button
                  type="button"
                  className="project-button"
                  onClick={() => setSelectedId(project.id)}
                >
                  <span className="project-name">{project.name}</span>
                  <span className="project-meta">
                    {project.status === "archived" && (
                      <em className="tag archived">{t.archivedTag}</em>
                    )}
                    {project.job_count} {t.jobsCount}
                  </span>
                </button>
                {project.status !== "archived" && (
                  <button
                    type="button"
                    className="link danger"
                    onClick={() => void handleArchive(project.id)}
                  >
                    {t.archive}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </aside>

        <section className="content">
          {!selected && <p className="hint">{t.selectProjectHint}</p>}

          {selected && (
            <>
              <h2>
                {selected.name}
                {selected.description && <small className="muted"> — {selected.description}</small>}
              </h2>

              <form onSubmit={handleCreateJob} className="card stack">
                <h3>{t.newJob}</h3>
                <label className="field">
                  <span>{t.promptLabel}</span>
                  <textarea
                    required
                    minLength={3}
                    maxLength={2000}
                    rows={3}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    data-testid="job-prompt"
                    placeholder={t.promptPlaceholder}
                  />
                </label>
                <div className="row">
                  <label className="field">
                    <span>{t.scenes}</span>
                    <input
                      type="number"
                      min={2}
                      max={8}
                      value={numScenes}
                      onChange={(e) => setNumScenes(Number(e.target.value))}
                    />
                  </label>
                  <label className="field">
                    <span>{t.aspect}</span>
                    <select value={aspect} onChange={(e) => setAspect(e.target.value)} dir="ltr">
                      {ASPECTS.map((a) => (
                        <option key={a} value={a}>
                          {a}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>{t.style}</span>
                    <select value={style} onChange={(e) => setStyle(e.target.value)} dir="ltr">
                      {STYLES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>
                  <span className="cost">
                    {t.cost}: {numScenes}
                  </span>
                </div>

                {jobError && (
                  <p className="panel panel-error" role="alert">
                    {jobError}
                  </p>
                )}

                <button type="submit" className="primary" disabled={creatingJob} data-testid="job-submit">
                  {creatingJob ? t.generating : t.generate}
                </button>
              </form>

              <h3 className="jobs-title">{t.jobsTitle}</h3>
              {jobs.length === 0 && <p className="hint">{t.noJobs}</p>}
              <ul className="job-list" data-testid="job-list">
                {jobs.map((job) => (
                  <li key={job.id} className={`card job status-${job.status}`}>
                    <div className="job-head">
                      <span className={`chip status-${job.status}`}>
                        {t[`status_${job.status}` as const]}
                      </span>
                      {(ACTIVE_STATUSES.has(job.status)) && <span className="spinner" aria-hidden="true" />}
                      <span className="job-provider" dir="ltr">
                        {job.provider} · {job.aspect} · {job.style}
                      </span>
                      <span className={job.simulated ? "tag simulated" : "tag real"}>
                        {job.simulated ? t.simulatedBadge : t.realBadge}
                      </span>
                    </div>

                    <p className="job-prompt">{job.prompt}</p>

                    {job.status === "rejected" && job.rejection_reason && (
                      <p className="panel panel-warn">
                        <strong>{t.rejection}:</strong> {job.rejection_reason}
                      </p>
                    )}
                    {job.status === "failed" && job.error_message && (
                      <p className="panel panel-error">
                        <strong>{t.jobError}:</strong> {job.error_message}
                      </p>
                    )}

                    {job.output_url && (
                      <figure className="video-figure">
                        <video controls preload="metadata" src={job.output_url} data-testid="job-video" />
                        <figcaption dir="ltr">
                          {t.videoLabel} · {job.video_size_bytes
                            ? `${Math.round(job.video_size_bytes / 1024)} KB`
                            : ""}
                          {job.duration_seconds ? ` · ${job.duration_seconds}${t.durationSeconds}` : ""}
                        </figcaption>
                      </figure>
                    )}

                    {job.scenes.length > 0 && (
                      <div className="scenes">
                        <h4>{t.storyboard}</h4>
                        <ol>
                          {job.scenes.map((scene) => (
                            <li key={scene.index}>
                              {scene.image_url && (
                                <img
                                  src={scene.image_url}
                                  alt={`scene ${scene.index}`}
                                  loading="lazy"
                                />
                              )}
                              <p>
                                {scene.description}{" "}
                                <em dir="ltr">
                                  ({scene.duration_seconds}
                                  {t.durationSeconds})
                                </em>
                              </p>
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </main>
  );
}

/** Single-job poll helper kept for future WebSocket replacement (Stage 6). */
export async function pollJobUntilTerminal(
  token: string,
  jobId: string,
  onUpdate: (job: Job) => void,
  timeoutMs = 300_000,
): Promise<Job> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const job = await fetchJob(token, jobId);
    onUpdate(job);
    if (!ACTIVE_STATUSES.has(job.status) || Date.now() > deadline) return job;
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}
