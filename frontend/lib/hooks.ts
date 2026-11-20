"use client";

import { useCallback, useEffect, useState } from "react";
import { crm, errorMessage, type Page } from "./crm";

export function useResource<T>(path: string | null, keepData = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    if (!keepData) setData(null);
    setError("");
    setLoading(Boolean(path));
    if (path) {
      crm<T>(path, { signal: controller.signal })
        .then((result) => {
          if (!controller.signal.aborted) setData(result);
        })
        .catch((error) => {
          if (!controller.signal.aborted) setError(errorMessage(error));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }
    return () => controller.abort();
  }, [path, revision, keepData]);
  // Reload automatically once the service is back, so a failed list fills in without a manual retry.
  useEffect(() => {
    if (!error) return;
    window.addEventListener("crm-service-up", reload);
    return () => window.removeEventListener("crm-service-up", reload);
  }, [error, reload]);
  return { data, error, loading, reload };
}

export const PAGE_SIZE = 25;

export function usePaged<T>(path: string | null, pageSize = PAGE_SIZE) {
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const key = `${path ?? ""}\u0000${pageSize}`;
  const [cursorKey, setCursorKey] = useState(key);
  const currentCursor = cursorKey === key ? cursor : null;
  const currentHistory = cursorKey === key ? history : [];
  const resource = useResource<Page<T>>(
    path
      ? `${path}${path.includes("?") ? "&" : "?"}limit=${pageSize}${currentCursor ? `&after=${encodeURIComponent(currentCursor)}` : ""}`
      : null,
  );
  useEffect(() => {
    setCursor(null);
    setHistory([]);
    setTotal(null);
    setCursorKey(key);
  }, [key]);
  // The API only counts on the first page, so remember it while paging.
  useEffect(() => {
    if (
      currentCursor === null &&
      resource.data &&
      typeof resource.data.total === "number"
    )
      setTotal(resource.data.total);
  }, [currentCursor, resource.data]);
  function next() {
    if (resource.data?.next_cursor) {
      setHistory((values) => [...values, currentCursor]);
      setCursor(resource.data.next_cursor);
    }
  }
  function previous() {
    if (currentHistory.length) {
      setCursor(currentHistory[currentHistory.length - 1]);
      setHistory((values) => values.slice(0, -1));
    }
  }
  return {
    ...resource,
    next,
    previous,
    hasPrevious: currentHistory.length > 0,
    page: currentHistory.length + 1,
    total: cursorKey === key ? total : null,
    pageSize,
  };
}
