"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { crm, errorMessage } from "@/lib/crm";
import { Button } from "@/components/ui/button";
import { Field, ErrorNotice } from "@/components/Ui";

export default function PlatformLoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await crm("/platform/login", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      router.replace("/platform");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return <main className="platform-login-page"><form className="platform-login-panel" onSubmit={submit}>
    <span className="platform-login-mark">LB</span>
    <h1>Platform administration</h1>
    <p>Restricted operator sign-in</p>
    <ErrorNotice error={error} />
    <Field label="Email"><input className="input" name="email" type="email" autoComplete="username" required /></Field>
    <Field label="Password"><input className="input" name="password" type="password" autoComplete="current-password" required /></Field>
    <Button className="full-width" type="submit" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</Button>
  </form></main>;
}