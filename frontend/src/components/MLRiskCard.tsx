import React from 'react';
import { ShieldAlert, BookOpen, Award } from 'lucide-react';

interface MLRiskCardProps {
  investigation: any;
}

export const MLRiskCard: React.FC<MLRiskCardProps> = ({ investigation }) => {
  if (!investigation) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 flex flex-col items-center justify-center text-slate-500 text-xs">
        <ShieldAlert className="w-8 h-8 opacity-40 mb-2" />
        <span>No ML risk assessment yet. Run the graph to evaluate coverage & fraud.</span>
      </div>
    );
  }

  const score = investigation.fraud_risk_score ?? 0;
  const level = investigation.fraud_risk_level || 'low';
  const acv = investigation.actual_cash_value || 0;
  const ratio = (investigation.repair_to_acv_ratio || 0) * 100;
  const isTotalLoss = investigation.is_total_loss_candidate;
  const siuMandatory = investigation.siu_referral_recommended;

  const scoreColor =
    score >= 75
      ? 'text-rose-500 border-rose-500/30 bg-rose-500/10'
      : score >= 40
      ? 'text-amber-500 border-amber-500/30 bg-amber-500/10'
      : 'text-emerald-500 border-emerald-500/30 bg-emerald-500/10';

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-5">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <ShieldAlert className="w-4 h-4 text-sky-400" />
          <h3 className="text-xs font-bold text-white uppercase tracking-wider">
            ML Risk & Policy Clause Audit
          </h3>
        </div>
        <span className="text-xs text-slate-400 font-mono">LightGBM Model + Valuation</span>
      </div>

      {/* Top Gauges Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Fraud Risk Score Box */}
        <div className={`p-4 rounded-xl border flex items-center justify-between ${scoreColor}`}>
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              Fraud Risk Score
            </span>
            <div className="text-3xl font-black font-mono mt-1">
              {score} <span className="text-xs font-normal text-slate-400">/ 100</span>
            </div>
            <div className="text-xs font-medium uppercase mt-0.5">
              Risk Level: <span className="font-bold">{level}</span>
            </div>
          </div>

          <div className="text-right">
            {siuMandatory ? (
              <span className="bg-rose-500 text-white text-[11px] px-2.5 py-1 rounded-full font-bold uppercase tracking-wider animate-pulse inline-block">
                SIU Referral Req
              </span>
            ) : (
              <span className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[11px] px-2 py-0.5 rounded font-medium">
                Standard Fast-Track
              </span>
            )}
          </div>
        </div>

        {/* ACV Valuation & Total Loss Ratio Box */}
        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Vehicle ACV Valuation
            </span>
            <span className="font-mono text-sm font-bold text-white">
              ${acv.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>

          <div className="space-y-1.5 my-2">
            <div className="flex justify-between text-xs font-mono">
              <span className="text-slate-400">Repair / ACV Ratio:</span>
              <span className={`font-bold ${ratio >= 75 ? 'text-rose-400' : 'text-slate-200'}`}>
                {ratio.toFixed(1)}% {isTotalLoss ? '(Total Loss Threshold)' : ''}
              </span>
            </div>
            <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  ratio >= 75 ? 'bg-rose-500' : ratio >= 50 ? 'bg-amber-500' : 'bg-sky-500'
                }`}
                style={{ width: `${Math.min(100, ratio)}%` }}
              />
            </div>
          </div>

          <span className="text-[10px] text-slate-500">
            Total loss threshold applies if repairs exceed 75% of vehicle ACV.
          </span>
        </div>
      </div>

      {/* Validated Endorsements & Riders */}
      {investigation.endorsements_validated && investigation.endorsements_validated.length > 0 && (
        <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800">
          <div className="flex items-center space-x-1.5 text-xs font-semibold text-emerald-400 mb-2">
            <Award className="w-4 h-4" />
            <span>Validated Endorsements & Riders</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {investigation.endorsements_validated.map((end: string, i: number) => (
              <span
                key={i}
                className="bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 text-xs px-2.5 py-1 rounded-md font-mono"
              >
                {end}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Policy Clause Audit Notes */}
      {investigation.clause_audit_notes && investigation.clause_audit_notes.length > 0 && (
        <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-2">
          <div className="flex items-center space-x-1.5 text-xs font-semibold text-sky-400">
            <BookOpen className="w-4 h-4" />
            <span>Automated Policy Clause Audit Notes</span>
          </div>
          <ul className="divide-y divide-slate-800/60 text-xs text-slate-300 font-sans space-y-1.5 pt-1">
            {investigation.clause_audit_notes.map((note: string, idx: number) => (
              <li key={idx} className="pt-1.5 text-[11px] leading-relaxed text-slate-300">
                • {note}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
