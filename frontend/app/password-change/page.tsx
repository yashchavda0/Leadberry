"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/components/Session";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Field } from "@/components/Ui";
import { crm, errorMessage, homeFor } from "@/lib/crm";

export default function PasswordChangePage() {
  const { identity, reload, logout } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!identity?.password_change_required) return null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const current = String(form.get("current_password") || "");
    const next = String(form.get("new_password") || "");
    if (next !== form.get("confirm_password")) {
      setError("The new passwords do not match.");
      setBusy(false);
      return;
    }
    try {
      await crm<void>("/auth/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) });
      const updated = await reload();
      if (updated) router.replace(homeFor(updated));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return <div className="auth-container"><form className="card password-change-form" onSubmit={submit}>
    <span className="eyebrow">ACCOUNT SECURITY</span><h1>Set a new password</h1><p className="muted">Your administrator generated a temporary password. Replace it before continuing.</p>
    <ErrorNotice error={error} />
    <Field label="Temporary password"><input className="input" type="password" name="current_password" autoComplete="current-password" minLength={12} required /></Field>
    <Field label="New password"><input className="input" type="password" name="new_password" autoComplete="new-password" minLength={12} maxLength={128} required /></Field>
    <Field label="Confirm new password"><input className="input" type="password" name="confirm_password" autoComplete="new-password" minLength={12} maxLength={128} required /></Field>
    <div className="actions"><Button type="submit" disabled={busy}>{busy ? "Updating..." : "Update password"}</Button><Button type="button" variant="outline" onClick={() => void logout()}>Sign out</Button></div>
  </form></div>;
}