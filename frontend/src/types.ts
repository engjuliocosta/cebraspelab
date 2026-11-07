export interface SubtopicRecurrence {
  topic?: string;
  subtopic: string;
  recurrence_level: 'Muito Alta' | 'Alta' | 'Média' | 'Baixa' | string;
  recurrence_percentage: number;
  real_questions_found: number;
  periods_count?: number;
  min_recommended_questions: number;
  target_questions?: number;
  pages_reference: string;
  cebraspe_focus_points: string[];
}

export interface StoredPdfFileRecord {
  id?: number;
  file_id?: number;
  material_id?: number;
  filename: string;
  file_role: string;
  mime_type: string;
  file_size: number;
  sha256_hash: string;
  vault_filename: string;
  created_at: string;
}

export interface MaterialAnalysisResult {
  material_id: number;
  title: string;
  subject: string;
  area: string;
  total_pages: number;
  total_periods?: number;
  real_questions_count: number;
  analysis_summary: string;
  subtopics: SubtopicRecurrence[];
  stored_files?: StoredPdfFileRecord[];
  sample_real_questions: Array<{
    exam_info: string;
    statement: string;
    answer: string;
    commentary?: string;
    page_number?: number;
    subtopic?: string;
  }>;
}

export interface WordAnnotation {
  wordIndex: number;
  type: 'strike' | 'highlight';
}

export interface AssertionItem {
  id: number;
  battery_id: number;
  material_id?: number;
  item_number: number;
  subtopic: string;
  recurrence_level: string;
  command_text: string;
  statement: string;
  answer: 'C' | 'E';
  explanation: string;
  pdf_quote: string;
  pdf_page: string;
  trap_type: string;
  difficulty: string;
  inspired_by_real_question: string;
  is_favorite: boolean;
  answered_with_doubt?: boolean;
  user_answer: 'C' | 'E' | 'BLANK' | null;
  is_correct: number | null;
  annotations: WordAnnotation[];
  answered_at?: string | null;
  battery_title?: string;
  subject?: string;
  area?: string;
}

export interface QuestionBattery {
  id: number;
  material_id?: number;
  title: string;
  subject: string;
  area: string;
  depth: string;
  total_questions: number;
  recurrence_summary: SubtopicRecurrence[];
  created_at: string;
  assertions?: AssertionItem[];
  stats?: {
    total: number;
    answered: number;
    blank: number;
    correct: number;
    wrong: number;
    favorites: number;
    net_score: number;
  };
}

export interface AppSettings {
  gemini_api_key: string;
  masked_api_key: string;
  has_api_key: boolean;
  gemini_model: string;
  default_area: string;
  default_depth: string;
}

export interface ErrorNotebookData {
  items: AssertionItem[];
  subtopic_stats: Array<{
    subject: string;
    subtopic: string;
    total_answered: number;
    correct: number;
    wrong: number;
    blank: number;
  }>;
  trap_stats: Array<{
    trap_type: string;
    total_answered: number;
    wrong: number;
  }>;
}

export interface DiscursiveQuestion {
  id: number;
  material_id?: number;
  subject: string;
  subtopic: string;
  target_concept: string;
  trap_type: string;
  prompt_text: string;
  max_lines: number;
  expected_key_points: string[];
  pdf_reference_quote: string;
  pdf_page: string;
  created_at: string;
}

export interface DiscursiveSavedResponse {
  id?: number;
  response_id?: number;
  question_id: number;
  material_id?: number;
  subject: string;
  subtopic: string;
  target_concept: string;
  prompt_text: string;
  student_text: string;
  lines_used: number;
  max_lines?: number;
  char_count: number;
  score: number;
  feedback_text: string;
  covered_points: string[];
  missing_points: string[];
  pdf_reference_quote: string;
  pdf_page: string;
  created_at: string;
}

export interface TutorDiagnosisData {
  material_id: number;
  material_title: string;
  subject: string;
  stored_files: StoredPdfFileRecord[];
  weakness_stats: Array<{
    subtopic: string;
    total_answered: number;
    correct: number;
    wrong: number;
  }>;
  wrong_assertions_sample: AssertionItem[];
  content_summary: {
    target_subtopic: string;
    dominant_trap: string;
    errors_analyzed_count: number;
    executive_overview: string;
    golden_rule: string;
    key_periods_from_pdf: Array<{
      page: string;
      text: string;
      focus: string;
    }>;
  };
  discursive_question: DiscursiveQuestion;
}

export interface PresentedConceptItem {
  assertion_id: number;
  material_id?: number;
  subject: string;
  suggested_topic: string;
  suggested_subtopic: string;
  suggested_concept: string;
  suggested_subconcept: string;
  presented_concept_context: string;
  original_statement: string;
  official_answer: string;
  explanation: string;
  pdf_page: string;
  trap_type: string;
}

export interface AvailableTopicSubtopicOption {
  material_id: number;
  subject: string;
  topic: string;
  subtopic: string;
  pages_reference: string;
}

export interface ConceptRelationshipLink {
  id: number;
  material_id?: number;
  subject: string;
  topic: string;
  subtopic: string;
  concept: string;
  subconcept: string;
  summary_ids: number[];
  generated_questions_count: number;
  updated_at: string;
}

export interface ConceptsHierarchyData {
  presented_concepts_from_errors: PresentedConceptItem[];
  available_topics_and_subtopics: AvailableTopicSubtopicOption[];
  concept_relationships: ConceptRelationshipLink[];
}

export interface StudentErrorSummaryRecord {
  id: number;
  relationship_link_id?: number;
  material_id?: number;
  assertion_id?: number;
  subject: string;
  topic: string;
  subtopic: string;
  concept: string;
  subconcept: string;
  presented_concept_context: string;
  student_summary: string;
  personal_notes: string;
  trap_type: string;
  pdf_page: string;
  review_interval_days: number;
  review_cycle_count: number;
  created_at: string;
  last_reviewed_at?: string | null;
  next_review_at: string;
  is_due_for_3day_review?: boolean;
  days_until_review?: number;
  hierarchy_path?: string;
}

export interface SpacedReviewOverviewData {
  total_summaries: number;
  due_for_review_count: number;
  review_alert_active: boolean;
  review_interval_days: number;
  items: StudentErrorSummaryRecord[];
  due_items: StudentErrorSummaryRecord[];
  cycles_history: Array<{
    id: number;
    battery_id: number;
    summary_ids: number[];
    questions_generated: number;
    triggered_mode: string;
    triggered_at: string;
    next_scheduled_at: string;
  }>;
}

export interface StorageProviderMeta {
  id: string;
  name: string;
  requires_credentials: boolean;
  description: string;
}

export interface DefaultLocalDirectory {
  label: string;
  path: string;
  provider_type: string;
}

export interface ConnectorProvidersInfo {
  providers: StorageProviderMeta[];
  supported_extensions: string[];
  default_local_directories: DefaultLocalDirectory[];
}

export interface StorageConnectionRecord {
  id: number;
  name: string;
  provider_type: string;
  provider_label: string;
  target_path_or_folder_id: string;
  subject_hint: string;
  area_hint: string;
  has_api_key: boolean;
  has_access_token: boolean;
  api_key_masked: string;
  access_token_masked: string;
  app_key_masked: string;
  endpoint_url: string;
  local_sync_mirror_path: string;
  recursive_scan: boolean;
  auto_generate_questions: boolean;
  is_active: boolean;
  last_connected_at?: string | null;
  created_at: string;
  discovered_files_count?: number;
  files_with_questions_count?: number;
}

export interface DiscoveredStudyFileRecord {
  id: number;
  connection_id: number;
  provider_type: string;
  file_name: string;
  file_path_or_remote_id: string;
  file_ext: string;
  file_size: number;
  sha256_hash: string;
  status: string;
  stored_file_id?: number | null;
  material_id?: number | null;
  battery_id?: number | null;
  extracted_topics_count: number;
  extracted_questions_count: number;
  related_topics: Array<{
    topic: string;
    subtopic: string;
    concept: string;
    subconcept: string;
  }>;
  discovered_at: string;
  last_synced_at: string;
}

export interface FolderBrowserData {
  current_path: string;
  current_name: string;
  parent_path?: string | null;
  subfolders: Array<{
    name: string;
    path: string;
  }>;
  study_files_in_current: Array<{
    name: string;
    ext: string;
    size_bytes: number;
  }>;
  study_files_count: number;
}

export interface MultiFolderEntry {
  path: string;
  label: string;
  subject: string;
}

export interface MultiFolderWorkspaceRecord {
  id: number;
  name: string;
  subject_hint: string;
  area_hint: string;
  folders: MultiFolderEntry[];
  folders_count: number;
  connection_ids: number[];
  recursive_scan: boolean;
  auto_generate_questions: boolean;
  unified_battery_id?: number | null;
  total_files_found: number;
  last_synced_at?: string | null;
  created_at: string;
}

export interface ContrastiveConceptPair {
  id: string;
  subject: string;
  topic: string;
  subtopic: string;
  concept_a: string;
  concept_b: string;
  key_distinction: string;
  source?: string;
}

export interface AdaptiveEvaluationResult {
  battery_id: number;
  cycle_id?: number | null;
  total_questions: number;
  answered_questions: number;
  correct_answers: number;
  accuracy_ratio: number;
  accuracy_percentage: number;
  mastery_threshold_percentage: number;
  achieved_mastery: boolean;
  updated_summaries: Array<{
    summary_id: number;
    concept: string;
    subconcept: string;
    old_interval_days: number;
    new_interval_days: number;
    concept_accuracy_ratio: number;
    promoted: boolean;
    next_review_at: string;
  }>;
  updated_count: number;
}

export interface LocalBridgeStatus {
  bridge_online: boolean;
  bridge_version: string;
  ui_mode: 'github_pages_connected_to_local_pc' | 'local_direct_ui' | string;
  request_origin: string;
  top_level_pages_url: string;
  pc_environment: {
    os: string;
    os_release: string;
    arch: string;
    hostname: string;
  };
  local_storage: {
    sql_db_path: string;
    nosql_store_path: string;
    pdf_vault_dir: string;
    stored_files_count: number;
    saved_batteries_count: number;
    storage_connections_count: number;
    multi_folder_workspaces_count: number;
  };
  license: {
    is_activated: boolean;
    plan: string;
    license_key_masked: string;
    buyer_email: string;
    activated_at: string;
    top_level_pages_url: string;
  };
}




