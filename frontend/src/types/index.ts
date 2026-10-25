export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface Company {
  id: string;
  name: string;
  slug: string;
  role?: string;
  created_at: string;
}

export interface ColumnProfile {
  name: string;
  inferred_type: 'numeric' | 'categorical' | 'datetime' | 'boolean' | 'text';
  missing_count: number;
  missing_percentage: number;
  unique_count: number;
  is_constant: boolean;
  is_identifier: boolean;
  sample_values: any[];
  numeric_stats?: {
    min: number;
    max: number;
    mean: number;
    median: number;
    std: number;
    q25: number;
    q75: number;
  };
  top_categories?: Array<{
    value: string;
    count: number;
    percentage: number;
  }>;
  datetime_stats?: {
    min_date: string;
    max_date: string;
  };
}

export interface DataQualityIssue {
  type: 'warning' | 'error' | 'info';
  category: string;
  column: string | null;
  message: string;
}

export interface DatasetProfile {
  summary: {
    row_count: number;
    column_count: number;
    duplicate_rows: number;
    duplicate_row_percentage: number;
    health_score: number;
  };
  columns: ColumnProfile[];
  issues: DataQualityIssue[];
  candidates: {
    dates: string[];
    targets: string[];
    entities: string[];
  };
}

export interface Dataset {
  id: string;
  name: string;
  original_filename: string;
  file_format: string;
  file_size_bytes: number;
  row_count: number;
  column_count: number;
  checksum_sha256: string;
  processing_status: string;
  validation_summary?: {
    row_count: number;
    column_count: number;
    duplicate_rows: number;
    duplicate_row_percentage: number;
    health_score: number;
  };
  created_at: string;
  profile?: DatasetProfile;
}

export interface DatasetListResponse {
  items: Dataset[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DatasetPreviewResponse {
  total_rows: number;
  page: number;
  page_size: number;
  total_pages: number;
  columns: string[];
  records: Record<string, any>[];
}

export interface SuggestedConfig {
  recommended_task: string;
  target_column: string | null;
  feature_columns: string[];
  date_column: string | null;
  entity_columns: string[] | null;
  excluded_columns: string[] | null;
}

export interface DatasetConfiguration {
  id: string;
  dataset_id: string;
  task_type: 'regression' | 'forecasting' | 'classification' | 'anomaly';
  target_column: string | null;
  feature_columns: string[];
  date_column: string | null;
  entity_columns: string[] | null;
  excluded_columns: string[] | null;
  configuration_version: number;
  updated_at: string;
}

export interface CandidateModel {
  id: string;
  algorithm: string;
  algorithm_display_name: string;
  model_family: string;
  status: 'SUCCESS' | 'FAILED';
  hyperparameters?: Record<string, any>;
  metrics?: Record<string, any>;
  evaluation_summary?: Record<string, any>;
  sample_predictions?: Array<{
    actual: any;
    predicted: any;
    residual?: number;
  }>;
  feature_importances?: Record<string, number>;
  artifact_size_bytes: number;
  training_duration_seconds: number;
  is_active: boolean;
  error_details?: string | null;
  created_at: string;
}

export interface TrainingRun {
  id: string;
  dataset_id: string;
  task_type: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'PARTIALLY_FAILED' | 'FAILED' | 'CANCELLED';
  target_column?: string | null;
  feature_columns: string[];
  date_column?: string | null;
  entity_columns?: string[] | null;
  train_row_count: number;
  val_row_count: number;
  val_time_range?: { start: string; end: string } | null;
  duration_seconds: number;
  candidate_count: number;
  error_message?: string | null;
  created_at: string;
  models?: CandidateModel[];
}

export interface ModelComparisonResponse {
  run_id: string;
  task_type: string;
  target_column?: string | null;
  date_column?: string | null;
  primary_metric: string;
  primary_metric_direction?: 'lower_is_better' | 'higher_is_better' | 'diagnostic';
  primary_metric_display_name?: string | null;
  is_unsupervised?: boolean;
  task_objective?: string | null;
  metrics_table: CandidateModel[];
}

export interface ModelSchemaField {
  name: string;
  type: 'numeric' | 'categorical' | 'text';
  sample_values: any[];
  default: any;
}

export interface ModelSchemaResponse {
  model_id: string;
  algorithm: string;
  algorithm_display_name: string;
  task_type: string;
  target_column?: string | null;
  fields: ModelSchemaField[];
  classes?: string[] | null;
}

export interface PredictionResultItem {
  row_index: number;
  prediction: any;
  probabilities?: number[] | null;
  class_labels?: string[] | null;
  anomaly_score?: number | null;
}

export interface PredictionResponse {
  prediction_id: string;
  model_id: string;
  algorithm: string;
  algorithm_display_name: string;
  task_type: string;
  total_rows: number;
  latency_ms: number;
  predictions: PredictionResultItem[];
  classes?: string[] | null;
}

export interface PredictionLog {
  id: string;
  model_id: string;
  dataset_id?: string | null;
  prediction_type: string;
  row_count: number;
  input_sample?: any[];
  output_sample?: any[];
  latency_ms: number;
  created_at: string;
}

export interface InventoryItem {
  sku: string;
  daily_demand: number;
  demand_std: number;
  lead_time_days: number;
  current_stock: number;
  safety_stock: number;
  reorder_point: number;
  days_of_supply: number;
  status: 'CRITICAL' | 'REORDER_NOW' | 'HEALTHY' | 'OVERSTOCK';
  unit_cost: number;
  total_value: number;
  recommended_reorder_qty: number;
  overstock_capital: number;
}

export interface InventoryKPIsResponse {
  dataset_id: string;
  dataset_name: string;
  service_level_percent: number;
  summary: {
    total_skus: number;
    critical_stockouts: number;
    reorder_needed: number;
    healthy_stock: number;
    overstocked: number;
    total_inventory_value: number;
    overstock_capital_at_risk: number;
  };
  columns_detected: Record<string, string | null>;
  items: InventoryItem[];
}

export interface CopilotResponse {
  answer: string;
  grounded_sources: string[];
  model_engine: string;
}

export interface WorkspaceMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: 'OWNER' | 'WORKER';
  created_at: string;
  is_active?: boolean;
}

export interface AddWorkerPayload {
  email: string;
  full_name: string;
  password: string;
  role?: 'OWNER' | 'WORKER';
}

export interface WorkspaceJoinRequest {
  id: string;
  company_id: string;
  company_name: string;
  company_slug?: string;
  user_id: string;
  email: string;
  full_name: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
  created_at: string;
  reviewed_at?: string | null;
  reviewed_by_id?: string | null;
  rejection_reason?: string | null;
  message?: string;
}

export interface WorkerJoinRequestPayload {
  full_name: string;
  email: string;
  password: string;
  workspace_slug: string;
}


