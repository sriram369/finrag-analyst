"use client";

import { useState } from "react";
import { queryRAG } from "@/lib/api";
import { Send, Loader2, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";

const TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "GS", "META", "GOOGL", "AMZN", "TSLA", "BLK"];

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  cost_usd?: number;
  latency_ms?: number;
  faithfulness?: number;
};

type Citation = {
  chunk_id: string;
  ticker: string;
  form_type: string;
  filing_year: number;
  section: string;
  excerpt: string;
  score: number;
};

function MetricPill({ label, value, color = "gray" }: { label: string; value: string; color?: string }) {
  const colors: Record<string, string> = {
    gray:  "bg-gray-800 text-gray-300",
    green: "bg-green-950 text-green-400",
    blue:  "bg-blue-950 text-blue-400",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono ${colors[color]}`}>
      {label}: {value}
    </span>
  );
}

function AssistantMessage({ msg }: { msg: Message }) {
  const [showSources, setShowSources] = useState(false);

  return (
    <div className="space-y-2">
      <div className="bg-[#0f1e2e] border border-[#1e2a3a] rounded-xl px-4 py-3 text-gray-200 text-sm leading-relaxed whitespace-pre-wrap">
        {msg.content}
      </div>

      {/* Metrics bar */}
      <div className="flex items-center gap-2 flex-wrap pl-1">
        {msg.latency_ms !== undefined && (
          <MetricPill label="Latency" value={`${msg.latency_ms}ms`} color="blue" />
        )}
        {msg.cost_usd !== undefined && (
          <MetricPill label="Cost" value={`$${msg.cost_usd.toFixed(4)}`} color="gray" />
        )}
        {msg.faithfulness !== undefined && (
          <MetricPill
            label="Faithfulness"
            value={`${(msg.faithfulness * 100).toFixed(0)}%`}
            color={msg.faithfulness >= 0.9 ? "green" : "gray"}
          />
        )}
        {msg.citations && msg.citations.length > 0 && (
          <button
            onClick={() => setShowSources((v) => !v)}
            className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            {showSources ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {showSources ? "Hide" : "Show"} {msg.citations.length} source{msg.citations.length > 1 ? "s" : ""}
          </button>
        )}
      </div>

      {/* Sources */}
      {showSources && msg.citations && (
        <div className="space-y-2 pl-1">
          {msg.citations.map((c, i) => (
            <div key={i} className="bg-[#0a1520] border border-[#1e2a3a] rounded-lg p-3 text-xs">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="font-mono font-bold text-blue-400">{c.ticker}</span>
                <span className="text-gray-500">{c.form_type} {c.filing_year}</span>
                <span className="text-gray-600">·</span>
                <span className="text-gray-400">{c.section}</span>
                <span className="ml-auto text-gray-600">score {c.score.toFixed(2)}</span>
              </div>
              <p className="text-gray-400 italic line-clamp-3">&ldquo;{c.excerpt}&rdquo;</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [ticker, setTicker] = useState<string>("");
  const [loading, setLoading] = useState(false);

  async function handleSend() {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const res = await queryRAG(question, ticker || undefined);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          citations: res.citations,
          cost_usd: res.cost_usd,
          latency_ms: res.latency_ms,
          faithfulness: res.faithfulness,
        },
      ]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${e}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Ticker filter */}
      <div className="flex gap-2 flex-wrap mb-4">
        <button
          onClick={() => setTicker("")}
          className={`px-3 py-1 rounded text-xs font-mono transition-colors ${
            ticker === "" ? "bg-blue-600 text-white" : "bg-[#1e2a3a] text-gray-400 hover:bg-[#243044]"
          }`}
        >
          All
        </button>
        {TICKERS.map((t) => (
          <button
            key={t}
            onClick={() => setTicker(t === ticker ? "" : t)}
            className={`px-3 py-1 rounded text-xs font-mono transition-colors ${
              ticker === t ? "bg-blue-600 text-white" : "bg-[#1e2a3a] text-gray-400 hover:bg-[#243044]"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-600 gap-2">
            <p className="text-lg">Ask anything about SEC filings</p>
            <p className="text-sm">e.g. &ldquo;What were Apple&apos;s biggest risk factors in 2024?&rdquo;</p>
          </div>
        )}
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="bg-blue-600 text-white rounded-xl px-4 py-2 text-sm max-w-[80%]">
                {msg.content}
              </div>
            </div>
          ) : (
            <div key={i} className="max-w-[90%]">
              <AssistantMessage msg={msg} />
            </div>
          )
        )}
        {loading && (
          <div className="flex items-center gap-2 text-gray-500 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            Retrieving and generating answer…
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="Ask about any SEC filing…"
          className="flex-1 bg-[#0f1e2e] border border-[#1e2a3a] rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-600 transition-colors"
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="p-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Send className="w-4 h-4 text-white" />
        </button>
      </div>
    </div>
  );
}
