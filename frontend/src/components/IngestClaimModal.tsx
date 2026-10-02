import React, { useState } from 'react';
import { UploadCloud, AlertCircle, X, FileJson } from 'lucide-react';
import { ingestClaim } from '../api/client';

interface IngestClaimModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (claimId: string) => void;
}

const SAMPLE_CLAIM = {
  fnol: {
    claim_id: `CLM-2026-${Math.floor(10000 + Math.random() * 90000)}`,
    incident_date: "2026-10-01",
    incident_time: "14:30",
    incident_location: "Austin, TX",
    incident_description: "Vehicle sideswiped in parking lot.",
    insured_driver: "Alex Mercer",
    policyholder_name: "Alex Mercer",
    vehicle_vin: "1HGCR2F83HA001234",
    vehicle_year: 2022,
    vehicle_make: "Honda",
    vehicle_model: "Accord",
    vehicle_mileage: 31000
  },
  estimate: {
    repair_facility: "Capital Collision Center",
    tax_id: "74-9988776",
    estimate_date: "2026-10-02",
    line_items: [
      { description: "OEM Door Shell Front LT", category: "parts", part_type: "OEM", amount: 650.0 },
      { description: "Body Labor - Align Door", category: "body_labor", labor_hours: 3.0, amount: 240.0 },
      { description: "Paint & Refinish Door", category: "paint_materials", amount: 180.0 }
    ],
    financial_summary: {
      parts_total: 650.0,
      labor_total: 240.0,
      additional_total: 180.0,
      grand_total: 1070.0
    }
  },
  policy: {
    policy_number: "POL-TX-998811",
    named_insured: "Alex Mercer",
    effective_date: "2025-01-01",
    expiration_date: "2027-01-01",
    status: "Active",
    coverages: {
      collision: {
        limit: 50000.0,
        deductible: 500.0
      },
      comprehensive: {
        limit: 50000.0,
        deductible: 250.0
      }
    }
  }
};

export const IngestClaimModal: React.FC<IngestClaimModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [jsonText, setJsonText] = useState(JSON.stringify(SAMPLE_CLAIM, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleUpload = async () => {
    setError(null);
    try {
      const parsed = JSON.parse(jsonText);
      if (!parsed.fnol || !parsed.estimate || !parsed.policy) {
        throw new Error("JSON package must contain 'fnol', 'estimate', and 'policy' objects.");
      }
      setIsSubmitting(true);
      const res = await ingestClaim(parsed);
      setIsSubmitting(false);
      onSuccess(res.claim_id);
      onClose();
    } catch (err: any) {
      setIsSubmitting(false);
      setError(err.message || "Failed to parse or submit claim JSON.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2.5">
            <UploadCloud className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-white tracking-tight">
              Ingest Custom Claim Package
            </h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-xs text-slate-400">
          Upload or paste custom FNOL, Estimate, and Policy JSON to test the multi-agent orchestration pipeline.
        </p>

        {error && (
          <div className="flex items-center space-x-2 bg-rose-500/10 border border-rose-500/30 text-rose-400 p-3 rounded-lg text-xs">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <div className="flex justify-between items-center mb-1.5">
            <label className="text-xs font-semibold text-slate-300">
              Claim JSON Payload (fnol + estimate + policy)
            </label>
            <button
              onClick={() => setJsonText(JSON.stringify(SAMPLE_CLAIM, null, 2))}
              className="text-[11px] text-sky-400 hover:underline"
            >
              Reset to Sample
            </button>
          </div>
          <textarea
            rows={14}
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-slate-200 focus:outline-none focus:border-sky-500 transition"
          />
        </div>

        <div className="flex justify-end space-x-3 pt-2 border-t border-slate-800">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white transition"
          >
            Cancel
          </button>
          <button
            disabled={isSubmitting}
            onClick={handleUpload}
            className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold transition shadow-sm flex items-center space-x-2"
          >
            <FileJson className="w-4 h-4" />
            <span>{isSubmitting ? 'Ingesting...' : 'Ingest Claim Package'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
