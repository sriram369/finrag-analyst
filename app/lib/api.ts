const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function startIngestion(tickers: string[], filingTypes: string[], limit: number) {
  const res = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tickers, filing_types: filingTypes, limit }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ job_id: string }>;
}

export function streamIngestionProgress(jobId: string, onEvent: (e: ProgressEvent) => void) {
  const source = new EventSource(`${API_BASE}/ingest/${jobId}/stream`);
  source.onmessage = (e) => {
    const data = JSON.parse(e.data);
    onEvent(data);
    if (data.type === "done" || data.type === "error") source.close();
  };
  source.onerror = () => source.close();
  return () => source.close();
}

export async function queryRAG(question: string, ticker?: string, formType?: string, year?: number) {
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, ticker, form_type: formType, filing_year: year }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getMetrics() {
  const res = await fetch(`${API_BASE}/metrics`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Types ──────────────────────────────────────────────────────────────────
export type ProgressEvent = {
  type: "phase" | "step" | "ticker_start" | "ticker_done" | "system" | "warning" | "done" | "error" | "heartbeat" | "__end__";
  step?: string;
  ticker?: string;
  status?: "started" | "done" | "error";
  message?: string;
  total_chunks?: number;
  [key: string]: unknown;
};
