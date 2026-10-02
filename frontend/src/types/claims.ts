export interface ClaimListItem {
  claim_id: string;
  policyholder_name?: string;
  policyholder?: string;
  filing_channel?: string;
  vehicle_summary?: string;
  vehicle?: string;
  incident_date?: string;
  total_claimed?: number;
  claimed_amount?: number;
  attached_documents?: string[];
  status?: string;
}

export interface ClaimListResponse {
  claims: ClaimListItem[];
  total: number;
}

export interface ClaimDetailResponse {
  claim_id: string;
  fnol_raw: any;
  estimate_raw: any;
  policy_raw: any;
  rental_raw?: any;
  medical_raw?: any;
  third_party_raw?: any;
}

export interface RunClaimResponse {
  claim_id: string;
  run_id: string;
  thread_id: string;
  status: string;
  message: string;
}

export interface RunStatusResponse {
  claim_id: string;
  run_id: string;
  thread_id: string;
  status: string;
  current_phase: string;
  active_node?: string;
  step_count: number;
  total_tokens: number;
  total_cost_usd: number;
  is_paused_at_gate: boolean;
  terminal_status?: string;
  final_payout_amount?: number;
  payout_breakdown?: Record<string, number>;
  settlement_summary?: string;
  error?: string;
}

export interface ThreadStateResponse {
  thread_id: string;
  claim_id?: string;
  current_phase?: string;
  next_nodes: string[];
  is_interrupted: boolean;
  step_count: number;
  total_tokens: number;
  total_cost_usd: number;
  values: Record<string, any>;
}

export interface ApprovalDossier {
  claim_id: string;
  thread_id: string;
  policyholder_vehicle?: string;
  repair_shop?: string;
  fraud_risk_score?: number;
  fraud_risk_level?: string;
  siu_referral_recommended?: boolean;
  detected_fraud_signals?: string[];
  actual_cash_value?: number;
  repair_to_acv_ratio?: number;
  is_total_loss_candidate?: boolean;
  endorsements_validated?: string[];
  applied_exclusions?: string[];
  clause_audit_notes?: string[];
  discrepancy_details?: string[];
  itemized_payout_breakdown?: {
    vehicle_repair?: number;
    rental_car?: number;
    medical_payments?: number;
  };
  total_proposed_payout: number;
  policy_collision_limit?: number;
  deductible_applied?: number;
  rental_reimbursement_eligible?: number;
  medical_payments_eligible?: number;
  liability_warning?: string;
  recommendation?: string;
  justification?: string;
  action_required?: string;
}

export interface PendingApprovalItem {
  thread_id: string;
  claim_id: string;
  run_id?: string;
  total_proposed_payout: number;
  recommendation?: string;
  fraud_risk_score?: number;
  dossier?: ApprovalDossier;
}

export interface HumanDecisionPayload {
  approver_id: string;
  action: 'approve' | 'partial_approve' | 'reject' | 'escalate_siu';
  authorized_amount: number;
  comments: string;
}

export interface StreamEvent {
  event: string;
  data: any;
  timestamp: string;
}

export interface SystemHealth {
  status: string;
  version: string;
  checkpointer_status: string;
  database_status: string;
}
