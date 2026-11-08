"use client";

import { useState } from "react";

const formats = ["png", "svg"] as const;

// Looks for /public/marketplace/<provider-code>.png, then .svg, then falls back to initials.
export default function ProviderLogo({ code, name }: { code: string; name: string }) {
  const [attempt, setAttempt] = useState(0);
  if (attempt >= formats.length) return <span className={`marketplace-mark marketplace-mark-${code}`} aria-hidden="true">{name.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase()}</span>;
  const wide = formats[attempt] === "svg";
  // eslint-disable-next-line @next/next/no-img-element
  return <img className={wide ? "marketplace-logo marketplace-logo-wide" : "marketplace-logo"} src={`/marketplace/${code}.${formats[attempt]}`} alt={`${name} logo`} loading="lazy" onError={() => setAttempt(value => value + 1)} />;
}
