"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Radar, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
export default function AuthForm({ signup = false }: { signup?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try { await api(`/auth/${signup ? "signup" : "login"}`, { method: "POST", body: JSON.stringify(data) }); router.replace("/"); }
    catch (error) { setError(error instanceof Error ? error.message : "Unable to sign in"); }
    finally { setBusy(false); }
  }
  const field = "mt-2 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 focus:border-emerald-400";
  return <main className="grid min-h-screen lg:grid-cols-2">
    <section className="relative hidden flex-col justify-between overflow-hidden border-r border-white/10 bg-[#0c151c] p-14 lg:flex">
      <div className="flex items-center gap-3 text-xl font-semibold"><Radar className="text-emerald-300" />sentinel<span className="text-emerald-300">.</span></div>
      <div className="absolute -right-36 top-32 h-[600px] w-[600px] rounded-full border border-emerald-300/10 shadow-[0_0_150px_#10b98110]"><div className="absolute inset-20 rounded-full border border-emerald-300/10"><div className="absolute inset-20 rounded-full border border-emerald-300/20" /></div></div>
      <div className="relative max-w-lg"><p className="mb-6 text-xs uppercase tracking-[.3em] text-emerald-300">Your personal intelligence agent</p><h1 className="text-5xl font-semibold leading-tight tracking-tight">Less noise.<br />More opportunity.</h1><p className="mt-6 text-lg leading-relaxed text-slate-400">Keep an eye on your sources. Understand what changed. Know what to do next.</p></div>
      <p className="relative flex items-center gap-2 text-sm text-slate-500"><ShieldCheck size={17} /> Secure sessions. Intelligence that stays with you.</p>
    </section>
    <section className="flex items-center justify-center px-6 py-16"><div className="w-full max-w-sm">
      <div className="mb-12 flex items-center gap-2 text-xl font-semibold lg:hidden"><Radar className="text-emerald-300" />sentinel.</div>
      <p className="text-xs uppercase tracking-[.22em] text-emerald-300">{signup ? "Get started" : "Welcome back"}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight">{signup ? "Create your account" : "Sign in to Sentinel"}</h2>
      <p className="mt-3 text-sm leading-6 text-slate-400">{signup ? "Create your private workspace and start monitoring what matters." : "Your sources, findings, and next steps are waiting."}</p>
      <form onSubmit={submit} className="mt-8 space-y-5">
        {signup && <label className="block text-sm">Full name<input name="name" autoComplete="name" required maxLength={100} className={field} placeholder="Your name" /></label>}
        <label className="block text-sm">Email address<input name="email" type="email" autoComplete="email" required maxLength={254} className={field} placeholder="you@example.com" /></label>
        <label className="block text-sm">Password<input name="password" type="password" autoComplete={signup ? "new-password" : "current-password"} required minLength={10} maxLength={128} className={field} placeholder="At least 10 characters" /></label>
        {error && <p role="alert" className="rounded-lg border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-200">{error}</p>}
        <button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-300 py-3 font-semibold text-[#081912] transition hover:bg-emerald-200">{busy ? "Please wait…" : signup ? "Create account" : "Sign in"}<ArrowRight size={17} /></button>
      </form>
      <p className="mt-7 text-center text-sm text-slate-400">{signup ? "Already have an account? " : "New to Sentinel? "}<Link className="text-emerald-300 hover:underline" href={signup ? "/login" : "/signup"}>{signup ? "Sign in" : "Create an account"}</Link></p>
    </div></section>
  </main>;
}
