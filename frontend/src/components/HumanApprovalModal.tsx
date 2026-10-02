import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  UserCheck,
  CheckCircle2,
  XCircle,
  ShieldAlert,
  X,
} from 'lucide-react';
import { ApprovalDossier, HumanDecisionPayload } from '../types/claims';

interface HumanApprovalModalProps {
  isOpen: boolean;
  onClose: () => void;
  dossier: ApprovalDossier | null;
  threadId: string | null;
  onSubmitDecision: (threadId: string, decision: HumanDecisionPayload) => Promise<void>;
  isSubmitting: boolean;
}

export const HumanApprovalModal: React.FC<HumanApprovalModalProps> = ({
  isOpen,
  onClose,
  dossier,
  threadId,
  onSubmitDecision,
  isSubmitting,
}) => {
  const [approverId, setApproverId] = useState('senior_adjuster_samyak');
  const [authorizedAmount, setAuthorizedAmount] = useState<number>(0);
  const [comments, setComments] = useState('');

  useEffect(() => {
    if (dossier) {
      setAuthorizedAmount(dossier.total_proposed_payout || 0);
      if (dossier.recommendation === 'partial_approve') {
        setComments('Approved verified damages; medical/discrepancies adjusted per audit.');
      } else if (dossier.recommendation === 'deny') {
        setComments('Claim rejected based on policy exclusion or cancellation.');
      } else if (dossier.siu_referral_recommended) {
        setComments('Critical fraud score triggered mandatory SIU referral.');
      } else {
        setComments('All line items, coverages, and policy limits audited and verified.');
      }
    }
  }, [dossier]);

  if (!isOpen || !dossier || !threadId) return null;

  const handleSubmit = async (action: 'approve' | 'partial_approve' | 'reject' | 'escalate_siu') => {
    await onSubmitDecision(threadId, {
      approver_id: approverId,
      action: action,
      authorized_amount: action === 'reject' || action === 'escalate_siu' ? 0.0 : authorizedAmount,
      comments: comments || `Action ${action} submitted by ${approverId}.`,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-200">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400">
              <UserCheck className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                Human-in-the-Loop Approval Gate
              </h2>
              <p className="text-xs text-slate-400">
                Claim: <span className="font-mono text-sky-400 font-semibold">{dossier.claim_id}</span> | Thread: <span className="font-mono text-slate-300">{threadId}</span>
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Discrepancy Warnings */}
        {dossier.discrepancy_details && dossier.discrepancy_details.length > 0 && (
          <div className="bg-amber-950/30 border border-amber-500/40 rounded-xl p-4 space-y-2">
            <div className="flex items-center space-x-2 text-xs font-bold text-amber-300 uppercase tracking-wider">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              <span>Flagged Inconsistencies & Anomalies</span>
            </div>
            <ul className="text-xs text-amber-200/90 space-y-1 pl-5 list-disc">
              {dossier.discrepancy_details.map((disc, idx) => (
                <li key={idx}>{disc}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Payout Breakdown & Proposed Settlement */}
        <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-400 uppercase tracking-wider">
            <span>Proposed Itemized Settlement</span>
            <span className="text-emerald-400 font-mono">
              Total Proposed: ${dossier.total_proposed_payout?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-3 font-mono text-xs">
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
              <span className="text-slate-500 text-[10px] block">Vehicle Repair</span>
              <span className="font-bold text-slate-200">
                ${(dossier.itemized_payout_breakdown?.vehicle_repair || 0).toFixed(2)}
              </span>
            </div>
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
              <span className="text-slate-500 text-[10px] block">Rental Car</span>
              <span className="font-bold text-slate-200">
                ${(dossier.itemized_payout_breakdown?.rental_car || 0).toFixed(2)}
              </span>
            </div>
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
              <span className="text-slate-500 text-[10px] block">Medical (MedPay)</span>
              <span className="font-bold text-slate-200">
                ${(dossier.itemized_payout_breakdown?.medical_payments || 0).toFixed(2)}
              </span>
            </div>
          </div>

          {dossier.justification && (
            <div className="text-xs text-slate-300 pt-2 border-t border-slate-800/80 leading-relaxed">
              <span className="text-slate-500 font-semibold block text-[11px] uppercase">Agent Recommendation Justification:</span>
              {dossier.justification}
            </div>
          )}
        </div>

        {/* Adjuster Input Controls */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">
              Authorized Payout Amount ($)
            </label>
            <input
              type="number"
              step="0.01"
              value={authorizedAmount}
              onChange={(e) => setAuthorizedAmount(parseFloat(e.target.value) || 0)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm font-mono text-emerald-400 focus:outline-none focus:border-sky-500 transition"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">
              Adjuster Signoff ID
            </label>
            <input
              type="text"
              value={approverId}
              onChange={(e) => setApproverId(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-500 transition font-mono"
            />
          </div>

          <div className="col-span-2">
            <label className="block text-xs font-semibold text-slate-400 mb-1">
              Adjuster Settlement Notes & Rationale
            </label>
            <textarea
              rows={2}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Provide comments or rationale for authorized amount..."
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 transition"
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-between pt-3 border-t border-slate-800">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white transition"
          >
            Cancel / Close
          </button>

          <div className="flex space-x-2">
            <button
              disabled={isSubmitting}
              onClick={() => handleSubmit('reject')}
              className="px-3.5 py-2 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 text-xs font-semibold border border-rose-500/30 transition flex items-center space-x-1.5"
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>Deny</span>
            </button>

            <button
              disabled={isSubmitting}
              onClick={() => handleSubmit('escalate_siu')}
              className="px-3.5 py-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 text-xs font-semibold border border-purple-500/30 transition flex items-center space-x-1.5"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Escalate SIU</span>
            </button>

            <button
              disabled={isSubmitting}
              onClick={() => handleSubmit('partial_approve')}
              className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-sm transition flex items-center space-x-1.5"
            >
              <span>Partial Approve</span>
            </button>

            <button
              disabled={isSubmitting}
              onClick={() => handleSubmit('approve')}
              className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-md transition flex items-center space-x-1.5"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{isSubmitting ? 'Resuming...' : 'Approve Settlement'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
