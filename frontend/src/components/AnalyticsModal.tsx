import React from 'react';
import { BarChart3, DollarSign, Activity, Cpu, X } from 'lucide-react';

interface AnalyticsModalProps {
  isOpen: boolean;
  onClose: () => void;
  analytics: any;
}

export const AnalyticsModal: React.FC<AnalyticsModalProps> = ({
  isOpen,
  onClose,
  analytics,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2.5">
            <BarChart3 className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-white tracking-tight">
              System Performance & Cost Metrics
            </h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Analytics Cards Grid */}
        <div className="grid grid-cols-2 gap-3.5">
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1">
              <Activity className="w-4 h-4 text-sky-400" />
              <span>Total Agent Runs</span>
            </div>
            <div className="text-2xl font-bold font-mono text-white">
              {analytics?.total_runs_executed ?? 0}
            </div>
          </div>

          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1">
              <DollarSign className="w-4 h-4 text-emerald-400" />
              <span>Settlement Payouts</span>
            </div>
            <div className="text-2xl font-bold font-mono text-emerald-400">
              ${(analytics?.total_payout_authorized_usd || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </div>

          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1">
              <Cpu className="w-4 h-4 text-amber-400" />
              <span>Total Tokens Used</span>
            </div>
            <div className="text-2xl font-bold font-mono text-white">
              {(analytics?.total_tokens_consumed || 0).toLocaleString()}
            </div>
          </div>

          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center space-x-2 text-xs text-slate-400 mb-1">
              <DollarSign className="w-4 h-4 text-sky-400" />
              <span>Avg Cost / Claim</span>
            </div>
            <div className="text-2xl font-bold font-mono text-sky-400">
              ${(analytics?.avg_cost_per_claim_usd || 0).toFixed(5)}
            </div>
          </div>
        </div>

        {/* Status Breakdown */}
        {analytics?.status_breakdown && (
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
              Terminal Decisions Breakdown
            </span>
            <div className="flex flex-wrap gap-2 text-xs font-mono">
              {Object.entries(analytics.status_breakdown).map(([status, count]: [string, any]) => (
                <div key={status} className="bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 text-slate-300">
                  <span className="capitalize">{status.replace('_', ' ')}</span>: <span className="font-bold text-white">{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex justify-end pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
