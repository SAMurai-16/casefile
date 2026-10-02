import React, { useRef, useEffect } from 'react';
import { Terminal, Activity, Zap, Cpu } from 'lucide-react';
import { StreamEvent } from '../types/claims';

interface EventStreamLogProps {
  events: StreamEvent[];
  isConnected: boolean;
  totalTokens: number;
  totalCost: number;
  stepCount: number;
}

export const EventStreamLog: React.FC<EventStreamLogProps> = ({
  events,
  isConnected,
  totalTokens,
  totalCost,
  stepCount,
}) => {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const costPercentage = Math.min(100, (totalCost / 2.0) * 100);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl flex flex-col h-full overflow-hidden shadow-sm">
      {/* Console Header */}
      <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Terminal className="w-4 h-4 text-sky-400" />
          <h3 className="text-xs font-bold text-white uppercase tracking-wider">
            Live Agent Execution Log (SSE)
          </h3>
        </div>

        <div className="flex items-center space-x-2">
          <span
            className={`w-2 h-2 rounded-full ${
              isConnected ? 'bg-emerald-500 animate-ping' : 'bg-slate-600'
            }`}
          />
          <span className="text-[11px] font-mono text-slate-400">
            {isConnected ? 'STREAMING' : 'IDLE'}
          </span>
        </div>
      </div>

      {/* Resource Consumption Sub-bar */}
      <div className="bg-slate-950/60 px-4 py-2 border-b border-slate-800/80 flex items-center justify-between text-xs font-mono">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-1.5 text-slate-300">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Steps: {stepCount}</span>
          </div>
          <div className="flex items-center space-x-1.5 text-slate-300">
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
            <span>Tokens: {totalTokens.toLocaleString()}</span>
          </div>
        </div>

        {/* Cost Progress Bar */}
        <div className="flex items-center space-x-2 w-48">
          <span className="text-[11px] text-slate-400">${totalCost.toFixed(5)}</span>
          <div className="flex-1 bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                costPercentage > 75 ? 'bg-rose-500' : 'bg-emerald-500'
              }`}
              style={{ width: `${costPercentage}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-500">$2.00</span>
        </div>
      </div>

      {/* Event Terminal Output */}
      <div className="flex-1 p-4 overflow-y-auto space-y-2 font-mono text-xs text-slate-300">
        {events.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 space-y-2 py-12">
            <Activity className="w-8 h-8 opacity-40 animate-pulse" />
            <p>Click "Run Claim" to launch multi-agent graph stream</p>
          </div>
        ) : (
          events.map((ev, i) => {
            const isStep = ev.event === 'step';
            const isGate = ev.event === 'gate_paused';
            const isCompleted = ev.event === 'completed';
            const isError = ev.event === 'error';

            return (
              <div
                key={i}
                className={`p-2.5 rounded-md border text-left transition ${
                  isGate
                    ? 'bg-amber-950/30 border-amber-500/40 text-amber-200'
                    : isCompleted
                    ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-200'
                    : isError
                    ? 'bg-rose-950/30 border-rose-500/40 text-rose-200'
                    : 'bg-slate-950/70 border-slate-800/80 text-slate-300'
                }`}
              >
                <div className="flex items-center justify-between text-[11px] mb-1">
                  <span
                    className={`font-bold px-1.5 py-0.5 rounded text-[10px] uppercase ${
                      isGate
                        ? 'bg-amber-500/20 text-amber-300'
                        : isCompleted
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : isError
                        ? 'bg-rose-500/20 text-rose-300'
                        : 'bg-sky-500/20 text-sky-300'
                    }`}
                  >
                    {ev.event}
                  </span>
                  <span className="text-slate-500 text-[10px]">{ev.timestamp}</span>
                </div>

                {/* Event Details */}
                {isStep && (
                  <div className="flex items-center justify-between text-slate-300 text-xs">
                    <div>
                      Agent: <span className="text-sky-400 font-bold">{ev.data.node}</span> ({ev.data.phase})
                    </div>
                    <div className="text-slate-500 text-[11px]">
                      Tokens: {ev.data.total_tokens} | Cost: ${ev.data.total_cost_usd?.toFixed(5)}
                    </div>
                  </div>
                )}

                {isGate && (
                  <div className="text-xs text-amber-300">
                    ⚠️ Graph halted at Human Approval Gate. Adjuster sign-off required!
                    {ev.data.dossier?.total_proposed_payout && (
                      <div className="font-bold mt-0.5">
                        Proposed Payout: ${ev.data.dossier.total_proposed_payout.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </div>
                    )}
                  </div>
                )}

                {isCompleted && (
                  <div className="text-xs text-emerald-300">
                    🎯 Decision finalized: <span className="font-bold">{ev.data.terminal_status}</span> | Payout: ${ev.data.final_payout_amount?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </div>
                )}

                {isError && (
                  <div className="text-xs text-rose-400">
                    ❌ Error: {ev.data.error}
                  </div>
                )}
              </div>
            );
          })
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};
