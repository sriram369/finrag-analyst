import IngestionMonitor from "@/components/IngestionMonitor";
import Link from "next/link";
import { MessageSquare, BarChart2 } from "lucide-react";

export default function IngestPage() {
  return (
    <div className="flex h-screen bg-[#050d18] text-white">
      {/* Sidebar */}
      <aside className="w-56 bg-[#0a1520] border-r border-[#1e2a3a] flex flex-col p-4 shrink-0">
        <div className="mb-8">
          <h1 className="text-lg font-bold text-white">FinRAG Analyst</h1>
          <p className="text-xs text-gray-500 mt-0.5">SEC Filing Intelligence</p>
        </div>
        <nav className="space-y-1 text-sm">
          <Link href="/" className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:bg-[#1e2a3a] transition-colors">
            <MessageSquare className="w-4 h-4" /> Chat
          </Link>
          <Link href="/ingest" className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 text-white">
            <span>🗄️</span> Ingestion
          </Link>
          <Link href="/metrics" className="flex items-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:bg-[#1e2a3a] transition-colors">
            <BarChart2 className="w-4 h-4" /> Metrics
          </Link>
        </nav>
      </aside>

      {/* Main */}
      <main className="flex-1 p-6 overflow-y-auto">
        <div className="max-w-3xl">
          <h2 className="text-xl font-bold mb-1">Data Ingestion</h2>
          <p className="text-gray-400 text-sm mb-6">
            Download SEC filings, parse them with LlamaParse, chunk semantically,
            embed with BAAI/bge-large-en-v1.5, and store in Qdrant Cloud — all streamed live.
          </p>
          <IngestionMonitor />
        </div>
      </main>
    </div>
  );
}
