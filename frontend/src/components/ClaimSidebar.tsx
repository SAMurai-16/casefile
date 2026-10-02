import React, { useState } from 'react';
import { Search, Car, Calendar, Clock, CheckCircle2, AlertCircle } from 'lucide-react';
import { ClaimListItem } from '../types/claims';

interface ClaimSidebarProps {
  claims: ClaimListItem[];
  selectedClaimId: string | null;
  onSelectClaim: (claimId: string) => void;
  isLoading: boolean;
}

export const ClaimSidebar: React.FC<ClaimSidebarProps> = ({
  claims,
  selectedClaimId,
  onSelectClaim,
  isLoading,
}) => {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'pending'>('all');

  const filteredClaims = claims.filter((c) => {
    const policyholder = c.policyholder_name || c.policyholder || '';
    const vehicle = c.vehicle_summary || c.vehicle || '';
    const matchesSearch =
      c.claim_id.toLowerCase().includes(search.toLowerCase()) ||
      policyholder.toLowerCase().includes(search.toLowerCase()) ||
      vehicle.toLowerCase().includes(search.toLowerCase());

    if (filter === 'pending') {
      return matchesSearch && c.status === 'paused_at_gate';
    }
    return matchesSearch;
  });

  return (
    <aside className="w-80 bg-slate-900/90 border-r border-slate-800 flex flex-col h-[calc(100vh-61px)]">
      {/* Search & Filter Header */}
      <div className="p-4 border-b border-slate-800 space-y-3">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search claims, vehicles, insured..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-md pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 transition"
          />
        </div>

        <div className="flex items-center justify-between text-xs">
          <div className="flex space-x-1 bg-slate-950 p-1 rounded-md border border-slate-800">
            <button
              onClick={() => setFilter('all')}
              className={`px-2.5 py-1 rounded text-[11px] font-medium transition ${
                filter === 'all'
                  ? 'bg-sky-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              All ({claims.length})
            </button>
            <button
              onClick={() => setFilter('pending')}
              className={`px-2.5 py-1 rounded text-[11px] font-medium transition ${
                filter === 'pending'
                  ? 'bg-amber-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Gate Review
            </button>
          </div>
          <span className="text-slate-500 text-[11px]">{filteredClaims.length} shown</span>
        </div>
      </div>

      {/* Claim Cards List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60 p-2 space-y-1">
        {isLoading && claims.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs">Loading available claims...</div>
        ) : filteredClaims.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs">No claims found.</div>
        ) : (
          filteredClaims.map((c) => {
            const isSelected = c.claim_id === selectedClaimId;
            const policyholder = c.policyholder_name || c.policyholder || 'Insured';
            const vehicle = c.vehicle_summary || c.vehicle || 'Vehicle details';
            const amount = c.total_claimed ?? c.claimed_amount ?? 0;

            return (
              <div
                key={c.claim_id}
                onClick={() => onSelectClaim(c.claim_id)}
                className={`p-3 rounded-lg cursor-pointer transition border text-left ${
                  isSelected
                    ? 'bg-sky-950/40 border-sky-500/50 text-white shadow-sm'
                    : 'bg-slate-900/40 hover:bg-slate-850 border-transparent hover:border-slate-800 text-slate-300'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono text-xs font-bold text-sky-400">
                    Claim {c.claim_id}
                  </span>
                  {c.status === 'paused_at_gate' && (
                    <span className="flex items-center space-x-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] px-1.5 py-0.5 rounded font-medium">
                      <Clock className="w-3 h-3" />
                      <span>Review Req</span>
                    </span>
                  )}
                  {c.status === 'approved' && (
                    <span className="flex items-center space-x-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] px-1.5 py-0.5 rounded font-medium">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>Approved</span>
                    </span>
                  )}
                  {c.status === 'escalated_siu' && (
                    <span className="flex items-center space-x-1 bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[10px] px-1.5 py-0.5 rounded font-medium">
                      <AlertCircle className="w-3 h-3" />
                      <span>SIU Esc</span>
                    </span>
                  )}
                </div>

                <div className="text-xs font-medium text-slate-200 truncate">
                  {policyholder}
                </div>

                <div className="flex items-center space-x-2 text-[11px] text-slate-400 mt-1">
                  <div className="flex items-center space-x-1 truncate max-w-[170px]">
                    <Car className="w-3 h-3 text-slate-500 shrink-0" />
                    <span className="truncate">{vehicle}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 mt-2 pt-2 border-t border-slate-800/40">
                  <div className="flex items-center space-x-1 text-slate-500">
                    <Calendar className="w-3 h-3" />
                    <span>{c.incident_date || c.filing_channel || 'File'}</span>
                  </div>
                  {amount > 0 && (
                    <div className="font-mono font-semibold text-slate-200">
                      ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
