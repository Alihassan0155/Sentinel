"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, ArrowUpRight, Bell, Check, ChevronRight, Circle, FileText, Globe, LayoutDashboard, LoaderCircle, LogOut, Plus, Radar, RefreshCw, Search, Settings, X } from "lucide-react";
import { api, ApiError, type Action, type Finding, type User, type Watch } from "@/lib/api";

type Tab = "Overview" | "Intelligence" | "Sources" | "Actions" | "Alerts" | "Digests" | "Profile";
type Alert = { id: number; subject: string; body: string; status: string; reason: string };
type Digest = { id: number; subject: string; period_start: string; period_end: string; status: string; body?: string };
type Profile = { skills: string[]; degree: string | null; interests: string[]; desired_roles: string[]; locations: string[]; preferred_categories: string[]; available_resources: string[]; salary_min: number | null; salary_max: number | null };
const tabs = [{ name: "Overview", icon: LayoutDashboard }, { name: "Intelligence", icon: Activity }, { name: "Sources", icon: Globe }, { name: "Actions", icon: Check }, { name: "Alerts", icon: Bell }, { name: "Digests", icon: FileText }, { name: "Profile", icon: Settings }] as const;
const panel = "rounded-2xl border border-white/[.08] bg-[#101720]";
const field = "w-full rounded-lg border border-white/10 bg-[#0a1018] px-3 py-2.5 text-sm";
const button = "inline-flex items-center justify-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm transition hover:bg-white/5 disabled:opacity-50";
function date(value: string | null) { if (!value) return "Not checked yet"; return new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
function Badge({ children, bright = false }: { children: React.ReactNode; bright?: boolean }) { return <span className={`inline-flex rounded-md px-2 py-1 text-[10px] font-semibold uppercase tracking-wider ${bright ? "bg-emerald-300/10 text-emerald-300" : "bg-white/5 text-slate-400"}`}>{children}</span>; }
function Empty({ title, detail, children }: { title: string; detail: string; children?: React.ReactNode }) { return <div className={`${panel} flex flex-col items-center px-6 py-16 text-center`}><Radar className="mb-5 text-emerald-300/50" size={34} /><h3 className="font-medium">{title}</h3><p className="mt-2 max-w-md text-sm leading-6 text-slate-400">{detail}</p>{children && <div className="mt-5">{children}</div>}</div>; }

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [watches, setWatches] = useState<Watch[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [digests, setDigests] = useState<Digest[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [emailConfigured, setEmailConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [newWatch, setNewWatch] = useState(false);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [digest, setDigest] = useState<Digest | null>(null);
  const [query, setQuery] = useState("");
  const [priority, setPriority] = useState("all");
  const [jobs, setJobs] = useState<Record<number, { id: number; status: string }>>({});
  const failure = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) { router.replace("/login"); setUser(null); }
    else setError(error instanceof Error ? error.message : "Something went wrong");
  }, [router]);
  const load = useCallback(async () => {
    setError("");
    try {
      const account = await api<User>("/auth/me"); setUser(account);
      const results = await Promise.allSettled([
        api<Watch[]>("/watches"), api<Finding[]>("/changes"),
        api<{ email_configured: boolean; notifications: Alert[] }>("/notifications"),
        api<Digest[]>("/digests/weekly"), api<Profile>("/profile"),
      ]);
      const [w, f, a, d, p] = results;
      if (w.status === "fulfilled") setWatches(w.value);
      if (f.status === "fulfilled") setFindings(f.value);
      if (a.status === "fulfilled") { setAlerts(a.value.notifications); setEmailConfigured(a.value.email_configured); }
      if (d.status === "fulfilled") setDigests(d.value);
      if (p.status === "fulfilled") setProfile(p.value);
      for (const result of results) if (result.status === "rejected") failure(result.reason);
    } catch (error) { failure(error); }
    finally { setLoading(false); }
  }, [failure]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!Object.values(jobs).some(job => ["pending", "running"].includes(job.status))) return;
    const timer = setInterval(async () => {
      for (const [watchId, job] of Object.entries(jobs)) {
        if (!["pending", "running"].includes(job.status)) continue;
        try {
          const result = await api<{ status: string; error: string | null }>(`/watches/check-jobs/${job.id}`);
          setJobs(previous => ({ ...previous, [watchId]: { ...job, status: result.status } }));
          if (!["pending", "running"].includes(result.status)) {
            if (result.error) setError(result.error);
            else setMessage("Source check finished. Your intelligence is up to date.");
            void load();
          }
        } catch (error) { failure(error); }
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [jobs, failure, load]);
  useEffect(() => {
    if (!newWatch && !selected && !digest) return;
    const previous = document.activeElement as HTMLElement | null;
    const savedOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) { setNewWatch(false); setSelected(null); setDigest(null); }
      if (event.key === "Tab") {
        const items = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"] button:not(:disabled), [role="dialog"] input, [role="dialog"] select, [role="dialog"] a[href], [role="dialog"] summary'));
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = savedOverflow; document.removeEventListener("keydown", keydown); previous?.focus(); };
  }, [newWatch, selected, digest, busy]);
  async function run(operation: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try { await operation(); } catch (error) { failure(error); } finally { setBusy(false); }
  }
  async function checkWatch(watch: Watch) {
    await run(async () => {
      const job = await api<{ job_id: number; status: string }>(`/watches/${watch.id}/check`, { method: "POST" });
      setJobs(previous => ({ ...previous, [watch.id]: { id: job.job_id, status: job.status } }));
      setMessage(`Check queued for ${watch.name}. The worker will process it.`);
    });
  }
  async function createWatch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget));
    await run(async () => {
      await api("/watches", { method: "POST", body: JSON.stringify({ ...data, check_interval_minutes: Number(data.check_interval_minutes) }) });
      setNewWatch(false); setMessage("Source added. Its first check is queued."); await load();
    });
  }
  async function updateAction(action: Action, status: string) {
    await run(async () => {
      await api(`/actions/${action.id}`, { method: "PATCH", body: JSON.stringify({ status }) }); await load();
      setSelected(null); setMessage("Action updated.");
    });
  }
  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget));
    const data: Record<string, unknown> = {};
    for (const key of ["skills", "interests", "desired_roles", "locations", "preferred_categories", "available_resources"]) data[key] = String(values[key]).split(",").map(v => v.trim()).filter(Boolean);
    data.degree = values.degree || null;
    for (const key of ["salary_min", "salary_max"]) data[key] = values[key] ? Number(values[key]) : null;
    await run(async () => { await api("/profile", { method: "PUT", body: JSON.stringify(data) }); await load(); setMessage("Profile saved. Future findings will use these preferences."); });
  }
  const actions = findings.flatMap(f => f.actions.map(a => ({ ...a, finding: f })));
  const recommended = findings.filter(f => f.recommendation.recommendation === "recommended");
  const filtered = findings.filter(f => `${f.summary} ${f.why_it_matters}`.toLowerCase().includes(query.toLowerCase()) && (priority === "all" || f.recommendation.priority === priority));
  const source = (id: number) => watches.find(w => w.id === id);
  const renderFinding = (finding: Finding) => <button key={finding.id} onClick={() => setSelected(finding)} className={`${panel} group w-full p-5 text-left transition hover:border-emerald-300/25`}>
    <div className="mb-3 flex flex-wrap items-center gap-2"><Badge bright={finding.recommendation.recommendation === "recommended"}>{finding.recommendation.priority}</Badge><span className="text-xs text-slate-500">{source(finding.watch_source_id)?.name || `Source #${finding.watch_source_id}`} · {date(finding.detected_at)}</span><ArrowUpRight size={16} className="ml-auto text-slate-500 group-hover:text-emerald-300" /></div>
    <h3 className="text-base font-medium leading-6">{finding.summary}</h3><p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-400">{finding.why_it_matters}</p>
    <div className="mt-4 flex items-center gap-3 border-t border-white/5 pt-3"><span className="text-xs text-emerald-300">{finding.recommendation.relevance_score}% relevance</span><span className="text-xs text-slate-500">{finding.actions.length} next steps</span><span className="ml-auto text-xs text-slate-400">{finding.recommendation.recommendation}</span></div>
  </button>;
  if (loading || !user) return <main className="flex min-h-screen flex-col items-center justify-center gap-4"><Radar size={40} className="animate-pulse text-emerald-300" /><p className="text-sm text-slate-400">Connecting to your workspace…</p>{error && <><p role="alert" className="max-w-md text-center text-rose-300">{error}</p><button className={button} onClick={() => { setLoading(true); void load(); }}>Try again</button></>}</main>;
  return <div className="min-h-screen lg:pl-60">
    <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-white/[.07] bg-[#0b1119] px-4 py-7 lg:flex">
      <a href="/" className="mb-10 flex items-center gap-2 px-3 text-2xl font-semibold tracking-tight"><Radar className="text-emerald-300" size={25} />sentinel<span className="-ml-2 text-emerald-300">.</span></a>
      <p className="mb-3 px-3 text-[10px] uppercase tracking-[.2em] text-slate-600">Workspace</p><nav className="space-y-1">{tabs.map(({ name, icon: Icon }) => <button key={name} onClick={() => setTab(name)} aria-current={tab === name ? "page" : undefined} className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-sm ${tab === name ? "bg-emerald-300/10 text-emerald-300" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}><Icon size={18} />{name}{name === "Intelligence" && <span className="ml-auto text-xs">{findings.length}</span>}</button>)}</nav>
      <div className="mt-auto rounded-xl border border-white/5 bg-white/[.02] p-4"><div className="flex items-center gap-2 text-xs text-emerald-300"><span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />Connected to backend</div><p className="mt-2 text-xs leading-5 text-slate-500">{watches.filter(w => w.active).length} active sources in your private workspace.</p></div>
      <div className="mt-5 flex items-center gap-3 px-2"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-300/10 text-sm text-emerald-300">{user.name[0].toUpperCase()}</div><div className="min-w-0"><p className="truncate text-sm">{user.name}</p><p className="text-[10px] text-slate-500">Private workspace</p></div><button aria-label="Log out" disabled={busy} onClick={() => void run(async () => { await api("/auth/logout", { method: "POST" }); setUser(null); router.replace("/login"); })} className="ml-auto text-slate-500 hover:text-white"><LogOut size={17} /></button></div>
    </aside>
    <header className="flex flex-wrap items-center gap-3 border-b border-white/[.07] px-5 py-4 lg:px-9"><div className="flex items-center gap-2 text-sm text-slate-500"><Radar size={18} className="text-emerald-300 lg:hidden" /><span>Workspace</span><ChevronRight size={13} /><span className="text-slate-200">{tab}</span></div><div className="ml-auto flex gap-2"><button disabled={busy} onClick={() => void run(load)} className={button} aria-label="Refresh data"><RefreshCw size={15} /></button><button onClick={() => setNewWatch(true)} className="flex items-center gap-2 rounded-lg bg-emerald-300 px-3 py-2 text-sm font-semibold text-[#071912]"><Plus size={16} />Add source</button><button className={`${button} lg:hidden`} aria-label="Log out" onClick={() => void run(async () => { await api("/auth/logout", { method: "POST" }); router.replace("/login"); })}><LogOut size={16} /></button></div></header>
    <nav className="flex gap-1 overflow-x-auto border-b border-white/10 px-4 py-2 lg:hidden">{tabs.map(({ name }) => <button key={name} onClick={() => setTab(name)} className={`whitespace-nowrap rounded-md px-3 py-2 text-xs ${tab === name ? "bg-emerald-300/10 text-emerald-300" : "text-slate-400"}`}>{name}</button>)}</nav>
    <main className="mx-auto max-w-[1500px] px-5 py-8 lg:px-9">
      {error && <div role="alert" className="mb-5 flex items-center gap-3 rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-200"><span className="flex-1">{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X size={16} /></button></div>}
      {message && <div role="status" className="mb-5 flex items-center gap-3 rounded-xl border border-emerald-300/20 bg-emerald-300/5 p-4 text-sm text-emerald-200"><Check size={16} /><span className="flex-1">{message}</span><button aria-label="Dismiss message" onClick={() => setMessage("")}><X size={16} /></button></div>}
      <div className="mb-8"><p className="text-[10px] uppercase tracking-[.25em] text-emerald-300">Personal intelligence</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">{tab === "Overview" ? `Your edge, ${user.name.split(" ")[0]}.` : tab}</h1><p className="mt-2 text-sm text-slate-400">{{ Overview: "Everything that matters. One clear view.", Intelligence: "Changes from your sources, ranked for you.", Sources: "Keep watch on the places where opportunity happens.", Actions: "Turn intelligence into your next move.", Alerts: "Delivery status for your important findings.", Digests: "Your weekly intelligence, brought together.", Profile: "Give Sentinel the context to find what matters to you." }[tab]}</p></div>
      {tab === "Overview" && <>
        <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[{ label: "Active sources", value: watches.filter(w => w.active).length, caption: "Monitoring your corner of the web", icon: Globe }, { label: "Findings", value: findings.length, caption: "Changes detected by Sentinel", icon: Activity }, { label: "Recommended", value: recommended.length, caption: "Opportunities worth your attention", icon: Radar }, { label: "Open actions", value: actions.filter(a => a.status !== "completed").length, caption: "Your next steps, ready to go", icon: Check }].map(({ label, value, caption, icon: Icon }) => <div key={label} className={`${panel} p-5`}><div className="flex items-center justify-between text-xs text-slate-400">{label}<Icon size={17} className="text-slate-600" /></div><p className="mt-4 text-3xl font-semibold tracking-tight">{value}<span className="ml-2 text-lg text-emerald-300">·</span></p><p className="mt-2 text-[11px] text-slate-500">{caption}</p></div>)}</div>
        <div className="grid gap-7 xl:grid-cols-[1fr_320px]"><section><div className="mb-4 flex items-center justify-between"><h2 className="font-medium">Latest intelligence</h2><button onClick={() => setTab("Intelligence")} className="flex items-center gap-1 text-xs text-emerald-300">View all<ArrowUpRight size={14} /></button></div><div className="space-y-3">{findings.length ? findings.slice(0, 5).map(renderFinding) : <Empty title="Your intelligence starts here" detail="Add a source to queue its first snapshot. Sentinel will surface meaningful changes as your sources update."><button className={button} onClick={() => setNewWatch(true)}><Plus size={15} />Add your first source</button></Empty>}</div></section>
          <section className="space-y-5"><div className={`${panel} p-5`}><div className="mb-5 flex items-center justify-between"><h2 className="text-sm font-medium">Your sources</h2><Globe size={16} className="text-slate-500" /></div>{watches.slice(0, 5).map(w => <div key={w.id} className="flex items-center gap-3 border-t border-white/5 py-3"><span className={`h-1.5 w-1.5 rounded-full ${w.active ? "bg-emerald-300" : "bg-slate-600"}`} /><div className="min-w-0 flex-1"><p className="truncate text-xs">{w.name}</p><p className="mt-1 truncate text-[10px] text-slate-500">{w.category}</p></div><span className="text-[10px] text-slate-500">{w.check_interval_minutes}m</span></div>)}{!watches.length && <p className="text-xs leading-5 text-slate-500">No sources yet. Add a page you want to keep an eye on.</p>}<button onClick={() => setTab("Sources")} className="mt-4 w-full rounded-lg border border-white/10 py-2 text-xs text-slate-400">Manage sources</button></div><div className="rounded-2xl border border-emerald-300/15 bg-emerald-300/[.04] p-5"><Radar className="mb-4 text-emerald-300" size={23} /><h3 className="text-sm font-medium">Make it personal</h3><p className="mt-2 text-xs leading-6 text-slate-400">Your skills, interests, and goals help Sentinel rank the right opportunities.</p><button onClick={() => setTab("Profile")} className="mt-4 flex items-center gap-2 text-xs text-emerald-300">Update your profile<ArrowUpRight size={14} /></button></div></section></div>
      </>}
      {tab === "Intelligence" && <><div className="mb-5 flex flex-wrap gap-3"><div className="relative min-w-56 flex-1"><Search className="absolute left-3 top-3 text-slate-500" size={16} /><input aria-label="Search intelligence" value={query} onChange={e => setQuery(e.target.value)} className={`${field} pl-10`} placeholder="Search findings…" /></div><select aria-label="Filter priority" value={priority} onChange={e => setPriority(e.target.value)} className={`${field} w-auto`}><option value="all">All priorities</option>{["critical", "high", "medium", "low"].map(p => <option key={p}>{p}</option>)}</select></div><div className="grid gap-4 xl:grid-cols-2">{filtered.length ? filtered.map(renderFinding) : <Empty title="No findings to show" detail={findings.length ? "Try another search or priority filter." : "Findings will appear here when Sentinel detects meaningful changes in your sources."} />}</div></>}
      {tab === "Sources" && <div className="space-y-3">{watches.length ? watches.map(w => <div key={w.id} className={`${panel} flex flex-wrap items-center gap-4 p-5`}><div className="rounded-xl bg-emerald-300/5 p-3"><Globe size={21} className="text-emerald-300" /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-3"><h2 className="font-medium">{w.name}</h2><Badge bright={w.active}>{w.active ? "Active" : "Paused"}</Badge></div><a href={w.url} target="_blank" rel="noopener noreferrer" className="mt-1 block truncate text-xs text-slate-500 hover:text-emerald-300">{w.url}</a><p className="mt-2 text-xs text-slate-500">{w.category} · Every {w.check_interval_minutes} minutes · {date(w.last_checked_at)}</p>{jobs[w.id] && <p role="status" className="mt-2 text-xs text-emerald-300">Check {jobs[w.id].status}</p>}</div><button disabled={busy || ["pending", "running"].includes(jobs[w.id]?.status)} onClick={() => void checkWatch(w)} className={button}><RefreshCw size={14} />Check now</button><button disabled={busy} className={button} onClick={() => void run(async () => { await api(`/watches/${w.id}`, { method: "PATCH", body: JSON.stringify({ active: !w.active }) }); await load(); })}>{w.active ? "Pause" : "Resume"}</button></div>) : <Empty title="Watch your first source" detail="Add a public webpage, choose a category, and let Sentinel monitor it for meaningful changes."><button className={button} onClick={() => setNewWatch(true)}><Plus size={15} />Add source</button></Empty>}</div>}
      {tab === "Actions" && <div className="space-y-3">{actions.length ? actions.map(action => <div key={action.id} className={`${panel} flex flex-wrap items-center gap-4 p-5`}><button aria-label={action.status === "completed" ? "Mark pending" : "Mark completed"} disabled={busy} onClick={() => void updateAction(action, action.status === "completed" ? "pending" : "completed")} className="text-emerald-300">{action.status === "completed" ? <Check size={22} /> : <Circle size={22} />}</button><div className="min-w-0 flex-1"><p className={action.status === "completed" ? "text-sm text-slate-500 line-through" : "text-sm"}>{action.title}</p><button onClick={() => setSelected(action.finding)} className="mt-2 line-clamp-1 text-left text-xs text-slate-500 hover:text-emerald-300">{action.finding.summary}</button>{action.deadline && <p className="mt-1 text-xs text-amber-300">Deadline: {action.deadline}</p>}</div><select aria-label={`Status for ${action.title}`} disabled={busy} value={action.status} onChange={e => void updateAction(action, e.target.value)} className={`${field} w-auto`}><option value="pending">Pending</option><option value="in_progress">In progress</option><option value="completed">Completed</option></select></div>) : <Empty title="A clear slate" detail="Action plans from recommended findings will appear here, with verified evidence and deadlines when available." />}</div>}
      {tab === "Alerts" && <><div className="mb-5 flex flex-wrap items-center justify-between gap-3"><Badge bright={emailConfigured}>{emailConfigured ? "Email configured" : "Email delivery not configured"}</Badge><button disabled={busy || !emailConfigured} className={button} onClick={() => void run(async () => { const r = await api<{ processed: number }>("/notifications/dispatch", { method: "POST" }); await load(); setMessage(`Processed ${r.processed} pending alerts.`); })}>Send pending alerts</button></div><div className="space-y-3">{alerts.length ? alerts.map(a => <details key={a.id} className={`${panel} p-5`}><summary className="flex cursor-pointer items-center justify-between gap-3 text-sm">{a.subject}<Badge bright={a.status === "sent"}>{a.status}</Badge></summary><p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-slate-400">{a.body}</p><p className="mt-3 text-xs text-slate-500">{a.reason}</p></details>) : <Empty title="Nothing needs your attention yet" detail="Important recommended findings will appear here with their email delivery status." />}</div></>}
      {tab === "Digests" && <><button disabled={busy} className={`${button} mb-5`} onClick={() => void run(async () => { const result = await api<Digest>("/digests/weekly", { method: "POST" }); setDigest(result); await load(); })}><Plus size={15} />Generate last week’s digest</button><div className="space-y-3">{digests.length ? digests.map(d => <div key={d.id} className={`${panel} flex items-center gap-4 p-5`}><FileText className="text-emerald-300" size={22} /><button disabled={busy} onClick={() => void run(async () => setDigest(await api<Digest>(`/digests/weekly/${d.id}`)))} className="flex-1 text-left"><h2 className="text-sm font-medium">{d.subject}</h2><p className="mt-2 text-xs text-slate-500">{d.period_start} — {d.period_end}</p></button><Badge bright={d.status === "sent"}>{d.status}</Badge><ArrowUpRight size={17} /></div>) : <Empty title="See the bigger picture" detail="Generate a digest for the last completed week to review your opportunities, deadlines, and progress." />}</div></>}
      {tab === "Profile" && profile && <form key={JSON.stringify(profile)} onSubmit={saveProfile} className={`${panel} max-w-3xl p-6`}><p className="mb-6 text-xs leading-6 text-slate-400">These preferences apply to the private workspace. Separate list items with commas.</p><div className="grid gap-5 sm:grid-cols-2">{[{ key: "skills", label: "Skills", placeholder: "Python, design, research" }, { key: "degree", label: "Degree", placeholder: "BS Computer Science" }, { key: "interests", label: "Interests", placeholder: "AI, climate, startups" }, { key: "desired_roles", label: "Desired roles", placeholder: "Software engineer" }, { key: "locations", label: "Locations", placeholder: "Karachi, remote" }, { key: "preferred_categories", label: "Preferred categories", placeholder: "jobs, scholarships" }, { key: "available_resources", label: "Available resources", placeholder: "CV, transcript" }, { key: "salary_min", label: "Minimum annual salary (USD)", placeholder: "30000" }, { key: "salary_max", label: "Maximum annual salary (USD)", placeholder: "100000" }].map(({ key, label, placeholder }) => <label key={key} className="text-xs text-slate-400">{label}<input name={key} type={key.startsWith("salary") ? "number" : "text"} min={key.startsWith("salary") ? 1 : undefined} defaultValue={Array.isArray(profile[key as keyof Profile]) ? (profile[key as keyof Profile] as string[]).join(", ") : profile[key as keyof Profile] as string | number || ""} placeholder={placeholder} className={`${field} mt-2`} /></label>)}</div><button disabled={busy} className="mt-7 rounded-lg bg-emerald-300 px-5 py-2.5 text-sm font-semibold text-[#071912]">{busy ? "Saving…" : "Save preferences"}</button></form>}
    </main>
    {(newWatch || selected || digest) && <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/75 p-4 backdrop-blur-sm" onClick={() => { if (!busy) { setNewWatch(false); setSelected(null); setDigest(null); } }}><section role="dialog" aria-modal="true" aria-labelledby="dialog-title" className={`${panel} relative my-auto max-h-[90vh] w-full max-w-2xl overflow-y-auto p-6 sm:p-8`} onClick={e => e.stopPropagation()}><button autoFocus aria-label="Close dialog" disabled={busy} onClick={() => { setNewWatch(false); setSelected(null); setDigest(null); }} className="absolute right-5 top-5 text-slate-400"><X size={20} /></button>
      {newWatch && <><p className="text-xs uppercase tracking-widest text-emerald-300">Expand your radar</p><h2 id="dialog-title" className="mt-2 text-2xl font-semibold">Add a source</h2><p className="mt-3 text-sm text-slate-400">Monitor a public webpage for meaningful changes.</p><form onSubmit={createWatch} className="mt-6 space-y-4"><label className="block text-xs text-slate-400">Source name<input required name="name" maxLength={255} className={`${field} mt-2`} placeholder="My favorite job board" /></label><label className="block text-xs text-slate-400">Page URL<input required type="url" name="url" className={`${field} mt-2`} placeholder="https://example.com/opportunities" /></label><div className="grid grid-cols-2 gap-4"><label className="text-xs text-slate-400">Category<input required name="category" maxLength={100} className={`${field} mt-2`} placeholder="jobs" /></label><label className="text-xs text-slate-400">Check every (minutes)<input required name="check_interval_minutes" type="number" min={1} max={1440} defaultValue={30} className={`${field} mt-2`} /></label></div>{error && <p role="alert" className="text-sm text-rose-300">{error}</p>}<button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-300 py-3 text-sm font-semibold text-[#071912]">{busy ? <LoaderCircle size={16} className="animate-spin" /> : <Plus size={16} />}Start monitoring</button></form></>}
      {selected && <><div className="mb-4"><Badge bright>{selected.recommendation.priority}</Badge></div><h2 id="dialog-title" className="pr-4 text-xl font-semibold leading-8">{selected.summary}</h2><p className="mt-4 text-sm leading-7 text-slate-400">{selected.why_it_matters}</p><h3 className="mt-6 text-sm font-medium">Why this matters to you</h3><ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-400">{selected.recommendation.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>{source(selected.watch_source_id) && <a href={source(selected.watch_source_id)!.url} target="_blank" rel="noopener noreferrer" className="mt-5 inline-flex items-center gap-2 text-sm text-emerald-300">Open original source<ArrowUpRight size={15} /></a>}<h3 className="mt-7 text-sm font-medium">Next steps</h3><div className="mt-3 space-y-3">{selected.actions.map(a => <div key={a.id} className="rounded-lg border border-white/10 p-4"><p className="text-sm">{a.title}</p>{a.supporting_quote && <blockquote className="mt-3 border-l border-emerald-300/30 pl-3 text-xs leading-6 text-slate-400">{a.supporting_quote}</blockquote>}{a.deadline && <p className="mt-2 text-xs text-amber-300">Deadline: {a.deadline}</p>}<Badge>{a.status}</Badge>{a.source_urls.filter(url => /^https?:\/\//.test(url)).map(url => <a key={url} href={url} target="_blank" rel="noopener noreferrer" className="mt-2 block break-all text-xs text-emerald-300">{url}</a>)}</div>)}{!selected.actions.length && <p className="text-sm text-slate-500">No action plan available for this finding.</p>}</div>{selected.investigation && <details className="mt-6"><summary className="cursor-pointer text-sm text-slate-400">Investigation · {selected.investigation.status}</summary><pre className="mt-3 overflow-auto whitespace-pre-wrap break-words text-xs leading-6 text-slate-500">{JSON.stringify(selected.investigation.result, null, 2)}</pre></details>}</>}
      {digest && <><Badge bright>{digest.status}</Badge><h2 id="dialog-title" className="mt-4 pr-4 text-xl font-semibold">{digest.subject}</h2><p className="mt-2 text-xs text-slate-500">{digest.period_start} — {digest.period_end}</p><div className="mt-6 whitespace-pre-wrap text-sm leading-7 text-slate-300">{digest.body}</div>{digest.status === "pending" && <button disabled={busy || !emailConfigured} className={`${button} mt-5`} onClick={() => void run(async () => { setDigest(await api<Digest>(`/digests/weekly/${digest.id}/send`, { method: "POST" })); await load(); })}>Send digest by email</button>}</>}
    </section></div>}
  </div>;
}
