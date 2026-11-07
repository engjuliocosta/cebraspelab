import {
  AdaptiveEvaluationResult,
  AppSettings,
  AssertionItem,
  ConceptsHierarchyData,
  ConnectorProvidersInfo,
  ContrastiveConceptPair,
  DiscoveredStudyFileRecord,
  DiscursiveSavedResponse,
  ErrorNotebookData,
  FolderBrowserData,
  LocalBridgeStatus,
  MaterialAnalysisResult,
  MultiFolderWorkspaceRecord,
  QuestionBattery,
  SpacedReviewOverviewData,
  StorageConnectionRecord,
  StoredPdfFileRecord,
  StudentErrorSummaryRecord,
  SubtopicRecurrence,
  TutorDiagnosisData,
  WordAnnotation,
} from './types';

const LOCAL_API_STORAGE_KEY = 'cebraspelab_local_api_url';
const DEFAULT_LOCAL_PC_SERVER = 'http://127.0.0.1:8000';

/**
 * Resolve dinamicamente o endpoint do Backend Local no PC do usuário:
 * 1. Se o usuário estiver rodando direto em `127.0.0.1:8000` ou `localhost:5173` (sem override),
 *    usa `/api` relativo (ou o servidor configurado).
 * 2. Se o usuário estiver acessando a interface hospedada no GitHub Pages (domínio de alto nível,
 *    ex: `https://app.cebraspelab.com.br` ou `https://*.github.io`), aponta automaticamente para
 *    o Banco Local no computador do usuário (`http://127.0.0.1:8000/api` ou porta customizada).
 */
export function getLocalServerOrigin(): string {
  if (typeof window === 'undefined') return DEFAULT_LOCAL_PC_SERVER;
  try {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get('local_api');
    if (fromQuery && fromQuery.startsWith('http')) {
      const cleaned = fromQuery.replace(/\/api\/?$/, '').replace(/\/$/, '');
      window.localStorage.setItem(LOCAL_API_STORAGE_KEY, cleaned);
      return cleaned;
    }
    const saved = window.localStorage.getItem(LOCAL_API_STORAGE_KEY);
    if (saved && saved.startsWith('http')) {
      return saved.replace(/\/api\/?$/, '').replace(/\/$/, '');
    }
  } catch {
    // ignore storage errors
  }
  return DEFAULT_LOCAL_PC_SERVER;
}

export function setLocalServerOrigin(serverUrl: string): string {
  const cleaned = (serverUrl || DEFAULT_LOCAL_PC_SERVER)
    .trim()
    .replace(/\/api\/?$/, '')
    .replace(/\/$/, '');
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(LOCAL_API_STORAGE_KEY, cleaned);
  }
  return cleaned;
}

export function isRunningOnRemotePagesUI(): boolean {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname;
  return host !== '127.0.0.1' && host !== 'localhost' && host !== '0.0.0.0';
}

export function getApiBase(): string {
  if (!isRunningOnRemotePagesUI()) {
    const saved =
      typeof window !== 'undefined' ? window.localStorage.getItem(LOCAL_API_STORAGE_KEY) : null;
    if (saved && saved.startsWith('http')) {
      return `${saved.replace(/\/$/, '')}/api`;
    }
    return '/api';
  }
  return `${getLocalServerOrigin()}/api`;
}

const API_BASE = {
  toString() {
    return getApiBase();
  },
};

export async function fetchSettings(): Promise<AppSettings> {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error('Falha ao carregar configurações');
  return res.json();
}

export async function updateSettings(data: Partial<AppSettings>): Promise<AppSettings> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Falha ao salvar configurações');
  return res.json();
}

export async function testGeminiConnection(
  gemini_api_key: string,
  gemini_model: string
): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/settings/test-gemini`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gemini_api_key, gemini_model }),
  });
  return res.json();
}

export async function analyzeMaterials(
  studyPdfs: File[],
  questionFiles: File[],
  area: string,
  subjectHint: string
): Promise<MaterialAnalysisResult> {
  const formData = new FormData();
  studyPdfs.forEach((f) => formData.append('study_pdfs', f));
  questionFiles.forEach((f) => formData.append('question_files', f));
  formData.append('area', area);
  formData.append('subject_hint', subjectHint);

  const res = await fetch(`${API_BASE}/materials/analyze`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao analisar PDF' }));
    throw new Error(err.detail || 'Erro ao analisar PDF');
  }
  return res.json();
}

export async function generateBattery(payload: {
  material_id: number;
  title: string;
  subject: string;
  area: string;
  depth: string;
  subtopic_plan: SubtopicRecurrence[];
}): Promise<QuestionBattery> {
  const res = await fetch(`${API_BASE}/batteries/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao gerar assertivas' }));
    throw new Error(err.detail || 'Erro ao gerar assertivas');
  }
  return res.json();
}

export async function extractPeriodAssertions(
  materialId: number,
  payload: {
    variations_per_period: number;
    title?: string;
    subject?: string;
    area?: string;
  }
): Promise<QuestionBattery> {
  const res = await fetch(`${API_BASE}/materials/${materialId}/extract-period-assertions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao extrair assertivas dos períodos' }));
    throw new Error(err.detail || 'Erro ao extrair assertivas dos períodos');
  }
  return res.json();
}

export async function generateDemoBattery(): Promise<QuestionBattery> {
  const res = await fetch(`${API_BASE}/batteries/generate-demo`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Erro ao criar bateria demonstrativa');
  return res.json();
}

export async function fetchBatteries(): Promise<QuestionBattery[]> {
  const res = await fetch(`${API_BASE}/batteries`);
  if (!res.ok) throw new Error('Erro ao listar baterias');
  return res.json();
}

export async function fetchBattery(id: number): Promise<QuestionBattery> {
  const res = await fetch(`${API_BASE}/batteries/${id}`);
  if (!res.ok) throw new Error('Erro ao carregar bateria');
  return res.json();
}

export async function submitAssertionAnswer(
  assertionId: number,
  payload: {
    user_answer?: 'C' | 'E' | 'BLANK' | 'RESET';
    is_favorite?: boolean;
    answered_with_doubt?: boolean;
    annotations?: WordAnnotation[];
  }
): Promise<AssertionItem> {
  const res = await fetch(`${API_BASE}/assertions/${assertionId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Erro ao registrar resposta');
  return res.json();
}

export async function fetchErrorNotebook(
  subject?: string,
  onlyFavorites: boolean = false
): Promise<ErrorNotebookData> {
  const params = new URLSearchParams();
  if (subject) params.set('subject', subject);
  if (onlyFavorites) params.set('only_favorites', 'true');
  const res = await fetch(`${API_BASE}/errors?${params.toString()}`);
  if (!res.ok) throw new Error('Erro ao carregar Caderno de Erros');
  return res.json();
}

export async function generateErrorReinforcement(payload: {
  assertion_ids?: number[];
  subject?: string;
  questions_per_error?: number;
}): Promise<QuestionBattery> {
  const res = await fetch(`${API_BASE}/errors/reinforce`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao gerar reforço' }));
    throw new Error(err.detail || 'Erro ao gerar reforço');
  }
  return res.json();
}

export async function fetchTutorDiagnosis(materialId?: number): Promise<TutorDiagnosisData> {
  const params = new URLSearchParams();
  if (materialId) params.set('material_id', String(materialId));
  const res = await fetch(`${API_BASE}/tutor/diagnosis?${params.toString()}`);
  if (!res.ok) throw new Error('Erro ao carregar diagnóstico e resumo do PDF');
  return res.json();
}

export async function generateFixationFromStoredPdf(payload: {
  material_id: number;
  target_subtopic?: string;
  variations_per_period?: number;
}): Promise<QuestionBattery> {
  const res = await fetch(`${API_BASE}/tutor/generate-fixation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Erro ao gerar bateria de fixação do PDF armazenado');
  return res.json();
}

export async function submitDiscursive5LinesAnswer(payload: {
  question_id: number;
  student_text: string;
}): Promise<DiscursiveSavedResponse> {
  const res = await fetch(`${API_BASE}/tutor/discursive/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao salvar resposta discursiva' }));
    throw new Error(err.detail || 'Erro ao salvar resposta discursiva');
  }
  return res.json();
}

export async function fetchDiscursiveHistory(
  materialId?: number
): Promise<DiscursiveSavedResponse[]> {
  const params = new URLSearchParams();
  if (materialId) params.set('material_id', String(materialId));
  const res = await fetch(`${API_BASE}/tutor/discursive/history?${params.toString()}`);
  if (!res.ok) throw new Error('Erro ao listar histórico de discursivas');
  return res.json();
}

export async function fetchStoredPdfFiles(
  materialId?: number
): Promise<StoredPdfFileRecord[]> {
  const params = new URLSearchParams();
  if (materialId) params.set('material_id', String(materialId));
  const res = await fetch(`${API_BASE}/storage/files?${params.toString()}`);
  if (!res.ok) throw new Error('Erro ao listar PDFs armazenados');
  return res.json();
}

export function getStoredFileDownloadUrl(fileId: number): string {
  return `${API_BASE}/storage/files/${fileId}/download`;
}

export function getExportUrl(
  batteryId: number,
  format: 'apkg' | 'csv' | 'pdf' | 'md',
  filterMode: 'all' | 'errors_or_favorites' | 'errors_only' | 'favorites_only' = 'all'
): string {
  return `${API_BASE}/batteries/${batteryId}/export/${format}?filter_mode=${filterMode}`;
}

export async function fetchSpacedReviewConceptsHierarchy(
  materialId?: number
): Promise<ConceptsHierarchyData> {
  const params = new URLSearchParams();
  if (materialId) params.set('material_id', String(materialId));
  const res = await fetch(`${API_BASE}/spaced-review/concepts-hierarchy?${params.toString()}`);
  if (!res.ok) throw new Error('Erro ao carregar conceitos e hierarquia');
  return res.json();
}

export async function createSpacedReviewErrorSummary(payload: {
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
  review_interval_days?: number;
}): Promise<StudentErrorSummaryRecord> {
  const res = await fetch(`${API_BASE}/spaced-review/summaries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao salvar resumo de erro' }));
    throw new Error(err.detail || 'Erro ao salvar resumo de erro');
  }
  return res.json();
}

export async function fetchSpacedReviewOverview(
  materialId?: number,
  onlyDue: boolean = false
): Promise<SpacedReviewOverviewData> {
  const params = new URLSearchParams();
  if (materialId) params.set('material_id', String(materialId));
  if (onlyDue) params.set('only_due', 'true');
  const res = await fetch(`${API_BASE}/spaced-review/overview?${params.toString()}`);
  if (!res.ok) throw new Error('Erro ao carregar overview de revisões');
  return res.json();
}

export async function triggerSpacedReview3Days(payload: {
  summary_ids?: number[];
  relationship_link_id?: number;
  questions_count?: number;
  force_all_if_none_due?: boolean;
}): Promise<{
  cycle_id: number;
  reviewed_summaries_count: number;
  questions_generated_count: number;
  next_review_scheduled_at: string;
  battery: QuestionBattery;
}> {
  const res = await fetch(`${API_BASE}/spaced-review/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao disparar revisão de 3 em 3 dias' }));
    throw new Error(err.detail || 'Erro ao disparar revisão de 3 em 3 dias');
  }
  return res.json();
}

export async function evaluateAdaptiveSpacedReview(payload: {
  cycle_id?: number;
  battery_id?: number;
}): Promise<AdaptiveEvaluationResult> {
  const res = await fetch(`${API_BASE}/spaced-review/evaluate-adaptive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao avaliar progressão adaptativa de intervalo' }));
    throw new Error(err.detail || 'Erro ao avaliar progressão adaptativa de intervalo');
  }
  return res.json();
}

export async function queueDoubtAssertionTo3DayReview(payload: {
  assertion_id: number;
  student_doubt_note?: string;
}): Promise<StudentErrorSummaryRecord> {
  const res = await fetch(`${API_BASE}/spaced-review/queue-doubt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao enfileirar dúvida na revisão de 3 dias' }));
    throw new Error(err.detail || 'Erro ao enfileirar dúvida na revisão de 3 dias');
  }
  return res.json();
}

export async function fetchContrastivePairs(): Promise<{ pairs: ContrastiveConceptPair[] }> {
  const res = await fetch(`${API_BASE}/spaced-review/contrastive-pairs`);
  if (!res.ok) throw new Error('Erro ao carregar pares contrastivos');
  const data = await res.json();
  return { pairs: Array.isArray(data) ? data : data.pairs || [] };
}

export async function generateContrastiveBattleBattery(payload: {
  pair_id?: string;
  questions_count?: number;
}): Promise<{
  pair: ContrastiveConceptPair;
  questions_generated_count: number;
  battery: QuestionBattery;
}> {
  const res = await fetch(`${API_BASE}/spaced-review/contrastive-battle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao gerar bateria contrastiva' }));
    throw new Error(err.detail || 'Erro ao gerar bateria contrastiva');
  }
  return res.json();
}

export async function fetchConnectorProviders(): Promise<ConnectorProvidersInfo> {
  const res = await fetch(`${API_BASE}/connectors/providers`);
  if (!res.ok) throw new Error('Erro ao carregar provedores de conexão');
  return res.json();
}

export async function fetchStorageConnections(): Promise<StorageConnectionRecord[]> {
  const res = await fetch(`${API_BASE}/connectors`);
  if (!res.ok) throw new Error('Erro ao listar conexões cadastradas');
  return res.json();
}

export async function saveStorageConnection(payload: {
  connection_id?: number;
  name: string;
  provider_type: string;
  target_path_or_folder_id: string;
  subject_hint: string;
  area_hint: string;
  api_key?: string;
  access_token?: string;
  app_key?: string;
  app_secret?: string;
  endpoint_url?: string;
  local_sync_mirror_path?: string;
  recursive_scan?: boolean;
  auto_generate_questions?: boolean;
}): Promise<StorageConnectionRecord> {
  const res = await fetch(`${API_BASE}/connectors`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao salvar conexão' }));
    throw new Error(err.detail || 'Erro ao salvar conexão');
  }
  return res.json();
}

export async function deleteStorageConnection(connectionId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/connectors/${connectionId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Erro ao remover conexão');
}

export async function scanStorageConnection(
  connectionId: number,
  payload: {
    auto_ingest_and_generate?: boolean;
    questions_per_file?: number;
    max_files_to_ingest?: number;
  } = {}
): Promise<{
  connection_id: number;
  provider_type: string;
  synced_at: string;
  total_discovered_files: number;
  newly_ingested_files_count: number;
  generated_batteries: QuestionBattery[];
  discovered_files: DiscoveredStudyFileRecord[];
}> {
  const res = await fetch(`${API_BASE}/connectors/${connectionId}/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao escanear e sincronizar conexão' }));
    throw new Error(err.detail || 'Erro ao escanear e sincronizar conexão');
  }
  return res.json();
}

export async function fetchDiscoveredFiles(
  connectionId?: number
): Promise<DiscoveredStudyFileRecord[]> {
  const params = new URLSearchParams();
  if (connectionId) params.set('connection_id', String(connectionId));
  const res = await fetch(`${API_BASE}/connectors/files?${params.toString()}`);
  if (!res.ok) throw new Error('Erro ao listar arquivos descobertos');
  return res.json();
}

export async function ingestDiscoveredFile(
  discoveredFileId: number,
  questionsCount: number = 10
): Promise<{
  discovered_file: DiscoveredStudyFileRecord;
  material_id: number;
  battery_id: number;
  battery: QuestionBattery;
}> {
  const res = await fetch(`${API_BASE}/connectors/files/${discoveredFileId}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ questions_count: questionsCount }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao importar arquivo e gerar questões' }));
    throw new Error(err.detail || 'Erro ao importar arquivo e gerar questões');
  }
  return res.json();
}

export async function browseLocalFolders(path?: string): Promise<FolderBrowserData> {
  const params = new URLSearchParams();
  if (path) params.set('path', path);
  const res = await fetch(`${API_BASE}/multi-folders/browse?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao navegar na pasta' }));
    throw new Error(err.detail || 'Erro ao navegar na pasta');
  }
  return res.json();
}

export async function pickFolderNativeDialog(initialDir?: string): Promise<{
  selected: boolean;
  path: string;
  error?: string;
}> {
  const params = new URLSearchParams();
  if (initialDir) params.set('initial_dir', initialDir);
  const res = await fetch(`${API_BASE}/multi-folders/pick-native?${params.toString()}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Erro ao abrir seletor nativo de pastas');
  return res.json();
}

export async function fetchMultiFolderWorkspaces(): Promise<MultiFolderWorkspaceRecord[]> {
  const res = await fetch(`${API_BASE}/multi-folders/workspaces`);
  if (!res.ok) throw new Error('Erro ao listar conjuntos de múltiplas pastas');
  return res.json();
}

export async function deleteMultiFolderWorkspace(workspaceId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/multi-folders/workspaces/${workspaceId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Erro ao excluir conjunto de pastas');
}

export async function scanAndSyncMultipleFolders(payload: {
  workspace_id?: number;
  folders?: Array<string | { path: string; label?: string; subject?: string }>;
  workspace_name?: string;
  subject_hint?: string;
  area_hint?: string;
  questions_per_file?: number;
  create_unified_battery?: boolean;
}): Promise<{
  workspace: MultiFolderWorkspaceRecord;
  folders_scanned_count: number;
  total_unique_files: number;
  duplicates_skipped_count: number;
  discovered_files: DiscoveredStudyFileRecord[];
  unified_battery_id?: number | null;
  unified_battery?: QuestionBattery | null;
  individual_batteries: QuestionBattery[];
}> {
  const res = await fetch(`${API_BASE}/multi-folders/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao escanear múltiplas pastas' }));
    throw new Error(err.detail || 'Erro ao escanear múltiplas pastas');
  }
  return res.json();
}

export async function fetchBridgeStatus(): Promise<LocalBridgeStatus> {
  const res = await fetch(`${API_BASE}/bridge/status`);
  if (!res.ok) throw new Error('Agente Local (127.0.0.1:8000) não detectado no seu computador');
  return res.json();
}

export async function activateProductLicense(payload: {
  license_key: string;
  buyer_email?: string;
  custom_pages_url?: string;
}): Promise<LocalBridgeStatus['license']> {
  const res = await fetch(`${API_BASE}/bridge/activate-license`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erro ao ativar licença' }));
    throw new Error(err.detail || 'Erro ao ativar licença');
  }
  return res.json();
}

export async function ingestBrowserSelectedFolder(
  files: File[],
  folderLabel: string,
  subjectHint: string,
  areaHint: string,
  questionsPerFile: number = 6
): Promise<{
  folder_label: string;
  processed_files_count: number;
  duplicates_skipped_count: number;
  battery_id: number;
  battery: QuestionBattery;
}> {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  formData.append('folder_label', folderLabel);
  formData.append('subject_hint', subjectHint);
  formData.append('area_hint', areaHint);
  formData.append('questions_per_file', String(questionsPerFile));

  const res = await fetch(`${API_BASE}/bridge/ingest-browser-folder`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res
      .json()
      .catch(() => ({ detail: 'Erro ao sincronizar pasta selecionada no navegador com o banco local' }));
    throw new Error(err.detail || 'Erro ao sincronizar pasta selecionada no navegador com o banco local');
  }
  return res.json();
}



