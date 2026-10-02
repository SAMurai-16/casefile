import { useState, useEffect } from 'react';
import {
  Play,
  RotateCw,
  FileText,
  Activity,
  UserCheck,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { Header } from './components/Header';
import { ClaimSidebar } from './components/ClaimSidebar';
import { PipelineVisualizer } from './components/PipelineVisualizer';
import { EventStreamLog } from './components/EventStreamLog';
import { EvidenceViewer } from './components/EvidenceViewer';
import { MLRiskCard } from './components/MLRiskCard';
import { StateTreeViewer } from './components/StateTreeViewer';
import { HumanApprovalModal } from './components/HumanApprovalModal';
import { IngestClaimModal } from './components/IngestClaimModal';
import { AnalyticsModal } from './components/AnalyticsModal';
import {
  getSystemHealth,
  listClaims,
  getClaim,
  runClaim,
  getRunStatus,
  getRunState,
  getApprovalDossier,
  submitHumanDecision,
  getAnalyticsSummary,
} from './api/client';
import {
  ClaimListItem,
  ClaimDetailResponse,
  RunStatusResponse,
  ThreadStateResponse,
  StreamEvent,
  SystemHealth,
  ApprovalDossier,
  HumanDecisionPayload,
} from './types/claims';

export function App() {
  // Navigation & Data State
  const [claims, setClaims] = useState<ClaimListItem[]>([]);
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const [claimDetail, setClaimDetail] = useState<ClaimDetailResponse | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [isLoadingClaims, setIsLoadingClaims] = useState(false);

  // Execution & Stream State
  const [activeRun, setActiveRun] = useState<RunStatusResponse | null>(null);
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [autoApproveToggle, setAutoApproveToggle] = useState(false);
  const [threadState, setThreadState] = useState<ThreadStateResponse | null>(null);

  // Modals & Drawers
  const [dossier, setDossier] = useState<ApprovalDossier | null>(null);
  const [isApprovalModalOpen, setIsApprovalModalOpen] = useState(false);
  const [isIngestModalOpen, setIsIngestModalOpen] = useState(false);
  const [isAnalyticsModalOpen, setIsAnalyticsModalOpen] = useState(false);
  const [analytics, setAnalytics] = useState<any>(null);
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false);

  // Active Center Tab
  const [activeTab, setActiveTab] = useState<'stream' | 'evidence' | 'ml_risk' | 'state'>('stream');

  // Load initial health and claims list
  useEffect(() => {
    loadHealthAndClaims();
  }, []);

  const loadHealthAndClaims = async () => {
    setIsLoadingClaims(true);
    try {
      const [h, c] = await Promise.all([getSystemHealth(), listClaims()]);
      setHealth(h);
      setClaims(c.claims);
      if (c.claims.length > 0 && !selectedClaimId) {
        setSelectedClaimId(c.claims[0].claim_id);
      }
    } catch (err) {
      console.error('Initialization error:', err);
    } finally {
      setIsLoadingClaims(false);
    }
  };

  // Load claim details when selected claim changes
  useEffect(() => {
    if (!selectedClaimId) return;
    loadClaimDetails(selectedClaimId);
  }, [selectedClaimId]);

  const loadClaimDetails = async (id: string) => {
    try {
      const detail = await getClaim(id);
      setClaimDetail(detail);
      // Reset run-specific view if selecting a new claim
      if (activeRun?.claim_id !== id) {
        setActiveRun(null);
        setThreadState(null);
        setStreamEvents([]);
      }
    } catch (err) {
      console.error('Failed to load claim detail:', err);
    }
  };

  // Trigger Graph Execution and Start Real-Time SSE Stream
  const handleStartRun = async () => {
    if (!selectedClaimId) return;

    setStreamEvents([]);
    setIsStreaming(true);
    setActiveTab('stream');

    try {
      const res = await runClaim(selectedClaimId, autoApproveToggle);
      const runId = res.run_id;
      const threadId = res.thread_id;

      setActiveRun({
        claim_id: res.claim_id,
        run_id: runId,
        thread_id: threadId,
        status: 'running',
        current_phase: 'intake',
        active_node: 'supervisor',
        step_count: 0,
        total_tokens: 0,
        total_cost_usd: 0.0,
        is_paused_at_gate: false,
      });

      // Connect to Server-Sent Events (SSE)
      const sseUrl = `/api/v1/claims/${encodeURIComponent(selectedClaimId)}/runs/${encodeURIComponent(runId)}/stream`;
      const es = new EventSource(sseUrl);

      es.addEventListener('connected', (e) => {
        const data = JSON.parse(e.data);
        appendStreamEvent('connected', data);
      });

      es.addEventListener('step', (e) => {
        const data = JSON.parse(e.data);
        appendStreamEvent('step', data);
        setActiveRun((prev) =>
          prev
            ? {
                ...prev,
                current_phase: data.phase,
                active_node: data.node,
                step_count: data.step_count,
                total_tokens: data.total_tokens,
                total_cost_usd: data.total_cost_usd,
              }
            : null
        );
      });

      es.addEventListener('gate_paused', async (e) => {
        const data = JSON.parse(e.data);
        appendStreamEvent('gate_paused', data);
        setIsStreaming(false);

        setActiveRun((prev) =>
          prev
            ? {
                ...prev,
                status: 'paused_at_gate',
                is_paused_at_gate: true,
                current_phase: 'human_gate',
              }
            : null
        );

        // Fetch dossier and state
        try {
          const d = await getApprovalDossier(threadId);
          setDossier(d);
          setIsApprovalModalOpen(true);
          const st = await getRunState(selectedClaimId, runId);
          setThreadState(st);
        } catch (err) {
          console.error('Failed to fetch approval dossier:', err);
        }
      });

      es.addEventListener('completed', async (e) => {
        const data = JSON.parse(e.data);
        appendStreamEvent('completed', data);
        setIsStreaming(false);

        setActiveRun((prev) =>
          prev
            ? {
                ...prev,
                status: 'completed',
                is_paused_at_gate: false,
                terminal_status: data.terminal_status,
                final_payout_amount: data.final_payout_amount,
                payout_breakdown: data.payout_breakdown,
                settlement_summary: data.settlement_summary,
              }
            : null
        );

        // Fetch final state snapshot
        try {
          const st = await getRunState(selectedClaimId, runId);
          setThreadState(st);
          // Refresh claims list badges
          const c = await listClaims();
          setClaims(c.claims);
        } catch (err) {
          console.error('Failed to fetch completed state:', err);
        }
      });

      es.addEventListener('error', (e: any) => {
        setIsStreaming(false);
        try {
          const data = JSON.parse(e.data);
          appendStreamEvent('error', data);
        } catch {
          // Normal close or connection drop
        }
        es.close();
      });

      es.addEventListener('end', () => {
        setIsStreaming(false);
        es.close();
      });
    } catch (err: any) {
      setIsStreaming(false);
      alert(`Failed to start run: ${err.message}`);
    }
  };

  const appendStreamEvent = (eventType: string, data: any) => {
    setStreamEvents((prev) => [
      ...prev,
      {
        event: eventType,
        data,
        timestamp: new Date().toLocaleTimeString(),
      },
    ]);
  };

  // Submit Decision for Human Gate
  const handleSubmitDecision = async (threadId: string, decision: HumanDecisionPayload) => {
    setIsSubmittingDecision(true);
    try {
      await submitHumanDecision(threadId, decision);
      setIsApprovalModalOpen(false);

      if (selectedClaimId && activeRun) {
        // Fetch updated run state
        const st = await getRunState(selectedClaimId, activeRun.run_id);
        setThreadState(st);
        const status = await getRunStatus(selectedClaimId, activeRun.run_id);
        setActiveRun(status);
      }

      // Refresh claims list
      const c = await listClaims();
      setClaims(c.claims);
    } catch (err: any) {
      alert(`Failed to submit decision: ${err.message}`);
    } finally {
      setIsSubmittingDecision(false);
    }
  };

  const handleOpenAnalytics = async () => {
    try {
      const data = await getAnalyticsSummary();
      setAnalytics(data);
      setIsAnalyticsModalOpen(true);
    } catch (err: any) {
      alert(`Failed to load analytics: ${err.message}`);
    }
  };

  const fnol = claimDetail?.fnol_raw || {};
  const currentVehicle = fnol.vehicle_info
    ? `${fnol.vehicle_info.year} ${fnol.vehicle_info.make} ${fnol.vehicle_info.model}`
    : `${fnol.vehicle_year || ''} ${fnol.vehicle_make || ''} ${fnol.vehicle_model || ''}`.trim() || 'Vehicle Not Specified';

  const policyholder = fnol.policyholder_name || fnol.insured_driver || 'Insured';
  const claimedTotal =
    claimDetail?.estimate_raw?.cost_summary?.grand_total ||
    claimDetail?.estimate_raw?.financial_summary?.grand_total ||
    claimDetail?.estimate_raw?.claimed_grand_total ||
    0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <Header
        health={health}
        onOpenIngest={() => setIsIngestModalOpen(true)}
        onOpenAnalytics={handleOpenAnalytics}
        totalTokens={activeRun?.total_tokens || 0}
        totalCost={activeRun?.total_cost_usd || 0.0}
      />

      {/* Main Workspace Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar */}
        <ClaimSidebar
          claims={claims}
          selectedClaimId={selectedClaimId}
          onSelectClaim={(id) => setSelectedClaimId(id)}
          isLoading={isLoadingClaims}
        />

        {/* Center Main Stage */}
        <main className="flex-1 flex flex-col overflow-y-auto p-6 space-y-6">
          {/* Claim Hero Banner & Run Actions */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center space-x-2.5">
                <span className="font-mono text-base font-bold text-sky-400">
                  {selectedClaimId || 'No Claim Selected'}
                </span>
                <span className="text-slate-500">•</span>
                <span className="text-sm font-semibold text-white">{policyholder}</span>
                <span className="text-slate-500">•</span>
                <span className="text-xs text-slate-300 font-medium">{currentVehicle}</span>
              </div>
              <p className="text-xs text-slate-400">
                Incident Date: {fnol.incident_date || 'N/A'} | Location: {fnol.incident_location || 'N/A'} | Claimed: <span className="font-mono text-slate-200 font-semibold">${(claimedTotal || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </p>
            </div>

            {/* Run Controls */}
            <div className="flex items-center space-x-3">
              {/* Auto-Approve Toggle */}
              <label className="flex items-center space-x-2 cursor-pointer bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-xs text-slate-300 select-none">
                <input
                  type="checkbox"
                  checked={autoApproveToggle}
                  onChange={(e) => setAutoApproveToggle(e.target.checked)}
                  className="rounded text-sky-500 focus:ring-0 bg-slate-900 border-slate-700"
                />
                <span className="text-[11px]">Auto-Approve Gate</span>
              </label>

              {/* Review Dossier Button (if paused at gate) */}
              {activeRun?.is_paused_at_gate && (
                <button
                  onClick={() => setIsApprovalModalOpen(true)}
                  className="flex items-center space-x-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs px-4 py-2 rounded-lg font-bold shadow-md transition animate-bounce"
                >
                  <UserCheck className="w-4 h-4" />
                  <span>Review Dossier</span>
                </button>
              )}

              {/* Trigger Run Button */}
              <button
                disabled={isStreaming}
                onClick={handleStartRun}
                className={`flex items-center space-x-2 text-xs px-5 py-2 rounded-lg font-bold shadow-md transition ${
                  isStreaming
                    ? 'bg-slate-800 text-slate-400 cursor-not-allowed'
                    : 'bg-sky-600 hover:bg-sky-500 text-white shadow-sky-600/30'
                }`}
              >
                {isStreaming ? (
                  <>
                    <RotateCw className="w-4 h-4 animate-spin text-sky-400" />
                    <span>Orchestrating...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-white" />
                    <span>Run Claim Graph</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Visual Agent Pipeline */}
          <PipelineVisualizer
            currentPhase={activeRun?.current_phase || 'intake'}
            activeNode={activeRun?.active_node || null}
            terminalStatus={activeRun?.terminal_status || null}
            isPausedAtGate={activeRun?.is_paused_at_gate || false}
            stepCount={activeRun?.step_count || 0}
          />

          {/* Center Tabs Navigation */}
          <div className="flex border-b border-slate-800 space-x-4 text-xs font-semibold">
            <button
              onClick={() => setActiveTab('stream')}
              className={`pb-2.5 px-2 border-b-2 flex items-center space-x-2 transition ${
                activeTab === 'stream'
                  ? 'border-sky-500 text-sky-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Activity className="w-4 h-4" />
              <span>Real-Time SSE Stream ({streamEvents.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('evidence')}
              className={`pb-2.5 px-2 border-b-2 flex items-center space-x-2 transition ${
                activeTab === 'evidence'
                  ? 'border-sky-500 text-sky-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Evidence & Extractions</span>
            </button>

            <button
              onClick={() => setActiveTab('ml_risk')}
              className={`pb-2.5 px-2 border-b-2 flex items-center space-x-2 transition ${
                activeTab === 'ml_risk'
                  ? 'border-sky-500 text-sky-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <ShieldCheck className="w-4 h-4" />
              <span>ML Fraud & Valuation Risk</span>
            </button>

            <button
              onClick={() => setActiveTab('state')}
              className={`pb-2.5 px-2 border-b-2 flex items-center space-x-2 transition ${
                activeTab === 'state'
                  ? 'border-sky-500 text-sky-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Sparkles className="w-4 h-4" />
              <span>Full ClaimState Snapshot</span>
            </button>
          </div>

          {/* Tab Content Display Area */}
          <div className="flex-1 min-h-[420px]">
            {activeTab === 'stream' && (
              <EventStreamLog
                events={streamEvents}
                isConnected={isStreaming}
                totalTokens={activeRun?.total_tokens || 0}
                totalCost={activeRun?.total_cost_usd || 0.0}
                stepCount={activeRun?.step_count || 0}
              />
            )}

            {activeTab === 'evidence' && (
              <EvidenceViewer
                extraction={threadState?.values?.extraction}
                
              />
            )}

            {activeTab === 'ml_risk' && (
              <MLRiskCard investigation={threadState?.values?.investigation} />
            )}

            {activeTab === 'state' && (
              <StateTreeViewer stateValues={threadState?.values || {}} />
            )}
          </div>
        </main>
      </div>

      {/* Human-in-the-Loop Approval Modal */}
      <HumanApprovalModal
        isOpen={isApprovalModalOpen}
        onClose={() => setIsApprovalModalOpen(false)}
        dossier={dossier}
        threadId={activeRun?.thread_id || null}
        onSubmitDecision={handleSubmitDecision}
        isSubmitting={isSubmittingDecision}
      />

      {/* Ingest Claim Modal */}
      <IngestClaimModal
        isOpen={isIngestModalOpen}
        onClose={() => setIsIngestModalOpen(false)}
        onSuccess={async (newClaimId) => {
          await loadHealthAndClaims();
          setSelectedClaimId(newClaimId);
        }}
      />

      {/* Analytics Modal */}
      <AnalyticsModal
        isOpen={isAnalyticsModalOpen}
        onClose={() => setIsAnalyticsModalOpen(false)}
        analytics={analytics}
      />
    </div>
  );
}

export default App;
