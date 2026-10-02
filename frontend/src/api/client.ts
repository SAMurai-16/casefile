import {
  ClaimListResponse,
  ClaimDetailResponse,
  RunClaimResponse,
  RunStatusResponse,
  ThreadStateResponse,
  ApprovalDossier,
  PendingApprovalItem,
  HumanDecisionPayload,
  SystemHealth,
} from '../types/claims';

const BASE_URL = '/api/v1';

export async function getSystemHealth(): Promise<SystemHealth> {
  const res = await fetch(`${BASE_URL}/system/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function listClaims(): Promise<ClaimListResponse> {
  const res = await fetch(`${BASE_URL}/claims`);
  if (!res.ok) throw new Error(`Failed to list claims: ${res.statusText}`);
  return res.json();
}

export async function getClaim(claimId: string): Promise<ClaimDetailResponse> {
  const res = await fetch(`${BASE_URL}/claims/${encodeURIComponent(claimId)}`);
  if (!res.ok) throw new Error(`Failed to get claim: ${res.statusText}`);
  return res.json();
}

export async function ingestClaim(claimPackage: {
  fnol: any;
  estimate: any;
  policy: any;
  rental?: any;
  medical?: any;
  third_party?: any;
}): Promise<any> {
  const res = await fetch(`${BASE_URL}/claims`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(claimPackage),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Ingestion failed: ${res.statusText}`);
  }
  return res.json();
}

export async function runClaim(
  claimId: string,
  autoApprove = false,
  maxCost = 2.0
): Promise<RunClaimResponse> {
  const res = await fetch(`${BASE_URL}/claims/${encodeURIComponent(claimId)}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auto_approve: autoApprove, max_cost: maxCost }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Run trigger failed: ${res.statusText}`);
  }
  return res.json();
}

export async function getRunStatus(
  claimId: string,
  runId: string
): Promise<RunStatusResponse> {
  const res = await fetch(
    `${BASE_URL}/claims/${encodeURIComponent(claimId)}/runs/${encodeURIComponent(runId)}/status`
  );
  if (!res.ok) throw new Error(`Failed to fetch run status: ${res.statusText}`);
  return res.json();
}

export async function getRunState(
  claimId: string,
  runId: string
): Promise<ThreadStateResponse> {
  const res = await fetch(
    `${BASE_URL}/claims/${encodeURIComponent(claimId)}/runs/${encodeURIComponent(runId)}/state`
  );
  if (!res.ok) throw new Error(`Failed to fetch run state: ${res.statusText}`);
  return res.json();
}

export async function getThreadHistory(threadId: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/threads/${encodeURIComponent(threadId)}/history`);
  if (!res.ok) throw new Error(`Failed to fetch thread history: ${res.statusText}`);
  return res.json();
}

export async function getPendingApprovals(): Promise<PendingApprovalItem[]> {
  const res = await fetch(`${BASE_URL}/approval-gate/pending`);
  if (!res.ok) throw new Error(`Failed to fetch pending approvals: ${res.statusText}`);
  return res.json();
}

export async function getApprovalDossier(threadId: string): Promise<ApprovalDossier> {
  const res = await fetch(`${BASE_URL}/approval-gate/${encodeURIComponent(threadId)}`);
  if (!res.ok) throw new Error(`Failed to fetch approval dossier: ${res.statusText}`);
  return res.json();
}

export async function submitHumanDecision(
  threadId: string,
  decision: HumanDecisionPayload
): Promise<any> {
  const res = await fetch(
    `${BASE_URL}/approval-gate/${encodeURIComponent(threadId)}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(decision),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Approval decision failed: ${res.statusText}`);
  }
  return res.json();
}

export async function getAnalyticsSummary(): Promise<any> {
  const res = await fetch(`${BASE_URL}/analytics/summary`);
  if (!res.ok) throw new Error(`Failed to fetch analytics: ${res.statusText}`);
  return res.json();
}
