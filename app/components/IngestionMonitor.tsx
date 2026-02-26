"use client";

import { useState } from "react";
import { startIngestion, streamIngestionProgress, ProgressEvent } from "@/lib/api";
import { CheckCircle, XCircle, Loader2, ChevronDown, ChevronUp } from "lucide-react";

const TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "GS", "META", "GOOGL", "AMZN", "TSLA", "BLK"];

type LogEntry = ProgressEvent & { ts: string };

const STEP_LABELS: Record<string, string> = {
  download: "Downloading from SEC EDGAR",
  extract:  "Extracting filing HTML",
  parse:    "Parsing with LlamaParse",
  chunk:    "Semantic chunking",
  embed:    "Generating embeddings",
  store:    "Storing in Qdrant Cloud",
};

function StatusIcon({ status }: { status?: string }) {
  if (status === "done")    return <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />;
  if (status === "error")   return <XCircle className="w-4 h-4 text-red-400 shrink-0" />;
  if (status === "started") return <Loader2 className="w-4 h-4 text-blue-400 animate-spin shrink-0" />;
  return <div className="w-4 h-4 rounded-full border border-gray-600 shrink-0" />;
}

export default function IngestionMonitor() {
  const [selectedTickers, setSelectedTickers] = useState<string[]>(["AAPL"]);
  const [limit, setLimit] = useState(2);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [showLog, setShowLog] = useState(false);

  // Latest status per step key
  const [stepStatus, setStepStatus] = useState<Record<string, "started" | "done" | "error">>({});

  function toggleTicker(t: string) {
    setSelectedTickers((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]
    );
  }

  async function handleStart() {
    setRunning(true);
    setDone(false);
    setLog([]);
    setStepStatus({});
    setTotalChunks(0);

    const { job_id } = await startIngestion(selectedTickers, ["10-K"], limit);

    streamIngestionProgress(job_id, (event) => {
      const entry: LogEntry = { ...event, ts: new Date().toLocaleTimeString() };
      setLog((prev) => [...prev, entry]);

      // Track step status for the visual pipeline
      if (event.step && event.status) {
        setStepStatus((prev) => ({
          ...prev,
          [event.step!]: event.status as "started" | "done" | "error",
        }));
      }

      if (event.type === "done") {
        setTotalChunks(event.total_chunks ?? 0);
        setRunning(false);
        setDone(true);
      }
      if (event.type === "error") {
        setRunning(false);
      }
    });
  }

  const pipeline = ["download", "extract", "parse", "chunk", "embed", "store"];

  return (
    <div className="space-y-6">
      {/* Ticker selector */}
      <div>
        <p className="text-sm text-gray-400 mb-2">Select companies to ingest</p>
        <div className="flex flex-wrap gap-2">
          {TICKERS.map((t) => (
            <button
              key={t}
              onClick={() => toggleTicker(t)}
              disabled={running}
              className={`px-3 py-1 rounded text-sm font-mono font-semibold transition-colors ${
                selectedTickers.includes(t)
                  ? "bg-blue-600 text-white"
                  : "bg-[#1e2a3a] text-gray-400 hover:bg-[#243044]"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Limit */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-400">Filings per company:</span>
        {[1, 2, 5].map((n) => (
          <button
            key={n}
            onClick={() => setLimit(n)}
            disabled={running}
            className={`px-3 py-1 rounded text-sm transition-colors ${
              limit === n ? "bg-blue-600 text-white" : "bg-[#1e2a3a] text-gray-400"
            }`}
          >
            {n}
          </button>
        ))}
      </div>

      {/* Start button */}
      <button
        onClick={handleStart}
        disabled={running || selectedTickers.length === 0}
        className="px-6 py-2.5 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold flex items-center gap-2 transition-colors"
      >
        {running && <Loader2 className="w-4 h-4 animate-spin" />}
        {running ? "Running…" : "Start Ingestion"}
      </button>

      {/* Pipeline steps visualiser */}
      {(running || done || log.length > 0) && (
        <div className="bg-[#0d1620] border border-[#1e2a3a] rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase tracking-widest mb-4">Pipeline Progress</p>
          <div className="flex items-center gap-1">
            {pipeline.map((step, i) => (
              <div key={step} className="flex items-center gap-1 flex-1">
                <div className={`flex flex-col items-center gap-1 flex-1 ${
                  stepStatus[step] === "done"    ? "opacity-100" :
                  stepStatus[step] === "started" ? "opacity-100" : "opacity-40"
                }`}>
                  <div className={`w-full h-1.5 rounded-full transition-all duration-500 ${
                    stepStatus[step] === "done"    ? "bg-green-500" :
                    stepStatus[step] === "started" ? "bg-blue-500 animate-pulse" :
                    stepStatus[step] === "error"   ? "bg-red-500" : "bg-gray-700"
                  }`} />
                  <p className="text-[10px] text-gray-400 text-center leading-tight">{STEP_LABELS[step]}</p>
                </div>
                {i < pipeline.length - 1 && (
                  <div className={`w-3 h-px shrink-0 mb-3 ${
                    stepStatus[step] === "done" ? "bg-green-500" : "bg-gray-700"
                  }`} />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Done banner */}
      {done && (
        <div className="flex items-center gap-3 bg-green-950 border border-green-800 rounded-lg px-4 py-3">
          <CheckCircle className="w-5 h-5 text-green-400 shrink-0" />
          <span className="text-green-300 font-medium">
            Ingestion complete — <strong>{totalChunks.toLocaleString()}</strong> chunks stored in Qdrant ✓
          </span>
        </div>
      )}

      {/* Live log */}
      {log.length > 0 && (
        <div className="bg-[#0d1620] border border-[#1e2a3a] rounded-lg overflow-hidden">
          <button
            onClick={() => setShowLog((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-2.5 text-sm text-gray-400 hover:text-gray-200 transition-colors"
          >
            <span>Live Log ({log.length} events)</span>
            {showLog ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          {showLog && (
            <div className="max-h-72 overflow-y-auto px-4 pb-4 space-y-1 font-mono text-xs">
              {log.map((entry, i) => (
                <div key={i} className="flex items-start gap-2 text-gray-400">
                  <span className="text-gray-600 shrink-0">{entry.ts}</span>
                  <StatusIcon status={entry.status} />
                  <span className={
                    entry.status === "done"  ? "text-green-400" :
                    entry.status === "error" ? "text-red-400"   :
                    entry.type === "phase"   ? "text-blue-400"  : "text-gray-300"
                  }>
                    {entry.message || JSON.stringify(entry)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
