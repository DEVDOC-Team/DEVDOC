/**
 * DEVDOC Frontend API Types
 * Strictly aligned with verified backend schemas in backend/app/schemas/
 */

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_active: boolean;
  is_superuser: boolean;
  provider?: string | null;
  provider_user_id?: string | null;
  last_sign_in_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserUpdate {
  full_name?: string | null;
  avatar_url?: string | null;
}

export interface AuthSyncResponse {
  success: boolean;
  message: string;
  user: User;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  settings_json: string | null;
  owner_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  slug?: string | null;
  settings_json?: string | null;
}

export interface ProjectUpdate {
  name?: string;
  description?: string | null;
  settings_json?: string | null;
  is_active?: boolean;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProjectDeleteResponse {
  success: boolean;
  message: string;
  project_id: string;
}

export interface GitHubConnectionResponse {
  connected: boolean;
  github_user_id: string | null;
  github_username: string | null;
  avatar_url: string | null;
  scope: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface GitHubConnectResponse {
  authorization_url: string;
  state: string;
}

export interface GitHubDisconnectResponse {
  success: boolean;
  message: string;
}

export interface GitHubRepositoryInfo {
  id: number;
  name: string;
  full_name: string;
  owner: string;
  is_private: boolean;
  html_url: string;
  description: string | null;
  default_branch: string;
  language: string | null;
}

export interface GitHubRepositoriesListResponse {
  items: GitHubRepositoryInfo[];
  page: number;
  per_page: number;
  total: number;
}

export interface RepositoryResponse {
  id: string;
  project_id: string;
  github_repo_id: number;
  full_name: string;
  owner: string;
  name: string;
  default_branch: string;
  is_private: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectRepositoryAttach {
  full_name: string;
}

export interface ProjectRepositoryDeleteResponse {
  success: boolean;
  message: string;
  repository_id: string;
}

export interface HealthResponse {
  success: boolean;
  service: string;
  status: string;
}

export interface ReadinessResponse {
  success: boolean;
  service: string;
  status: string;
  checks: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Phase 3: Incidents, Investigations & Approvals Schemas
// ---------------------------------------------------------------------------

export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical';
export type IncidentStatus = 'open' | 'investigating' | 'mitigated' | 'resolved' | 'closed';
export type IncidentSource = 'manual' | 'alert' | 'sentry' | 'datadog' | 'prometheus' | 'cloudwatch' | 'pagerduty';

export interface Incident {
  id: string;
  project_id: string;
  repository_id: string | null;
  reported_by_id: string | null;
  title: string;
  description: string | null;
  severity: IncidentSeverity;
  status: IncidentStatus;
  source: IncidentSource;
  external_reference: string | null;
  affected_users: number;
  detected_at: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentCreate {
  title: string;
  description?: string | null;
  severity?: IncidentSeverity;
  source?: IncidentSource;
  status?: IncidentStatus;
  external_reference?: string | null;
  repository_id?: string | null;
  affected_users?: number;
  detected_at?: string | null;
}

export interface IncidentUpdate {
  title?: string | null;
  description?: string | null;
  severity?: IncidentSeverity | null;
  status?: IncidentStatus | null;
  source?: IncidentSource | null;
  external_reference?: string | null;
  repository_id?: string | null;
  affected_users?: number | null;
}

export interface IncidentStatusUpdate {
  status: IncidentStatus;
}

export interface IncidentListResponse {
  items: Incident[];
  total: number;
  limit: number;
  offset: number;
}

export interface IncidentDeleteResponse {
  success: boolean;
  message: string;
  incident_id: string;
}

export type InvestigationStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface Investigation {
  id: string;
  project_id: string;
  incident_id: string;
  initiated_by_id: string | null;
  status: InvestigationStatus;
  summary: string | null;
  tokens_used: number;
  estimated_cost_usd: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvestigationCreate {
  summary?: string | null;
  status?: InvestigationStatus;
}

export interface InvestigationUpdate {
  summary?: string | null;
  error_message?: string | null;
  status?: InvestigationStatus | null;
}

export interface InvestigationStatusUpdate {
  status: InvestigationStatus;
  error_message?: string | null;
}

export interface InvestigationListResponse {
  items: Investigation[];
  total: number;
  limit: number;
  offset: number;
}

export interface InvestigationDeleteResponse {
  success: boolean;
  message: string;
  investigation_id: string;
}

export interface InvestigationRunResponse extends Investigation {
  evidence_count: number;
  has_root_cause_analysis: boolean;
  has_fix_proposal: boolean;
  approval_artifact_id: string | null;
  approval_status: string | null;
}

export type ApprovalDecision = 'approved' | 'rejected' | 'cancelled';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'cancelled' | 'expired';

export type RCAStatus = 'root_cause_identified' | 'multiple_plausible_causes' | 'insufficient_evidence';
export type RCAConfidence = 'low' | 'medium' | 'high';
export type RCACategory =
  | 'code_defect'
  | 'configuration'
  | 'dependency'
  | 'infrastructure'
  | 'resource_exhaustion'
  | 'network'
  | 'database'
  | 'deployment'
  | 'authentication'
  | 'external_service'
  | 'human_change'
  | 'unknown';

export type EvidenceClassification = 'fact' | 'external_knowledge';

export interface RCAEvidenceReference {
  evidence_id: string;
  classification: EvidenceClassification;
  source: string;
  evidence_type: string;
  timestamp: string;
  source_url?: string | null;
  title: string;
  summary: string;
}

export interface RCAClaim {
  statement: string;
  evidence_references: RCAEvidenceReference[];
}

export interface CandidateRootCause {
  candidate_id: string;
  classification?: 'hypothesis';
  statement: string;
  category: RCACategory;
  confidence: RCAConfidence;
  rank: number;
  supporting_evidence: RCAEvidenceReference[];
  contradicting_evidence: RCAEvidenceReference[];
  contributing_factors: RCAClaim[];
  triggering_events: RCAClaim[];
  observed_symptoms: RCAClaim[];
  temporal_relationship_ids?: string[];
  uncertainty: string;
  rationale: string;
  ranking_basis: string;
}

export interface CausalStep {
  step: number;
  description: string;
  evidence_ids?: string[];
}

export interface RootCauseAnalysis {
  analysis_id?: string;
  investigation_id?: string;
  execution_id?: string;
  status?: RCAStatus;
  confidence?: RCAConfidence;
  candidates?: CandidateRootCause[];
  selected_root_cause?: CandidateRootCause | null;
  observed_facts?: RCAEvidenceReference[];
  reasoning_summary_evidence?: RCAEvidenceReference[];
  evidence_references?: RCAEvidenceReference[];
  contradictions?: RCAEvidenceReference[];
  uncertainties?: string[];
  missing_information?: string[];
  reasoning_summary?: string;
  analyzed_at?: string;
  // Fallback and display properties
  claim?: string;
  confidence_score?: number;
  causal_chain?: CausalStep[];
  failure_modes?: string[];
}

export type FixChangeType =
  | 'code_change'
  | 'configuration_change'
  | 'dependency_change'
  | 'infrastructure_change'
  | 'deployment_change'
  | 'database_change'
  | 'monitoring_change'
  | 'rollback'
  | 'documentation_change'
  | 'unknown';

export type FixRiskCategory =
  | 'data_loss'
  | 'downtime'
  | 'security'
  | 'compatibility'
  | 'performance'
  | 'regression'
  | 'migration'
  | 'dependency'
  | 'infrastructure'
  | 'unknown';

export type FixRiskSeverity = 'low' | 'medium' | 'high' | 'critical' | 'unknown';

export interface FixChange {
  target: string;
  target_path?: string | null;
  operation: string;
  current_state?: string | null;
  proposed_state?: string | null;
  proposed_diff?: string | null;
  patch_status?: string | null;
  reason: string;
  evidence_references?: string[];
  tests_required?: string[];
}

export interface FixRisk {
  category: FixRiskCategory;
  severity: FixRiskSeverity;
  description: string;
  mitigation: string;
}

export interface FixVerificationStep {
  description: string;
  expected_result: string;
  evidence_required?: string[];
}

export interface FixRollbackStep {
  description: string;
  trigger: string;
  expected_result: string;
}

export interface FixProposal {
  proposal_id?: string;
  investigation_id?: string;
  root_cause_reference?: string;
  status?: string;
  summary?: string;
  rationale?: string;
  affected_components?: string[];
  change_type?: FixChangeType;
  changes?: FixChange[];
  prerequisites?: string[];
  risks?: FixRisk[];
  verification_plan?: FixVerificationStep[];
  rollback_plan?: FixRollbackStep[];
  evidence_references?: string[];
  confidence?: number;
  change_scope?: string;
  human_approval_required?: boolean;
  generated_at?: string;
  // Legacy / fallback fields
  title?: string;
  explanation?: string;
  diff?: string;
  target_files?: string[];
}

export type VerificationStatus =
  | 'passed'
  | 'failed'
  | 'inconclusive'
  | 'timeout'
  | 'cancelled'
  | 'unsafe'
  | 'setup_failed'
  | 'not_run'
  | 'running'
  | 'unavailable';

export interface VerificationStepReview {
  step_id: string;
  description: string;
  status: string;
  exit_code: number | null;
  duration_ms: number;
  expected_result: string;
  observed_result: string;
}

export interface VerificationReview {
  verification_id: string;
  investigation_id: string;
  proposal_id: string;
  status: VerificationStatus;
  started_at: string;
  completed_at: string;
  verification_steps: VerificationStepReview[];
  passed_steps: number;
  failed_steps: number;
  risk_findings: string[];
  cleanup_status: string;
  summary: string;
}

export interface ApprovalReview {
  root_cause: RootCauseAnalysis;
  proposal: FixProposal;
  verification: VerificationReview;
}

export interface ApprovalResponse {
  id: string;
  fix_proposal_id: string;
  verification_id: string | null;
  status: ApprovalStatus;
  requested_by_id: string;
  approver_id: string | null;
  decision: ApprovalDecision | null;
  rationale: string | null;
  requested_at: string;
  decided_at: string | null;
  expires_at: string | null;
  proposal_fingerprint: string | null;
  verification_fingerprint: string | null;
  review: ApprovalReview | null;
}

export interface ApprovalListResponse {
  items: ApprovalResponse[];
  total: number;
}

export interface ApprovalDecisionInput {
  reason: string;
}

export interface ApprovalAuditEvent {
  id: string;
  actor_id: string | null;
  action: string;
  details: Record<string, any>;
  created_at: string;
}

export interface ApprovalAuditListResponse {
  items: ApprovalAuditEvent[];
  total: number;
  limit: number;
  offset: number;
}
