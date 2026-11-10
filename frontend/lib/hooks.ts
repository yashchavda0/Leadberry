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
  return { data, error, loading, reload };
}

export const PAGE_SIZE = 25;

export function usePaged<T>(path: string | null) {
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const resource = useResource<Page<T>>(
    path
      ? `${path}${path.includes("?") ? "&" : "?"}limit=${PAGE_SIZE}${cursor ? `&after=${encodeURIComponent(cursor)}` : ""}`
      : null,
  );
  useEffect(() => {
    setCursor(null);
    setHistory([]);
    setTotal(null);
  }, [path]);
  // The API only counts on the first page, so remember it while paging.
  useEffect(() => {
    if (cursor === null && resource.data && typeof resource.data.total === "number") setTotal(resource.data.total);
  }, [cursor, resource.data]);
  function next() {
    if (resource.data?.next_cursor) {
      setHistory((values) => [...values, cursor]);
      setCursor(resource.data.next_cursor);
    }
  }
  function previous() {
    if (history.length) {
      setCursor(history[history.length - 1]);
      setHistory((values) => values.slice(0, -1));
    }
  }
  return {
    ...resource,
    next,
    previous,
    hasPrevious: history.length > 0,
    page: history.length + 1,
    total,
    pageSize: PAGE_SIZE,
  };
}
