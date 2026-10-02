import React from 'react';
import { ShieldCheck, Database, Cpu, ExternalLink, PlusCircle, BarChart3 } from 'lucide-react';
import { SystemHealth } from '../types/claims';

interface HeaderProps {
  health: SystemHealth | null;
  onOpenIngest: () => void;
  onOpenAnalytics: () => void;
  totalTokens?: number;
  totalCost?: number;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  onOpenIngest,
  onOpenAnalytics,
  totalTokens = 0,
  totalCost = 0,
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 px-6 py-3.5 flex items-center justify-between sticky top-0 z-30 shadow-md">
      {/* Brand */}
      <div className="flex items-center space-x-3">
        <div className="bg-sky-500/10 p-2 rounded-lg border border-sky-500/20 text-sky-400">
          <ShieldCheck className="w-6 h-6" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-lg font-bold text-white tracking-tight">CaseFile</h1>
            <span className="bg-sky-500/20 text-sky-300 text-xs px-2 py-0.5 rounded-full font-medium border border-sky-500/30">
              Agentic Claims v0.1
            </span>
          </div>
          <p className="text-xs text-slate-400">LangGraph Multi-Agent Adjudication & HITL Gate</p>
        </div>
      </div>

      {/* Live Cost & Token Metrics */}
      <div className="hidden md:flex items-center space-x-6 bg-slate-950 px-4 py-1.5 rounded-lg border border-slate-800">
        <div className="flex items-center space-x-2">
          <Cpu className="w-4 h-4 text-emerald-400" />
          <div className="text-xs">
            <span className="text-slate-400">Tokens: </span>
            <span className="font-mono font-medium text-slate-200">{totalTokens.toLocaleString()}</span>
          </div>
        </div>
        <div className="h-4 w-px bg-slate-800" />
        <div className="flex items-center space-x-2">
          <span className="text-amber-400 font-mono text-xs font-semibold">$</span>
          <div className="text-xs">
            <span className="text-slate-400">Run Cost: </span>
            <span className="font-mono font-medium text-slate-200">${totalCost.toFixed(5)}</span>
            <span className="text-slate-500 text-[10px] ml-1">/ $2.00 cap</span>
          </div>
        </div>
      </div>

      {/* System Status & Actions */}
      <div className="flex items-center space-x-3">
        {/* DB & Checkpointer Pill */}
        <div className="flex items-center space-x-2 bg-slate-800/80 px-3 py-1 rounded-md text-xs border border-slate-700">
          <Database className="w-3.5 h-3.5 text-sky-400" />
          <span className="text-slate-300">SQLite Checkpointer:</span>
          <span className={`font-semibold ${health?.database_status === 'connected' ? 'text-emerald-400' : 'text-amber-400'}`}>
            {health?.database_status === 'connected' ? 'Active (Disk)' : health?.database_status || 'Checking...'}
          </span>
        </div>

        {/* Analytics button */}
        <button
          onClick={onOpenAnalytics}
          className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-md font-medium border border-slate-700 transition"
        >
          <BarChart3 className="w-3.5 h-3.5 text-sky-400" />
          <span>Analytics</span>
        </button>

        {/* Ingest Claim Button */}
        <button
          onClick={onOpenIngest}
          className="flex items-center space-x-1.5 bg-sky-600 hover:bg-sky-500 text-white text-xs px-3.5 py-1.5 rounded-md font-medium transition shadow-sm"
        >
          <PlusCircle className="w-3.5 h-3.5" />
          <span>Upload Claim</span>
        </button>

        {/* API Docs Link */}
        <a
          href="http://localhost:8001/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-slate-400 hover:text-slate-200 p-1.5 hover:bg-slate-800 rounded-md transition"
          title="Open Swagger API Docs"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>
    </header>
  );
};
