"use client";

import { useEffect, useState } from "react";
import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";

const RETRY_SECONDS = 15;

// Full-page state for when the API cannot be reached or is failing; retries itself every few seconds.
export default function ServiceUnavailable({ message, offline, retrying, onRetry }: { message: string; offline?: boolean; retrying?: boolean; onRetry: () => void }) {
  const [left, setLeft] = useState(RETRY_SECONDS);
  useEffect(() => {
    if (retrying) return;
    if (left <= 0) { onRetry(); setLeft(RETRY_SECONDS); return; }
    const timer = window.setTimeout(() => setLeft(value => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [left, retrying, onRetry]);
  return <div className="service-down" role="alert">
    <div className="service-down-card">
      <span className="service-down-icon"><Icon name={offline ? "alert" : "error"} size={30} /></span>
      <h1>{offline ? "We can't reach the server" : "Service unavailable"}</h1>
      <p className="muted">{message}</p>
      <ul className="service-down-tips">
        <li>Your data is safe. Nothing you entered has been lost.</li>
        <li>{offline ? "Check your internet connection or VPN." : "This is usually temporary while the service restarts."}</li>
        <li>If it keeps happening, contact your administrator.</li>
      </ul>
      <div className="service-down-actions">
        <Button onClick={() => { setLeft(RETRY_SECONDS); onRetry(); }} disabled={retrying}><span className={retrying ? "spin" : undefined}><Icon name="refresh" /></span>{retrying ? "Checking..." : "Try again"}</Button>
      </div>
      <span className="small muted">{retrying ? "Contacting the server..." : `Trying again automatically in ${left}s`}</span>
    </div>
  </div>;
}
