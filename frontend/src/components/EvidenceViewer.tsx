import React, { useState } from 'react';
import { Wrench, Car, Stethoscope, FileSpreadsheet } from 'lucide-react';

interface EvidenceViewerProps {
  extraction: any;
}

export const EvidenceViewer: React.FC<EvidenceViewerProps> = ({
  extraction,
}) => {
  const [activeTab, setActiveTab] = useState<'repairs' | 'rental' | 'medical'>('repairs');

  const repairs = extraction?.itemized_repairs || [];
  const rental = extraction?.rental_receipt;
  const medical = extraction?.medical_bills || [];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm flex flex-col h-full">
      {/* Sub Tabs */}
      <div className="bg-slate-950 px-4 pt-3 border-b border-slate-800 flex items-center justify-between">
        <div className="flex space-x-2">
          <button
            onClick={() => setActiveTab('repairs')}
            className={`flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition ${
              activeTab === 'repairs'
                ? 'border-sky-500 text-sky-400 bg-slate-900/60 rounded-t-md'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Wrench className="w-3.5 h-3.5" />
            <span>Body Shop Repairs ({repairs.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('rental')}
            className={`flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition ${
              activeTab === 'rental'
                ? 'border-sky-500 text-sky-400 bg-slate-900/60 rounded-t-md'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Car className="w-3.5 h-3.5" />
            <span>Rental Car {rental ? '✓' : ''}</span>
          </button>

          <button
            onClick={() => setActiveTab('medical')}
            className={`flex items-center space-x-1.5 px-3 py-2 text-xs font-semibold border-b-2 transition ${
              activeTab === 'medical'
                ? 'border-sky-500 text-sky-400 bg-slate-900/60 rounded-t-md'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Stethoscope className="w-3.5 h-3.5" />
            <span>Medical Bills ({medical.length})</span>
          </button>
        </div>

        {/* Claimed Total Summary Pill */}
        {extraction && (
          <div className="text-xs font-mono pb-2 text-slate-300">
            Claimed Total:{' '}
            <span className="font-bold text-sky-400">
              ${(extraction.claimed_grand_total || 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>
          </div>
        )}
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-4">
        {!extraction ? (
          <div className="h-48 flex flex-col items-center justify-center text-slate-500 text-xs">
            <FileSpreadsheet className="w-8 h-8 opacity-40 mb-2" />
            <span>No extracted data yet. Run the graph to extract evidence.</span>
          </div>
        ) : activeTab === 'repairs' ? (
          <div className="space-y-4">
            {/* Totals Breakdown Cards */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Parts Total</span>
                <div className="text-sm font-bold font-mono text-slate-100">
                  ${(extraction.total_parts_cost || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Labor Total</span>
                <div className="text-sm font-bold font-mono text-slate-100">
                  ${(extraction.total_labor_cost || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Additional Costs</span>
                <div className="text-sm font-bold font-mono text-slate-100">
                  ${(extraction.total_additional_costs || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            {/* Line Items Table */}
            <div className="border border-slate-800 rounded-lg overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800">
                  <tr>
                    <th className="py-2.5 px-3">Description</th>
                    <th className="py-2.5 px-3">Category</th>
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3 text-right">Hours</th>
                    <th className="py-2.5 px-3 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {repairs.map((r: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-850/40 text-slate-300">
                      <td className="py-2 px-3 font-sans text-slate-200">{r.description}</td>
                      <td className="py-2 px-3">
                        <span className="bg-slate-800 text-slate-300 text-[10px] px-1.5 py-0.5 rounded">
                          {r.category}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-slate-400 text-[11px]">{r.part_type || '—'}</td>
                      <td className="py-2 px-3 text-right text-slate-400">{r.labor_hours ?? '—'}</td>
                      <td className="py-2 px-3 text-right font-semibold text-slate-100">
                        ${(r.amount || 0).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : activeTab === 'rental' ? (
          <div>
            {rental ? (
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-semibold text-sm text-white">{rental.rental_agency || 'Rental Agency'}</span>
                  <span className="font-mono text-xs text-sky-400 font-bold">
                    ${(rental.total_charged || 0).toFixed(2)}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4 text-xs font-mono">
                  <div>
                    <span className="text-slate-500">Invoice:</span> {rental.invoice_number || 'N/A'}
                  </div>
                  <div>
                    <span className="text-slate-500">Daily Rate:</span> ${rental.daily_rate}/day
                  </div>
                  <div>
                    <span className="text-slate-500">Days Billed:</span> {rental.days_billed} days
                  </div>
                  <div>
                    <span className="text-slate-500">Dates:</span> {rental.start_date} → {rental.end_date}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 text-xs">
                No rental reimbursement claim attached.
              </div>
            )}
          </div>
        ) : (
          <div>
            {medical.length > 0 ? (
              <div className="space-y-3">
                {medical.map((m: any, idx: number) => (
                  <div key={idx} className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm text-white">{m.provider_name}</span>
                      <span className="font-mono text-xs text-emerald-400 font-bold">
                        ${(m.total_billed || 0).toFixed(2)}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono text-slate-400">
                      <div>
                        <span className="text-slate-500">Patient:</span> {m.patient_name}
                      </div>
                      <div>
                        <span className="text-slate-500">Service Date:</span> {m.date_of_service}
                      </div>
                      <div className="col-span-2">
                        <span className="text-slate-500">Diagnosis/Care:</span> {m.diagnosis_or_treatment}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 text-xs">
                No medical payments (MedPay) claims attached.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
