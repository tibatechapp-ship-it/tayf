import { useCallback, useEffect, useRef, useState } from "react";
import { ASPECTS, copy, STYLES, type Lang } from "../i18n/dictionary";
import {
  archiveProject,
  cancelJob,
  createJob,
  decideJobApproval,
  createProject,
  createTopUpCheckout,
  fetchCostReport,
  fetchCredits,
  fetchJob,
  fetchJobProof,
  fetchTopUpPackages,
  fetchStreamTicket,
  getToken,
  listJobs,
  listProjects,
  subscribeJobEvents,
  type ApprovalGate,
  type CostReport,
  type Job,
  type JobProof,
  type JobProgressEvent,
  type LedgerEntry,
  type Project,
  type TopUpPackage,
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
  const [requireApprovals, setRequireApprovals] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[] | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [topUpPackages, setTopUpPackages] = useState<TopUpPackage[]>([]);
  const [topUpConfigured, setTopUpConfigured] = useState(false);
  const [showTopUp, setShowTopUp] = useState(false);
  const [topUpBusy, setTopUpBusy] = useState(false);
  const [topUpError, setTopUpError] = useState<string | null>(null);

  const [approvalBusyId, setApprovalBusyId] = useState<string | null>(null);
  const [approvalNotes, setApprovalNotes] = useState<Record<string, string>>({});
  const [approvalError, setApprovalError] = useState<string | null>(null);

  const [proofOpenId, setProofOpenId] = useState<string | null>(null);
  const [proofs, setProofs] = useState<Record<string, JobProof>>({});
  const [proofLoadingId, setProofLoadingId] = useState<string | null>(null);
  const [proofError, setProofError] = useState<string | null>(null);

  const [costReport, setCostReport] = useState<CostReport | null>(null);
  const [costLoading, setCostLoading] = useState(false);
  const [costError, setCostError] = useState<string | null>(null);

  const token = getToken() ?? "";
  const pollTimer = useRef<number | null>(null);
  const streamClosers = useRef<Map<string, () => void>>(new Map());
  const pendingTickets = useRef<Set<string>>(new Set());

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

  const refreshCosts = useCallback(async () => {
    setCostLoading(true);
    try {
      const report = await fetchCostReport(token);
      setCostReport(report);
      setCostError(null);
    } catch (err) {
      setCostError(err instanceof Error ? err.message : String(err));
    } finally {
      setCostLoading(false);
    }
  }, [token]);

  const refreshJobs = useCallback(async () => {
    if (!selectedId) return;
    try {
      const data = await listJobs(token, selectedId);
      setJobs(data);
      const active = data.some((job) => ACTIVE_STATUSES.has(job.status));
      if (!active) {
        const credits = await fetchCredits(token);
        onBalanceChange(credits.balance);
        void refreshCosts();
      }
    } catch {
      /* transient poll errors are non-fatal; the next tick retries */
    }
  }, [token, selectedId, onBalanceChange, refreshCosts]);

  const refreshLedger = useCallback(async () => {
    try {
      const credits = await fetchCredits(token);
      setLedger(credits.entries);
    } catch {
      /* the ledger is supplementary — never block the studio on it */
    }
  }, [token]);

  const closeStream = useCallback((jobId: string) => {
    streamClosers.current.get(jobId)?.();
    streamClosers.current.delete(jobId);
  }, []);

  const applyProgress = useCallback(
    (event: JobProgressEvent) => {
      setJobs((current) =>
        current.map((job) =>
          job.id === event.job_id
            ? {
                ...job,
                status: event.status,
                progress: event.progress,
                stage: event.stage,
                error_message: event.error_message,
                rejection_reason: event.rejection_reason,
                output_url: event.output_url,
                thumbnail_url: event.thumbnail_url,
                completed_at: event.completed_at,
              }
            : job,
        ),
      );
      if (!ACTIVE_STATUSES.has(event.status)) {
        closeStream(event.job_id);
        void refreshJobs();
        void refreshLedger();
      }
    },
    [closeStream, refreshJobs, refreshLedger],
  );

  const syncStreams = useCallback(
    (activeJobs: Job[]) => {
      const wanted = new Set(activeJobs.map((job) => job.id));
      for (const [jobId, close] of streamClosers.current) {
        if (!wanted.has(jobId)) {
          close();
          streamClosers.current.delete(jobId);
        }
      }
      for (const job of activeJobs) {
        if (streamClosers.current.has(job.id) || pendingTickets.current.has(job.id)) continue;
        pendingTickets.current.add(job.id);
        void fetchStreamTicket(token, job.id)
          .then(({ ticket }) => {
            const close = subscribeJobEvents(job.id, ticket, applyProgress, () =>
              closeStream(job.id),
            );
            streamClosers.current.set(job.id, close);
          })
          .catch(() => {
            /* the 4s poll is the fallback when tickets cannot be minted */
          })
          .finally(() => {
            pendingTickets.current.delete(job.id);
          });
      }
    },
    [token, applyProgress, closeStream],
  );

  useEffect(() => {
    void refreshProjects(false);
    void refreshLedger();
    void refreshCosts();
  }, [refreshProjects, refreshLedger, refreshCosts]);

  useEffect(() => {
    if (!selectedId) {
      setJobs([]);
      for (const jobId of [...streamClosers.current.keys()]) closeStream(jobId);
      return;
    }
    void refreshJobs();
    if (pollTimer.current) window.clearInterval(pollTimer.current);
    pollTimer.current = window.setInterval(() => {
      void refreshJobs();
    }, POLL_MS);
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
      for (const jobId of [...streamClosers.current.keys()]) closeStream(jobId);
    };
  }, [selectedId, refreshJobs, closeStream]);

  useEffect(() => {
    syncStreams(jobs.filter((job) => ACTIVE_STATUSES.has(job.status)));
  }, [jobs, syncStreams]);

  useEffect(() => {
    let alive = true;
    fetchTopUpPackages()
      .then((data) => {
        if (!alive) return;
        setTopUpPackages(data.packages);
        setTopUpConfigured(data.configured);
      })
      .catch(() => {
        if (alive) setTopUpConfigured(false);
      });
    return () => {
      alive = false;
    };
  }, []);

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
        require_approvals: requireApprovals,
      });
      setPrompt("");
      onBalanceChange(balance - numScenes);
      await refreshJobs();
      void refreshLedger();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setJobError(message.includes("رصيد") || message.toLowerCase().includes("credit")
        ? t.insufficient
        : message);
    } finally {
      setCreatingJob(false);
    }
  }

  async function handleCancel(jobId: string) {
    if (cancellingId) return;
    setCancellingId(jobId);
    try {
      await cancelJob(token, jobId);
      await refreshJobs();
      void refreshLedger();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setCancellingId(null);
    }
  }

  async function handleApproval(jobId: string, decision: "approve" | "reject") {
    if (approvalBusyId) return;
    setApprovalBusyId(jobId);
    setApprovalError(null);
    try {
      await decideJobApproval(token, jobId, decision, approvalNotes[jobId]);
      await refreshJobs();
      void refreshLedger();
    } catch (err) {
      setApprovalError(err instanceof Error ? err.message : String(err));
    } finally {
      setApprovalBusyId(null);
    }
  }

  async function handleToggleProof(jobId: string) {
    if (proofOpenId === jobId) {
      setProofOpenId(null);
      return;
    }
    setProofOpenId(jobId);
    setProofError(null);
    if (proofs[jobId]) return;
    setProofLoadingId(jobId);
    try {
      const proof = await fetchJobProof(token, jobId);
      setProofs((current) => ({ ...current, [jobId]: proof }));
    } catch (err) {
      setProofError(err instanceof Error ? err.message : String(err));
    } finally {
      setProofLoadingId(null);
    }
  }

  async function handleTopUp(packageName: string) {
    if (topUpBusy) return;
    setTopUpBusy(true);
    setTopUpError(null);
    try {
      const checkout = await createTopUpCheckout(token, packageName);
      window.location.assign(checkout.checkout_url);
    } catch (err) {
      setTopUpError(
        `${t.topUpErrorPrefix}: ${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      setTopUpBusy(false);
    }
  }

  function ledgerReason(reason: string): string {
    const map: Record<string, string> = {
      signup_bonus: t.ledgerSignup,
      job_charge: t.ledgerCharge,
      refund_job_failed: t.ledgerRefundFailed,
      refund_job_cancelled: t.ledgerRefundCancelled,
    };
    return map[reason] ?? `${t.ledgerOther} (${reason})`;
  }

  function stageLabel(stage: string): string {
    const map: Record<string, string> = {
      queued: t.stageQueued,
      processing: t.stageProcessing,
      storyboard: t.stageStoryboard,
      safety: t.stageSafety,
      keyframes: t.stageKeyframes,
      composing: t.stageComposing,
      storing: t.stageStoring,
      completed: t.stageCompleted,
      failed: t.stageFailed,
      rejected: t.stageRejected,
      cancelled: t.stageCancelled,
    };
    return map[stage] ?? stage;
  }

  function proofStageLabel(stage: string): string {
    const extra: Record<string, string> = {
      safety_text: t.stageSafety,
      safety_artifact: t.stageSafety,
      video: t.stageComposing,
      compose: t.stageComposing,
      store: t.stageStoring,
    };
    return extra[stage] ?? stageLabel(stage);
  }

  function formatDuration(ms: number): string {
    return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms} ms`;
  }

  function ApprovalReview({ gate }: { gate: ApprovalGate }) {
    const rawScenes = Array.isArray(gate.review.scenes) ? gate.review.scenes : [];
    const scenes = rawScenes as Array<{
      index?: unknown;
      description?: unknown;
      image_prompt?: unknown;
      image_url?: unknown;
    }>;
    const videoUrl =
      typeof gate.review.video_url === "string" ? (gate.review.video_url as string) : null;
    const thumbUrl =
      typeof gate.review.thumbnail_url === "string" ? (gate.review.thumbnail_url as string) : null;
    return (
      <>
        <p className="hint">
          {gate.stage === "storyboard" ? t.approvalStoryboard : t.approvalAssets}
        </p>
        {thumbUrl && <img className="approval-thumb" src={thumbUrl} alt="review" loading="lazy" />}
        {videoUrl && <video className="approval-video" controls preload="metadata" src={videoUrl} />}
        <ol className="approval-scenes">
          {scenes.map((scene, index) => {
            const imageUrl = typeof scene.image_url === "string" ? scene.image_url : null;
            return (
              <li key={typeof scene.index === "number" ? scene.index : index}>
                {imageUrl && <img src={imageUrl} alt={`scene ${String(scene.index ?? index)}`} loading="lazy" />}
                {typeof scene.description === "string" && <p>{scene.description}</p>}
                {typeof scene.image_prompt === "string" && (
                  <p className="hint" dir="ltr">
                    {scene.image_prompt}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      </>
    );
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
          {topUpConfigured && (
            <button
              type="button"
              className="ghost"
              onClick={() => setShowTopUp(true)}
              data-testid="topup-open"
            >
              {t.topUp}
            </button>
          )}
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

          <details className="ledger" data-testid="ledger">
            <summary>{t.ledgerTitle}</summary>
            {ledger !== null && ledger.length === 0 && (
              <p className="hint">{t.ledgerEmpty}</p>
            )}
            <ul className="ledger-list">
              {(ledger ?? []).map((entry) => (
                <li key={entry.id}>
                  <span
                    className={entry.delta >= 0 ? "delta pos" : "delta neg"}
                    dir="ltr"
                  >
                    {entry.delta > 0 ? `+${entry.delta}` : entry.delta}
                  </span>
                  <span className="ledger-reason">{ledgerReason(entry.reason)}</span>
                  <span className="ledger-balance" dir="ltr" title={t.balance}>
                    = {entry.balance_after}
                  </span>
                </li>
              ))}
            </ul>
          </details>

          <details className="cost-dashboard" data-testid="cost-dashboard">
            <summary>{t.costTitle}</summary>
            <p className="hint">{t.costHint}</p>
            <button
              type="button"
              className="link"
              onClick={() => void refreshCosts()}
              disabled={costLoading}
              data-testid="cost-refresh"
            >
              {costLoading ? t.costLoading : t.costRefresh}
            </button>
            {costError && <p className="panel panel-error">{costError}</p>}
            {costReport && (
              <>
                <dl className="cost-kpis">
                  <div>
                    <dt>{t.costCharged}</dt>
                    <dd dir="ltr">{costReport.credits_charged} {t.creditsUnit}</dd>
                  </div>
                  <div>
                    <dt>{t.costRefunded}</dt>
                    <dd dir="ltr">{costReport.credits_refunded} {t.creditsUnit}</dd>
                  </div>
                  <div>
                    <dt>{t.costNet}</dt>
                    <dd dir="ltr">{costReport.credits_net} {t.creditsUnit}</dd>
                  </div>
                  <div>
                    <dt>{t.costJobs}</dt>
                    <dd dir="ltr">{costReport.jobs_analyzed}</dd>
                  </div>
                  <div>
                    <dt>{t.costScenes}</dt>
                    <dd dir="ltr">{costReport.scenes_generated}</dd>
                  </div>
                  <div>
                    <dt>{t.costRuntime}</dt>
                    <dd dir="ltr">{formatDuration(costReport.total_duration_ms)}</dd>
                  </div>
                </dl>
                <p className="hint cost-attribution">{t.costAttribution}</p>

                <h4>{t.costStages}</h4>
                {costReport.stages.length === 0 && <p className="hint">{t.costEmpty}</p>}
                {costReport.stages.length > 0 && (
                  <table className="cost-table">
                    <thead>
                      <tr>
                        <th>{t.costStage}</th>
                        <th>{t.costEvents}</th>
                        <th>{t.costDuration}</th>
                        <th>{t.costCredits}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {costReport.stages.map((stage) => (
                        <tr key={stage.stage}>
                          <td>{proofStageLabel(stage.stage)}</td>
                          <td dir="ltr">{stage.events}</td>
                          <td dir="ltr">{formatDuration(stage.duration_ms)}</td>
                          <td dir="ltr">{stage.credits}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                <h4>{t.costModels}</h4>
                {costReport.models.length === 0 && <p className="hint">{t.costEmpty}</p>}
                {costReport.models.length > 0 && (
                  <table className="cost-table">
                    <thead>
                      <tr>
                        <th>{t.costProvider}</th>
                        <th>{t.proofModel}</th>
                        <th>{t.costDuration}</th>
                        <th>{t.costCredits}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {costReport.models.map((model) => (
                        <tr
                          key={`${model.provider}:${model.model_version}:${model.simulated}`}
                        >
                          <td>
                            {model.provider}
                            <em className={model.simulated ? "tag simulated" : "tag real"}>
                              {model.simulated ? t.simulatedBadge : t.realBadge}
                            </em>
                          </td>
                          <td dir="ltr">{model.model_version || "-"}</td>
                          <td dir="ltr">{formatDuration(model.duration_ms)}</td>
                          <td dir="ltr">{model.credits}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </details>
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

                <label className="approval-check">
                  <input
                    type="checkbox"
                    checked={requireApprovals}
                    onChange={(e) => setRequireApprovals(e.target.checked)}
                    data-testid="require-approvals"
                  />
                  <span>{t.requireApprovals}</span>
                </label>

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
                {jobs.map((job) => {
                  const proof = proofs[job.id];
                  return (
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
                      <button
                        type="button"
                        className="link proof-btn"
                        onClick={() => void handleToggleProof(job.id)}
                        data-testid={`proof-toggle-${job.id}`}
                      >
                        {proofOpenId === job.id ? t.proofHide : t.proofShow}
                      </button>
                      {ACTIVE_STATUSES.has(job.status) && (
                        <button
                          type="button"
                          className="link danger cancel-btn"
                          onClick={() => void handleCancel(job.id)}
                          disabled={cancellingId !== null}
                          data-testid={`cancel-${job.id}`}
                        >
                          {cancellingId === job.id ? t.cancelling : t.cancel}
                        </button>
                      )}
                    </div>

                    {ACTIVE_STATUSES.has(job.status) && (
                      <div
                        className="job-progress"
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={job.progress}
                        data-testid={`progress-${job.id}`}
                      >
                        <div className="job-progress-track">
                          <div className="job-progress-fill" style={{ width: `${job.progress}%` }} />
                        </div>
                        <span className="job-progress-label" dir="ltr">
                          {t.progressLabel}: {job.progress}% · {stageLabel(job.stage)}
                        </span>
                      </div>
                    )}

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

                    {job.pending_approval && job.pending_approval.decision === null && (
                      <section className="approval-panel" data-testid={`approval-${job.id}`}>
                        <h4>{t.approvalTitle}</h4>
                        <ApprovalReview gate={job.pending_approval} />
                        <label className="field">
                          <span>{t.approvalNote}</span>
                          <input
                            type="text"
                            maxLength={1000}
                            value={approvalNotes[job.id] ?? ""}
                            onChange={(e) =>
                              setApprovalNotes((current) => ({ ...current, [job.id]: e.target.value }))
                            }
                          />
                        </label>
                        {approvalError && <p className="panel panel-error">{approvalError}</p>}
                        <div className="approval-actions">
                          <button
                            type="button"
                            className="primary"
                            disabled={approvalBusyId !== null}
                            onClick={() => void handleApproval(job.id, "approve")}
                            data-testid={`approve-${job.id}`}
                          >
                            {approvalBusyId === job.id ? t.approvalBusy : t.approvalApprove}
                          </button>
                          <button
                            type="button"
                            className="ghost danger"
                            disabled={approvalBusyId !== null}
                            onClick={() => void handleApproval(job.id, "reject")}
                            data-testid={`reject-${job.id}`}
                          >
                            {t.approvalReject}
                          </button>
                        </div>
                      </section>
                    )}

                    {proofOpenId === job.id && (
                      <section className="proof-panel" data-testid={`proof-${job.id}`}>
                        <h4>{t.proofTitle}</h4>
                        {proofLoadingId === job.id && <p className="hint">{t.proofLoading}</p>}
                        {proofError && <p className="panel panel-error">{proofError}</p>}
                        {proof && (
                          <>
                            <p className={proof.chain.valid ? "tag real" : "tag simulated"}>
                              {proof.chain.valid ? t.proofVerified : t.proofTampered}
                            </p>
                            <p className="hint" dir="ltr">
                              {t.proofModel}: {String(proof.document.model_version ?? "-")} ·{" "}
                              {t.proofRuntime}:{" "}
                              {proof.events.reduce((sum, event) => sum + event.duration_ms, 0)} ms ·{" "}
                              {t.proofCost}: {String(proof.document.credits_charged ?? 0)}{" "}
                              {t.creditsUnit}
                            </p>
                            {proof.events.length === 0 && <p className="hint">{t.proofEmpty}</p>}
                            <ol className="proof-events">
                              {proof.events.map((event) => (
                                <li key={event.seq}>
                                  <span>{proofStageLabel(event.stage)}</span>{" "}
                                  <span className={event.verification.allowed ? "tag real" : "tag simulated"}>
                                    {event.verification.allowed ? t.proofAllowed : t.proofBlocked}
                                  </span>{" "}
                                  <em dir="ltr">{event.duration_ms} ms</em>
                                  <code dir="ltr" className="proof-hash">
                                    {event.event_hash.slice(0, 12)}
                                  </code>
                                </li>
                              ))}
                            </ol>
                            <p className="hint" dir="ltr">
                              {t.proofHash}: {proof.document_hash.slice(0, 24)}
                            </p>
                          </>
                        )}
                      </section>
                    )}
                  </li>
                  );
                })}
              </ul>
            </>
          )}
        </section>
      </div>

      {showTopUp && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label={t.topUpTitle}
          onClick={() => setShowTopUp(false)}
          data-testid="topup-dialog"
        >
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <h2>{t.topUpTitle}</h2>
              <button
                type="button"
                className="ghost"
                onClick={() => setShowTopUp(false)}
                aria-label={t.close}
              >
                {t.close}
              </button>
            </div>
            <p className="hint">{t.topUpHint}</p>
            {topUpError && <p className="panel panel-error">{topUpError}</p>}
            <div className="topup-options">
              {topUpPackages.map((packageOption) => (
                <button
                  key={packageOption.name}
                  type="button"
                  className="topup-option"
                  disabled={topUpBusy}
                  onClick={() => void handleTopUp(packageOption.name)}
                  data-testid={`topup-${packageOption.name}`}
                >
                  <strong>{packageOption.credits} {t.creditsUnit}</strong>
                  <span dir="ltr">
                    {(packageOption.price_cents / 100).toFixed(2)} {packageOption.currency.toUpperCase()}
                  </span>
                </button>
              ))}
            </div>
            {topUpBusy && <p className="hint">{t.topUpBusy}</p>}
          </div>
        </div>
      )}
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
