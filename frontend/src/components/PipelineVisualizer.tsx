import React from 'react';
import {
  FileText,
  ScanLine,
  Sliders,
  ShieldAlert,
  FileCheck,
  UserCheck,
  CheckCircle,
  ArrowRight,
  Clock,
} from 'lucide-react';

interface PipelineVisualizerProps {
  currentPhase: string;
  activeNode: string | null;
  terminalStatus: string | null;
  isPausedAtGate: boolean;
  stepCount: number;
}

export const PipelineVisualizer: React.FC<PipelineVisualizerProps> = ({
  currentPhase,
  activeNode,
  terminalStatus,
  isPausedAtGate,
  stepCount,
}) => {
  const steps = [
    {
      id: 'intake',
      name: 'Intake',
      desc: 'Raw Claims Data',
      icon: FileText,
    },
    {
      id: 'extraction',
      name: 'Extractor',
      desc: 'Line-Item Breakdown',
      icon: ScanLine,
    },
    {
      id: 'supervisor',
      name: 'Supervisor',
      desc: 'Deterministic Router',
      icon: Sliders,
    },
    {
      id: 'investigation',
      name: 'Investigator',
      desc: 'Policy & ML Risk',
      icon: ShieldAlert,
    },
    {
      id: 'review',
      name: 'Reviewer',
      desc: 'Math & Discrepancies',
      icon: FileCheck,
    },
    {
      id: 'human_gate',
      name: 'Human Gate',
      desc: 'Approval Dossier',
      icon: UserCheck,
    },
    {
      id: 'terminated',
      name: 'Settlement',
      desc: 'Payout Finalized',
      icon: CheckCircle,
    },
  ];

  // Helper to determine status of each pipeline step
  const getStepStatus = (id: string) => {
    if (terminalStatus) {
      if (id === 'terminated') return 'completed';
      return 'completed';
    }

    if (isPausedAtGate && id === 'human_gate') {
      return 'paused';
    }

    if (activeNode === id || currentPhase === id) {
      return 'active';
    }

    // Determine past steps
    const phaseOrder = ['intake', 'extraction', 'supervisor', 'investigation', 'review', 'human_gate', 'terminated'];
    const currentIndex = phaseOrder.indexOf(currentPhase.toLowerCase());
    const stepIdx = phaseOrder.indexOf(id.toLowerCase());

    if (currentIndex > -1 && stepIdx < currentIndex) {
      return 'completed';
    }

    return 'pending';
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <h2 className="text-sm font-semibold text-white tracking-wide uppercase">
            Agentic Orchestration Graph
          </h2>
          <span className="bg-slate-800 text-slate-400 text-xs px-2 py-0.5 rounded font-mono">
            Superstep {stepCount}
          </span>
        </div>

        {isPausedAtGate && (
          <div className="flex items-center space-x-1.5 bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs px-2.5 py-1 rounded-full font-medium animate-pulse">
            <Clock className="w-3.5 h-3.5" />
            <span>Paused at Human Gate</span>
          </div>
        )}

        {terminalStatus && (
          <div className="flex items-center space-x-1.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs px-2.5 py-1 rounded-full font-medium">
            <CheckCircle className="w-3.5 h-3.5" />
            <span className="capitalize">{terminalStatus.replace('_', ' ')}</span>
          </div>
        )}
      </div>

      {/* Nodes Pipeline */}
      <div className="flex items-center justify-between overflow-x-auto py-2">
        {steps.map((step, idx) => {
          const status = getStepStatus(step.id);
          const Icon = step.icon;

          return (
            <React.Fragment key={step.id}>
              {/* Node Card */}
              <div className="flex flex-col items-center min-w-[105px]">
                <div
                  className={`w-11 h-11 rounded-xl flex items-center justify-center border transition-all duration-300 ${
                    status === 'active'
                      ? 'bg-sky-500 text-white border-sky-400 shadow-lg shadow-sky-500/30 animate-pulse ring-4 ring-sky-500/20'
                      : status === 'paused'
                      ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-lg shadow-amber-500/30 animate-bounce ring-4 ring-amber-500/20'
                      : status === 'completed'
                      ? 'bg-emerald-950/60 text-emerald-400 border-emerald-500/40'
                      : 'bg-slate-950 text-slate-500 border-slate-800'
                  }`}
                >
                  <Icon className="w-5 h-5" />
                </div>

                <span
                  className={`text-xs font-semibold mt-2 ${
                    status === 'active'
                      ? 'text-sky-400'
                      : status === 'paused'
                      ? 'text-amber-400'
                      : status === 'completed'
                      ? 'text-emerald-400'
                      : 'text-slate-400'
                  }`}
                >
                  {step.name}
                </span>

                <span className="text-[10px] text-slate-500 text-center leading-tight">
                  {step.desc}
                </span>
              </div>

              {/* Connecting Arrow */}
              {idx < steps.length - 1 && (
                <div className="flex-1 flex items-center justify-center px-1">
                  <div
                    className={`h-0.5 w-full transition-colors ${
                      status === 'completed' ? 'bg-emerald-500/50' : 'bg-slate-800'
                    }`}
                  />
                  <ArrowRight
                    className={`w-3.5 h-3.5 -ml-1 shrink-0 ${
                      status === 'completed' ? 'text-emerald-500/70' : 'text-slate-700'
                    }`}
                  />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
