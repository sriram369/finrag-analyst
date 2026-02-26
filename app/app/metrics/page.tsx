"use client";

import { useEffect, useState } from "react";
import { getMetrics } from "@/lib/api";
import Link from "next/link";
import { MessageSquare, Database } from "lucide-react";

type Metrics = {
  total_chunks: number;
  collection_status: string;
  tickers_available: string[];
  filing_types: string[];
};

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMetrics().then(setMetrics).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="flex h-screen bg-[#050d18] text-white">
      <aside className="w-56 bg-[#0a1520] border-r border-[#1e2a3a] flex flex-col p-4 shrink-0">
        <div className="mb-8">
          <h1 className="text-lg font-bold">FinRAG Analyst</h1>
          <p className="text-xs text-gray-500 mt-0.5">SEC Filing Intelligence</p>
        </div>
        <nav className="space-y-1 text-sm">
          <Link href="/" className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:bg-[#1e2a3a] transition-colors">
            <MessageSquare className="w-4 h-4" /> Chat
          </Link>
          <Link href="/ingest" className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:bg-[#1e2a3a] transition-colors">
            <Database className="w-4 h-4" /> Ingestion
          </Link>
          <Link href="/metrics" className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 text-white">
            <span>📊</span> Metrics
          </Link>
        </nav>
      </aside>

      <main className="flex-1 p-6 overflow-y-auto">
        <h2 className="text-xl font-bold mb-1">System Metrics</h2>
        <p className="text-gray-400 text-sm mb-6">Live stats from Qdrant Cloud + pipeline.</p>

        {error && <p className="text-red-400 text-sm">{error}</p>}
        {!metrics && !error && <p className="text-gray-500 text-sm">Loading…</p>}

        {metrics && (
          <div className="grid grid-cols-2 gap-4 max-w-2xl">
            <div className="bg-[#0a1520] border border-[#1e2a3a] rounded-xl p-5">
              <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">Total Chunks</p>
              <p className="text-3xl font-bold text-blue-400">{metrics.total_chunks.toLocaleString()}</p>
            </div>
            <div className="bg-[#0a1520] border border-[#1e2a3a] rounded-xl p-5">
              <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">Qdrant Status</p>
              <p className={`text-lg font-semibold capitalize ${metrics.collection_status === "green" ? "text-green-400" : "text-yellow-400"}`}>
                {metrics.collection_status}
              </p>
            </div>
            <div className="bg-[#0a1520] border border-[#1e2a3a] rounded-xl p-5 col-span-2">
              <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Indexed Tickers</p>
              <div className="flex flex-wrap gap-2">
                {metrics.tickers_available.map((t) => (
                  <span key={t} className="px-2 py-0.5 bg-[#1e2a3a] text-blue-400 rounded font-mono text-sm">{t}</span>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
