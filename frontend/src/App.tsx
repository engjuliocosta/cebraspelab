import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Award,
  Bell,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Cloud,
  Database,
  Download,
  FileSpreadsheet,
  FileText,
  Flame,
  FolderSearch,
  GitBranch,
  HardDrive,
  Highlighter,
  KeyRound,
  Layers,
  Loader2,
  MinusCircle,
  NotebookPen,
  PenTool,
  Play,
  RefreshCw,
  Send,
  Settings,
  ShieldAlert,
  Sparkles,
  Star,
  Strikethrough,
  Target,
  Trash2,
  TrendingUp,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  activateProductLicense,
  analyzeMaterials,
  browseLocalFolders,
  createSpacedReviewErrorSummary,
  deleteMultiFolderWorkspace,
  deleteStorageConnection,
  evaluateAdaptiveSpacedReview,
  extractPeriodAssertions,
  fetchBatteries,
  fetchBattery,
  fetchBridgeStatus,
  fetchConnectorProviders,
  fetchContrastivePairs,
  fetchDiscoveredFiles,
  fetchDiscursiveHistory,
  fetchErrorNotebook,
  fetchMultiFolderWorkspaces,
  fetchSettings,
  fetchSpacedReviewConceptsHierarchy,
  fetchSpacedReviewOverview,
  fetchStorageConnections,
  fetchStoredPdfFiles,
  fetchTutorDiagnosis,
  generateBattery,
  generateContrastiveBattleBattery,
  generateDemoBattery,
  generateErrorReinforcement,
  generateFixationFromStoredPdf,
  getExportUrl,
  getLocalServerOrigin,
  getStoredFileDownloadUrl,
  ingestBrowserSelectedFolder,
  ingestDiscoveredFile,
  isRunningOnRemotePagesUI,
  pickFolderNativeDialog,
  queueDoubtAssertionTo3DayReview,
  saveStorageConnection,
  scanAndSyncMultipleFolders,
  scanStorageConnection,
  setLocalServerOrigin,
  submitAssertionAnswer,
  submitDiscursive5LinesAnswer,
  testGeminiConnection,
  triggerSpacedReview3Days,
  updateSettings,
} from './api';
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
  PresentedConceptItem,
  QuestionBattery,
  SpacedReviewOverviewData,
  StorageConnectionRecord,
  StoredPdfFileRecord,
  SubtopicRecurrence,
  TutorDiagnosisData,
  WordAnnotation,
} from './types';

type ActiveTab = 'generator' | 'solver' | 'tutor' | 'spaced' | 'connectors' | 'errors' | 'history';
type SolverMode = 'training' | 'simulado';
type AnnotationTool = 'none' | 'strike' | 'highlight';

const AREAS = [
  'Geral',
  'Tribunais / Jurídico',
  'Policial',
  'Controle / Fiscal',
  'TI (Tecnologia da Informação)',
  'Administrativo',
];

const DEPTHS = [
  'Literalidade + Conceitos',
  'Misto Padrão Cebraspe',
  'Avançado / Jurisprudência e Casos Práticos',
];

const MODELS = [
  { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash (Recomendado — Rápido & Preciso)' },
  { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro (Máxima Profundidade & Casos Complexos)' },
  { id: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash (Econômico)' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('generator');
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [showSettingsModal, setShowSettingsModal] = useState(false);

  // Settings form state
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [modelInput, setModelInput] = useState('gemini-2.5-flash');
  const [testingApi, setTestingApi] = useState(false);
  const [apiTestStatus, setApiTestStatus] = useState<{ ok?: boolean; message?: string } | null>(null);

  // Generator state
  const [studyFiles, setStudyFiles] = useState<File[]>([]);
  const [questionFiles, setQuestionFiles] = useState<File[]>([]);
  const [selectedArea, setSelectedArea] = useState('Tribunais / Jurídico');
  const [selectedDepth, setSelectedDepth] = useState('Misto Padrão Cebraspe');
  const [subjectHint, setSubjectHint] = useState('');
  const [analyzingPdf, setAnalyzingPdf] = useState(false);
  const [generatingBattery, setGeneratingBattery] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<MaterialAnalysisResult | null>(null);
  const [editableSubtopics, setEditableSubtopics] = useState<SubtopicRecurrence[]>([]);
  const [customTitle, setCustomTitle] = useState('');
  const [customSubject, setCustomSubject] = useState('');
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  // Solver state
  const [currentBattery, setCurrentBattery] = useState<QuestionBattery | null>(null);
  const [solverMode, setSolverMode] = useState<SolverMode>('training');
  const [simuladoFinished, setSimuladoFinished] = useState(false);
  const [annotationTool, setAnnotationTool] = useState<AnnotationTool>('none');
  const [exportFilter, setExportFilter] = useState<'all' | 'errors_or_favorites'>('all');
  const [subtopicFilter, setSubtopicFilter] = useState<string>('ALL');

  // Tutor / Summary / 5-Line Discursive state
  const [tutorData, setTutorData] = useState<TutorDiagnosisData | null>(null);
  const [loadingTutor, setLoadingTutor] = useState(false);
  const [discursiveText, setDiscursiveText] = useState('');
  const [submittingDiscursive, setSubmittingDiscursive] = useState(false);
  const [lastDiscursiveResult, setLastDiscursiveResult] = useState<DiscursiveSavedResponse | null>(null);
  const [discursiveHistory, setDiscursiveHistory] = useState<DiscursiveSavedResponse[]>([]);
  const [generatingFixation, setGeneratingFixation] = useState(false);

  // 3-Day Spaced Review & Student Error Summaries state
  const [conceptsHierarchy, setConceptsHierarchy] = useState<ConceptsHierarchyData | null>(null);
  const [spacedOverview, setSpacedOverview] = useState<SpacedReviewOverviewData | null>(null);
  const [srAssertionId, setSrAssertionId] = useState<number | undefined>(undefined);
  const [srMaterialId, setSrMaterialId] = useState<number | undefined>(undefined);
  const [srSubject, setSrSubject] = useState('Direito Administrativo');
  const [srTopic, setSrTopic] = useState('');
  const [srSubtopic, setSrSubtopic] = useState('');
  const [srConcept, setSrConcept] = useState('');
  const [srSubconcept, setSrSubconcept] = useState('');
  const [srPresentedContext, setSrPresentedContext] = useState('');
  const [srStudentSummary, setSrStudentSummary] = useState('');
  const [srPersonalNotes, setSrPersonalNotes] = useState('');
  const [srTrapType, setSrTrapType] = useState('Inversão de Conceito');
  const [srPdfPage, setSrPdfPage] = useState('p. 1');
  const [savingSummaryNote, setSavingSummaryNote] = useState(false);
  const [triggering3DayReview, setTriggering3DayReview] = useState(false);
  const [contrastivePairs, setContrastivePairs] = useState<ContrastiveConceptPair[]>([]);
  const [generatingContrastivePairId, setGeneratingContrastivePairId] = useState<string | null>(null);
  const [evaluatingAdaptive, setEvaluatingAdaptive] = useState(false);
  const [lastAdaptiveResult, setLastAdaptiveResult] = useState<AdaptiveEvaluationResult | null>(null);
  const [queuingDoubtAssertionId, setQueuingDoubtAssertionId] = useState<number | null>(null);

  // Data Connectors (Local FS, Network Shares, Google Drive, Dropbox) state
  const [providersInfo, setProvidersInfo] = useState<ConnectorProvidersInfo | null>(null);
  const [connectionsList, setConnectionsList] = useState<StorageConnectionRecord[]>([]);
  const [discoveredFilesList, setDiscoveredFilesList] = useState<DiscoveredStudyFileRecord[]>([]);
  const [connName, setConnName] = useState('');
  const [connProviderType, setConnProviderType] = useState('local_fs');
  const [connTargetPath, setConnTargetPath] = useState('');
  const [connSubjectHint, setConnSubjectHint] = useState('Direito Administrativo');
  const [connAreaHint, setConnAreaHint] = useState('Tribunais / Jurídico');
  const [connApiKey, setConnApiKey] = useState('');
  const [connAccessToken, setConnAccessToken] = useState('');
  const [connAppKey, setConnAppKey] = useState('');
  const [connAppSecret, setConnAppSecret] = useState('');
  const [connEndpointUrl, setConnEndpointUrl] = useState('');
  const [connMirrorPath, setConnMirrorPath] = useState('');
  const [connAutoGenerate, setConnAutoGenerate] = useState(true);
  const [savingConnection, setSavingConnection] = useState(false);
  const [scanningConnId, setScanningConnId] = useState<number | null>(null);
  const [ingestingFileId, setIngestingFileId] = useState<number | null>(null);

  // Multi-Folder Picker & Workspace state
  const [multiWorkspacesList, setMultiWorkspacesList] = useState<MultiFolderWorkspaceRecord[]>([]);
  const [selectedMultiFolders, setSelectedMultiFolders] = useState<string[]>([]);
  const [multiWorkspaceName, setMultiWorkspaceName] = useState('Meu Conjunto de Pastas de Estudo');
  const [multiSubjectHint, setMultiSubjectHint] = useState('Multidisciplinar');
  const [folderBrowser, setFolderBrowser] = useState<FolderBrowserData | null>(null);
  const [showFolderBrowser, setShowFolderBrowser] = useState(false);
  const [scanningMultiFolders, setScanningMultiFolders] = useState(false);
  const [syncingBrowserFolder, setSyncingBrowserFolder] = useState(false);

  // Hybrid GitHub Pages <-> Local PC Bridge & Hotmart License state
  const [bridgeStatus, setBridgeStatus] = useState<LocalBridgeStatus | null>(null);
  const [bridgeOffline, setBridgeOffline] = useState(false);
  const [showBridgeModal, setShowBridgeModal] = useState(false);
  const [localServerInput, setLocalServerInput] = useState(getLocalServerOrigin());
  const [licenseKeyInput, setLicenseKeyInput] = useState('');
  const [buyerEmailInput, setBuyerEmailInput] = useState('');
  const [activatingLicense, setActivatingLicense] = useState(false);

  // Errors & History state
  const [errorNotebook, setErrorNotebook] = useState<ErrorNotebookData | null>(null);
  const [onlyFavoritesFilter, setOnlyFavoritesFilter] = useState(false);
  const [reinforcingErrors, setReinforcingErrors] = useState(false);
  const [batteriesList, setBatteriesList] = useState<QuestionBattery[]>([]);
  const [storedPdfsList, setStoredPdfsList] = useState<StoredPdfFileRecord[]>([]);

  useEffect(() => {
    loadInitialData();
  }, []);

  async function loadInitialData() {
    try {
      const [s, bats, files, spOverview, bStatus] = await Promise.all([
        fetchSettings(),
        fetchBatteries(),
        fetchStoredPdfFiles(),
        fetchSpacedReviewOverview(),
        fetchBridgeStatus().catch(() => null),
      ]);
      setBridgeStatus(bStatus);
      setBridgeOffline(!bStatus);
      setSettings(s);
      setApiKeyInput(s.gemini_api_key || '');
      setModelInput(s.gemini_model || 'gemini-2.5-flash');
      if (s.default_area) setSelectedArea(s.default_area);
      if (s.default_depth) setSelectedDepth(s.default_depth);
      setBatteriesList(bats);
      setStoredPdfsList(files);
      setSpacedOverview(spOverview);
      if (bats.length > 0 && !currentBattery) {
        const full = await fetchBattery(bats[0].id);
        setCurrentBattery(full);
      }
    } catch (err) {
      console.error(err);
      setBridgeOffline(true);
    }
  }

  async function handleSaveLocalBridgeServer(e: React.FormEvent) {
    e.preventDefault();
    const cleaned = setLocalServerOrigin(localServerInput);
    setLocalServerInput(cleaned);
    await loadInitialData();
  }

  async function handleActivateLicense(e: React.FormEvent) {
    e.preventDefault();
    if (!licenseKeyInput.trim()) return;
    setActivatingLicense(true);
    setErrorBanner(null);
    try {
      await activateProductLicense({
        license_key: licenseKeyInput,
        buyer_email: buyerEmailInput,
      });
      const updatedBridge = await fetchBridgeStatus();
      setBridgeStatus(updatedBridge);
      setLicenseKeyInput('');
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao ativar código de licença.');
    } finally {
      setActivatingLicense(false);
    }
  }

  async function handleBrowserDirectoryUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;
    const filesArray = Array.from(fileList);
    const firstRelPath = (filesArray[0] as any).webkitRelativePath || '';
    const folderLabel = firstRelPath ? firstRelPath.split('/')[0] : 'Pasta Selecionada no Navegador';

    setSyncingBrowserFolder(true);
    setErrorBanner(null);
    try {
      const res = await ingestBrowserSelectedFolder(
        filesArray,
        folderLabel,
        multiSubjectHint || 'Multidisciplinar',
        connAreaHint,
        6
      );
      await loadConnectorsData();
      await refreshBatteriesAndErrors();
      if (res.battery) {
        setCurrentBattery(res.battery);
        setSimuladoFinished(false);
        setSubtopicFilter('ALL');
        setActiveTab('solver');
      }
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao sincronizar pasta pelo navegador.');
    } finally {
      setSyncingBrowserFolder(false);
      e.target.value = '';
    }
  }

  async function refreshBatteriesAndErrors() {
    try {
      const [bats, errs, files, spOverview] = await Promise.all([
        fetchBatteries(),
        fetchErrorNotebook(undefined, onlyFavoritesFilter),
        fetchStoredPdfFiles(),
        fetchSpacedReviewOverview(),
      ]);
      setBatteriesList(bats);
      setErrorNotebook(errs);
      setStoredPdfsList(files);
      setSpacedOverview(spOverview);
    } catch (e) {
      console.error(e);
    }
  }

  async function loadTutorAndDiscursive(materialId?: number) {
    setLoadingTutor(true);
    try {
      const [diag, hist] = await Promise.all([
        fetchTutorDiagnosis(materialId || currentBattery?.material_id),
        fetchDiscursiveHistory(materialId || currentBattery?.material_id),
      ]);
      setTutorData(diag);
      setDiscursiveHistory(hist);
    } catch (e: any) {
      setErrorBanner(e.message || 'Erro ao carregar mentoria do PDF armazenado.');
    } finally {
      setLoadingTutor(false);
    }
  }

  async function loadSpacedReviewData(materialId?: number) {
    try {
      const [ch, ov, cp] = await Promise.all([
        fetchSpacedReviewConceptsHierarchy(materialId),
        fetchSpacedReviewOverview(materialId),
        fetchContrastivePairs(),
      ]);
      setConceptsHierarchy(ch);
      setSpacedOverview(ov);
      setContrastivePairs(cp.pairs || []);

      // Se o formulário ainda estiver em branco e houver conceitos errados, pré-preencher o primeiro
      if (!srTopic && ch.presented_concepts_from_errors.length > 0) {
        prefillFromPresentedConcept(ch.presented_concepts_from_errors[0]);
      } else if (!srTopic && ch.available_topics_and_subtopics.length > 0) {
        const firstOpt = ch.available_topics_and_subtopics[0];
        setSrMaterialId(firstOpt.material_id);
        setSrSubject(firstOpt.subject);
        setSrTopic(firstOpt.topic);
        setSrSubtopic(firstOpt.subtopic);
      }
    } catch (e: any) {
      console.error(e);
    }
  }

  function prefillFromPresentedConcept(pc: PresentedConceptItem) {
    setSrAssertionId(pc.assertion_id);
    setSrMaterialId(pc.material_id);
    setSrSubject(pc.subject || 'Direito Administrativo');
    setSrTopic(pc.suggested_topic || 'Tópico Principal');
    setSrSubtopic(pc.suggested_subtopic || 'Subtópico');
    setSrConcept(pc.suggested_concept || pc.suggested_subtopic);
    setSrSubconcept(pc.suggested_subconcept || pc.trap_type || 'Aplicação');
    setSrPresentedContext(pc.presented_concept_context || pc.explanation);
    setSrTrapType(pc.trap_type || 'Conceito');
    setSrPdfPage(pc.pdf_page || 'p. 1');
  }

  function openErrorSummaryNoteFromAssertion(assertion: AssertionItem) {
    setSrAssertionId(assertion.id);
    setSrMaterialId(assertion.material_id || currentBattery?.material_id);
    setSrSubject(currentBattery?.subject || assertion.subject || 'Disciplina');
    setSrTopic(currentBattery?.title || 'Tópico do Material');
    setSrSubtopic(assertion.subtopic);
    setSrConcept(`${assertion.subtopic} — ${assertion.trap_type || 'Regra Geral'}`);
    setSrSubconcept(assertion.trap_type || 'Distinção Técnica');
    setSrPresentedContext(assertion.pdf_quote || assertion.explanation);
    setSrTrapType(assertion.trap_type || 'Conceito');
    setSrPdfPage(assertion.pdf_page || 'p. 1');
    setActiveTab('spaced');
  }

  useEffect(() => {
    if (activeTab === 'errors') {
      fetchErrorNotebook(undefined, onlyFavoritesFilter).then(setErrorNotebook).catch(console.error);
    } else if (activeTab === 'history') {
      Promise.all([fetchBatteries(), fetchStoredPdfFiles()])
        .then(([bats, files]) => {
          setBatteriesList(bats);
          setStoredPdfsList(files);
        })
        .catch(console.error);
    } else if (activeTab === 'tutor') {
      loadTutorAndDiscursive(currentBattery?.material_id);
    } else if (activeTab === 'spaced') {
      loadSpacedReviewData();
    } else if (activeTab === 'connectors') {
      loadConnectorsData();
    }
  }, [activeTab, onlyFavoritesFilter]);

  async function loadConnectorsData() {
    try {
      const [prov, conns, dFiles, multiWs] = await Promise.all([
        fetchConnectorProviders(),
        fetchStorageConnections(),
        fetchDiscoveredFiles(),
        fetchMultiFolderWorkspaces(),
      ]);
      setProvidersInfo(prov);
      setConnectionsList(conns);
      setDiscoveredFilesList(dFiles);
      setMultiWorkspacesList(multiWs);
      if (!connTargetPath && prov.default_local_directories.length > 0) {
        setConnTargetPath(prov.default_local_directories[0].path);
        setConnName(prov.default_local_directories[0].label);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function handleBrowseFolder(targetPath?: string) {
    try {
      const data = await browseLocalFolders(targetPath);
      setFolderBrowser(data);
      setShowFolderBrowser(true);
    } catch (err: any) {
      setErrorBanner(err.message || 'Não foi possível abrir esta pasta.');
    }
  }

  async function handlePickNativeFolder() {
    try {
      const res = await pickFolderNativeDialog(folderBrowser?.current_path);
      if (res.selected && res.path) {
        setSelectedMultiFolders((prev) => (prev.includes(res.path) ? prev : [...prev, res.path]));
      }
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao abrir seletor de pastas do sistema.');
    }
  }

  function addPathToMultiSelection(folderPath: string) {
    const clean = folderPath.trim();
    if (!clean) return;
    setSelectedMultiFolders((prev) => (prev.includes(clean) ? prev : [...prev, clean]));
  }

  function removePathFromMultiSelection(folderPath: string) {
    setSelectedMultiFolders((prev) => prev.filter((p) => p !== folderPath));
  }

  async function handleScanSelectedMultiFolders(e: React.FormEvent) {
    e.preventDefault();
    if (selectedMultiFolders.length === 0) {
      setErrorBanner('Escolha pelo menos 1 pasta (ou várias pastas) antes de escanear.');
      return;
    }
    setScanningMultiFolders(true);
    setErrorBanner(null);
    try {
      const res = await scanAndSyncMultipleFolders({
        workspace_name: multiWorkspaceName || 'Minhas Pastas de Estudo',
        folders: selectedMultiFolders,
        subject_hint: multiSubjectHint || 'Multidisciplinar',
        area_hint: connAreaHint,
        questions_per_file: 6,
        create_unified_battery: true,
      });
      await loadConnectorsData();
      await refreshBatteriesAndErrors();
      if (res.unified_battery) {
        setCurrentBattery(res.unified_battery);
        setSimuladoFinished(false);
        setSubtopicFilter('ALL');
        setActiveTab('solver');
      }
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao escanear múltiplas pastas.');
    } finally {
      setScanningMultiFolders(false);
    }
  }

  async function handleResyncMultiWorkspace(workspaceId: number) {
    setScanningMultiFolders(true);
    setErrorBanner(null);
    try {
      const res = await scanAndSyncMultipleFolders({
        workspace_id: workspaceId,
        questions_per_file: 6,
        create_unified_battery: true,
      });
      await loadConnectorsData();
      await refreshBatteriesAndErrors();
      if (res.unified_battery) {
        setCurrentBattery(res.unified_battery);
        setSimuladoFinished(false);
        setSubtopicFilter('ALL');
        setActiveTab('solver');
      }
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao sincronizar conjunto de pastas.');
    } finally {
      setScanningMultiFolders(false);
    }
  }

  async function handleDeleteMultiWorkspace(workspaceId: number) {
    try {
      await deleteMultiFolderWorkspace(workspaceId);
      await loadConnectorsData();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao excluir conjunto de pastas.');
    }
  }

  async function handleSaveConnection(e: React.FormEvent) {
    e.preventDefault();
    if (!connName.trim() || (!connTargetPath.trim() && !connMirrorPath.trim())) {
      setErrorBanner('Informe o nome da conexão e o caminho da pasta ou ID da pasta na nuvem.');
      return;
    }
    setSavingConnection(true);
    setErrorBanner(null);
    try {
      const saved = await saveStorageConnection({
        name: connName,
        provider_type: connProviderType,
        target_path_or_folder_id: connTargetPath,
        subject_hint: connSubjectHint,
        area_hint: connAreaHint,
        api_key: connApiKey,
        access_token: connAccessToken,
        app_key: connAppKey,
        app_secret: connAppSecret,
        endpoint_url: connEndpointUrl,
        local_sync_mirror_path: connMirrorPath,
        recursive_scan: true,
        auto_generate_questions: connAutoGenerate,
      });
      await loadConnectorsData();
      // Escanear automaticamente após cadastrar
      await handleScanConnection(saved.id, connAutoGenerate);
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao salvar conexão.');
    } finally {
      setSavingConnection(false);
    }
  }

  async function handleScanConnection(connectionId: number, autoIngest: boolean = true) {
    setScanningConnId(connectionId);
    setErrorBanner(null);
    try {
      const res = await scanStorageConnection(connectionId, {
        auto_ingest_and_generate: autoIngest,
        questions_per_file: 8,
        max_files_to_ingest: 8,
      });
      await loadConnectorsData();
      await refreshBatteriesAndErrors();
      if (res.generated_batteries.length > 0) {
        setCurrentBattery(res.generated_batteries[0]);
      }
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao escanear e sincronizar arquivos da conexão.');
    } finally {
      setScanningConnId(null);
    }
  }

  async function handleIngestSingleFile(fileId: number) {
    setIngestingFileId(fileId);
    setErrorBanner(null);
    try {
      const res = await ingestDiscoveredFile(fileId, 10);
      await loadConnectorsData();
      await refreshBatteriesAndErrors();
      setCurrentBattery(res.battery);
      setSimuladoFinished(false);
      setSubtopicFilter('ALL');
      setActiveTab('solver');
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao processar arquivo e gerar questões.');
    } finally {
      setIngestingFileId(null);
    }
  }

  async function handleDeleteConnection(connectionId: number) {
    try {
      await deleteStorageConnection(connectionId);
      await loadConnectorsData();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao remover conexão.');
    }
  }

  async function handleSaveErrorSummaryNote(e: React.FormEvent) {
    e.preventDefault();
    if (!srTopic.trim() || !srSubtopic.trim() || !srConcept.trim()) {
      setErrorBanner('Indique o Tópico, o Subtópico e o Conceito da resposta que você resumiu.');
      return;
    }
    if (!srStudentSummary.trim()) {
      setErrorBanner('Escreva o seu resumo/anotação da resposta errada antes de salvar.');
      return;
    }
    setSavingSummaryNote(true);
    setErrorBanner(null);
    try {
      await createSpacedReviewErrorSummary({
        material_id: srMaterialId,
        assertion_id: srAssertionId,
        subject: srSubject,
        topic: srTopic,
        subtopic: srSubtopic,
        concept: srConcept,
        subconcept: srSubconcept,
        presented_concept_context: srPresentedContext,
        student_summary: srStudentSummary,
        personal_notes: srPersonalNotes,
        trap_type: srTrapType,
        pdf_page: srPdfPage,
        review_interval_days: 3,
      });
      setSrStudentSummary('');
      setSrPersonalNotes('');
      await loadSpacedReviewData();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao salvar resumo no banco.');
    } finally {
      setSavingSummaryNote(false);
    }
  }

  async function handleTrigger3DayReview(options?: {
    summaryIds?: number[];
    relationshipLinkId?: number;
  }) {
    setTriggering3DayReview(true);
    setErrorBanner(null);
    try {
      const res = await triggerSpacedReview3Days({
        summary_ids: options?.summaryIds,
        relationship_link_id: options?.relationshipLinkId,
        questions_count: 10,
        force_all_if_none_due: true,
      });
      setCurrentBattery(res.battery);
      setSimuladoFinished(false);
      setSubtopicFilter('ALL');
      setActiveTab('solver');
      await refreshBatteriesAndErrors();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao disparar revisão de 3 em 3 dias.');
    } finally {
      setTriggering3DayReview(false);
    }
  }

  async function handleQueueDoubtAssertion(assertion: AssertionItem) {
    setQueuingDoubtAssertionId(assertion.id);
    setErrorBanner(null);
    try {
      await queueDoubtAssertionTo3DayReview({
        assertion_id: assertion.id,
      });
      setCurrentBattery((prev) => {
        if (!prev || !prev.assertions) return prev;
        return {
          ...prev,
          assertions: prev.assertions.map((a) =>
            a.id === assertion.id ? { ...a, answered_with_doubt: true } : a
          ),
        };
      });
      await refreshBatteriesAndErrors();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao enviar questão com dúvida para a revisão de 3 dias.');
    } finally {
      setQueuingDoubtAssertionId(null);
    }
  }

  async function handleEvaluateAdaptiveIntervals(batteryId?: number, cycleId?: number) {
    setEvaluatingAdaptive(true);
    setErrorBanner(null);
    try {
      const res = await evaluateAdaptiveSpacedReview({
        battery_id: batteryId || currentBattery?.id,
        cycle_id: cycleId,
      });
      setLastAdaptiveResult(res);
      await loadSpacedReviewData();
    } catch (err: any) {
      setErrorBanner(
        err.message || 'Erro ao avaliar progressão adaptativa de intervalo (3 ➔ 7 ➔ 15 ➔ 30 dias).'
      );
    } finally {
      setEvaluatingAdaptive(false);
    }
  }

  async function handleGenerateContrastiveBattle(pairId?: string) {
    setGeneratingContrastivePairId(pairId || 'ALL');
    setErrorBanner(null);
    try {
      const res = await generateContrastiveBattleBattery({
        pair_id: pairId,
        questions_count: 6,
      });
      setCurrentBattery(res.battery);
      setSimuladoFinished(false);
      setSubtopicFilter('ALL');
      setActiveTab('solver');
      await refreshBatteriesAndErrors();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao gerar bateria de pares contrastivos.');
    } finally {
      setGeneratingContrastivePairId(null);
    }
  }

  async function handleAnalyzePdf(e: React.FormEvent) {
    e.preventDefault();
    if (studyFiles.length === 0) {
      setErrorBanner('Selecione pelo menos 1 arquivo PDF de material de estudo.');
      return;
    }
    setErrorBanner(null);
    setAnalyzingPdf(true);
    try {
      const res = await analyzeMaterials(studyFiles, questionFiles, selectedArea, subjectHint);
      setAnalysisResult(res);
      setCustomTitle(res.title);
      setCustomSubject(res.subject);
      setEditableSubtopics(
        res.subtopics.map((s) => ({
          ...s,
          target_questions: s.min_recommended_questions,
        }))
      );
      fetchStoredPdfFiles().then(setStoredPdfsList).catch(console.error);
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao analisar os PDFs enviados.');
    } finally {
      setAnalyzingPdf(false);
    }
  }

  async function handleGenerateBattery() {
    if (!analysisResult) return;
    setErrorBanner(null);
    setGeneratingBattery(true);
    try {
      const battery = await generateBattery({
        material_id: analysisResult.material_id,
        title: customTitle || analysisResult.title,
        subject: customSubject || analysisResult.subject,
        area: selectedArea,
        depth: selectedDepth,
        subtopic_plan: editableSubtopics,
      });
      setCurrentBattery(battery);
      setSimuladoFinished(false);
      setSubtopicFilter('ALL');
      setActiveTab('solver');
      refreshBatteriesAndErrors();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao gerar bateria de assertivas.');
    } finally {
      setGeneratingBattery(false);
    }
  }

  async function handleExtractAllPeriods(variationsPerPeriod: number) {
    if (!analysisResult) return;
    setErrorBanner(null);
    setGeneratingBattery(true);
    try {
      const battery = await extractPeriodAssertions(analysisResult.material_id, {
        variations_per_period: variationsPerPeriod,
        title: `${customTitle || analysisResult.title} — Períodos (${variationsPerPeriod}x)`,
        subject: customSubject || analysisResult.subject,
        area: selectedArea,
      });
      setCurrentBattery(battery);
      setSimuladoFinished(false);
      setSubtopicFilter('ALL');
      setActiveTab('solver');
      refreshBatteriesAndErrors();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao extrair assertivas por período.');
    } finally {
      setGeneratingBattery(false);
    }
  }

  async function handleLoadDemo() {
    setErrorBanner(null);
    setGeneratingBattery(true);
    try {
      const battery = await generateDemoBattery();
      setCurrentBattery(battery);
      setSimuladoFinished(false);
      setSubtopicFilter('ALL');
      setActiveTab('solver');
      refreshBatteriesAndErrors();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao carregar demonstração.');
    } finally {
      setGeneratingBattery(false);
    }
  }

  async function handleGenerateFixationFromTutor() {
    if (!tutorData) return;
    setGeneratingFixation(true);
    setErrorBanner(null);
    try {
      const bat = await generateFixationFromStoredPdf({
        material_id: tutorData.material_id,
        target_subtopic: tutorData.content_summary.target_subtopic,
        variations_per_period: 3,
      });
      setCurrentBattery(bat);
      setSimuladoFinished(false);
      setSubtopicFilter('ALL');
      setActiveTab('solver');
      refreshBatteriesAndErrors();
    } catch (e: any) {
      setErrorBanner(e.message || 'Erro ao gerar questões de fixação.');
    } finally {
      setGeneratingFixation(false);
    }
  }

  async function handleSubmitDiscursive(e: React.FormEvent) {
    e.preventDefault();
    if (!tutorData?.discursive_question) return;
    if (!discursiveText.trim()) {
      setErrorBanner('Digite sua resposta discursiva de até 5 linhas antes de salvar.');
      return;
    }
    setSubmittingDiscursive(true);
    setErrorBanner(null);
    try {
      const saved = await submitDiscursive5LinesAnswer({
        question_id: tutorData.discursive_question.id,
        student_text: discursiveText,
      });
      setLastDiscursiveResult(saved);
      setDiscursiveHistory((prev) => [saved, ...prev]);
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao salvar resposta discursiva.');
    } finally {
      setSubmittingDiscursive(false);
    }
  }

  function updateSubtopicQuestionCount(idx: number, delta: number) {
    setEditableSubtopics((prev) =>
      prev.map((item, i) => {
        if (i !== idx) return item;
        const current = item.target_questions ?? item.min_recommended_questions;
        return { ...item, target_questions: Math.max(0, Math.min(30, current + delta)) };
      })
    );
  }

  function applyPresetMultiplier(factor: number, onlyHighRecurrence: boolean = false) {
    setEditableSubtopics((prev) =>
      prev.map((item) => {
        if (onlyHighRecurrence && !['Muito Alta', 'Alta'].includes(item.recurrence_level)) {
          return { ...item, target_questions: 0 };
        }
        return {
          ...item,
          target_questions: Math.max(1, Math.round(item.min_recommended_questions * factor)),
        };
      })
    );
  }

  async function handleAnswerAssertion(
    assertion: AssertionItem,
    choice: 'C' | 'E' | 'BLANK' | 'RESET'
  ) {
    if (!currentBattery) return;
    try {
      const updated = await submitAssertionAnswer(assertion.id, { user_answer: choice });
      setCurrentBattery((prev) => {
        if (!prev || !prev.assertions) return prev;
        return {
          ...prev,
          assertions: prev.assertions.map((a) => (a.id === updated.id ? updated : a)),
        };
      });
    } catch (err) {
      console.error(err);
    }
  }

  async function handleToggleFavorite(assertion: AssertionItem) {
    try {
      const updated = await submitAssertionAnswer(assertion.id, {
        is_favorite: !assertion.is_favorite,
      });
      setCurrentBattery((prev) => {
        if (!prev || !prev.assertions) return prev;
        return {
          ...prev,
          assertions: prev.assertions.map((a) => (a.id === updated.id ? updated : a)),
        };
      });
      if (activeTab === 'errors') {
        refreshBatteriesAndErrors();
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function handleWordClick(assertion: AssertionItem, wordIndex: number) {
    if (annotationTool === 'none') return;
    const existing = assertion.annotations || [];
    const foundIdx = existing.findIndex((a) => a.wordIndex === wordIndex);
    let nextAnnotations: WordAnnotation[];

    if (foundIdx >= 0) {
      if (existing[foundIdx].type === annotationTool) {
        nextAnnotations = existing.filter((_, idx) => idx !== foundIdx);
      } else {
        nextAnnotations = existing.map((a, idx) =>
          idx === foundIdx ? { wordIndex, type: annotationTool } : a
        );
      }
    } else {
      nextAnnotations = [...existing, { wordIndex, type: annotationTool }];
    }

    try {
      const updated = await submitAssertionAnswer(assertion.id, {
        annotations: nextAnnotations,
      });
      setCurrentBattery((prev) => {
        if (!prev || !prev.assertions) return prev;
        return {
          ...prev,
          assertions: prev.assertions.map((a) => (a.id === updated.id ? updated : a)),
        };
      });
    } catch (e) {
      console.error(e);
    }
  }

  async function handleReinforceFromErrors() {
    setReinforcingErrors(true);
    setErrorBanner(null);
    try {
      const newBat = await generateErrorReinforcement({ questions_per_error: 2 });
      setCurrentBattery(newBat);
      setSimuladoFinished(false);
      setSubtopicFilter('ALL');
      setActiveTab('solver');
      refreshBatteriesAndErrors();
    } catch (err: any) {
      setErrorBanner(err.message || 'Erro ao gerar caderno de reforço.');
    } finally {
      setReinforcingErrors(false);
    }
  }

  async function handleSaveSettings(e: React.FormEvent) {
    e.preventDefault();
    try {
      const updated = await updateSettings({
        gemini_api_key: apiKeyInput,
        gemini_model: modelInput,
        default_area: selectedArea,
        default_depth: selectedDepth,
      });
      setSettings(updated);
      setShowSettingsModal(false);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleTestApi() {
    setTestingApi(true);
    setApiTestStatus(null);
    try {
      const res = await testGeminiConnection(apiKeyInput, modelInput);
      setApiTestStatus(res);
    } catch (err: any) {
      setApiTestStatus({ ok: false, message: err.message });
    } finally {
      setTestingApi(false);
    }
  }

  // Solver Score Calculation (Cebraspe Net Score: 1 wrong cancels 1 right)
  const solverMetrics = useMemo(() => {
    const list = currentBattery?.assertions || [];
    const total = list.length;
    let answered = 0;
    let blank = 0;
    let correct = 0;
    let wrong = 0;
    let favorites = 0;

    for (const a of list) {
      if (a.is_favorite) favorites++;
      if (a.user_answer === 'BLANK') {
        blank++;
        answered++;
      } else if (a.user_answer === 'C' || a.user_answer === 'E') {
        answered++;
        if (a.user_answer === a.answer) correct++;
        else wrong++;
      }
    }
    const netScore = correct - wrong;
    const rawPct = correct + wrong > 0 ? Math.round((correct / (correct + wrong)) * 100) : 0;
    const netPct = total > 0 ? Math.round((Math.max(0, netScore) / total) * 100) : 0;

    return { total, answered, blank, correct, wrong, favorites, netScore, rawPct, netPct };
  }, [currentBattery]);

  const totalPlannedQuestions = useMemo(
    () =>
      editableSubtopics.reduce(
        (acc, s) => acc + (s.target_questions ?? s.min_recommended_questions),
        0
      ),
    [editableSubtopics]
  );

  const filteredAssertions = useMemo(() => {
    const list = currentBattery?.assertions || [];
    if (subtopicFilter === 'ALL') return list;
    if (subtopicFilter === 'ERRORS') return list.filter((a) => a.is_correct === 0);
    if (subtopicFilter === 'FAVORITES') return list.filter((a) => a.is_favorite);
    return list.filter((a) => a.subtopic === subtopicFilter);
  }, [currentBattery, subtopicFilter]);

  const discursiveLinesCount = useMemo(() => {
    if (!discursiveText.trim()) return 0;
    const explicitLines = discursiveText.split('\n').length;
    const charEstimatedLines = Math.ceil(discursiveText.length / 90);
    return Math.max(explicitLines, charEstimatedLines);
  }, [discursiveText]);

  function getRecurrenceBadgeStyle(level: string) {
    switch (level) {
      case 'Muito Alta':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
      case 'Alta':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
      case 'Média':
        return 'bg-sky-500/20 text-sky-300 border-sky-500/40';
      default:
        return 'bg-slate-700/60 text-slate-300 border-slate-600';
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navbar */}
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
              <Target className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-bold text-base sm:text-lg tracking-tight text-white">
                  CebraspeLab
                </h1>
                <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  SQL+NoSQL
                </span>
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-xl border border-slate-800 overflow-x-auto">
            <button
              onClick={() => setActiveTab('generator')}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'generator'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>1. PDF & Períodos</span>
            </button>

            <button
              onClick={() => setActiveTab('solver')}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'solver'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>2. Resolver Bateria</span>
              {currentBattery && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/25 text-indigo-200">
                  {currentBattery.assertions?.length || currentBattery.total_questions}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('tutor')}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'tutor'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <PenTool className="w-3.5 h-3.5" />
              <span>3. Discursiva 5 Linhas</span>
            </button>

            <button
              onClick={() => setActiveTab('spaced')}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'spaced'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <CalendarClock className="w-3.5 h-3.5" />
              <span>4. Revisão 3 em 3 Dias</span>
              {spacedOverview && spacedOverview.total_summaries > 0 && (
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                    spacedOverview.due_for_review_count > 0
                      ? 'bg-rose-500 text-white animate-pulse'
                      : 'bg-emerald-500/20 text-emerald-300'
                  }`}
                >
                  {spacedOverview.due_for_review_count > 0
                    ? `${spacedOverview.due_for_review_count} pendente!`
                    : spacedOverview.total_summaries}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('connectors')}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'connectors'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Cloud className="w-3.5 h-3.5" />
              <span>5. Conexões (FS & Nuvem)</span>
            </button>

            <button
              onClick={() => setActiveTab('errors')}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'errors'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>6. Caderno de Erros</span>
            </button>

            <button
              onClick={() => setActiveTab('history')}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap ${
                activeTab === 'history'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Database className="w-3.5 h-3.5" />
              <span className="hidden lg:inline">7. Cofre PDFs</span>
            </button>
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setShowBridgeModal(true)}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-xl border text-xs font-semibold transition cursor-pointer ${
                bridgeOffline
                  ? 'bg-rose-950/70 border-rose-500/50 text-rose-200'
                  : 'bg-slate-900/80 border-slate-800 hover:bg-slate-800 text-emerald-300'
              }`}
              title="Status da Ponte Híbrida (GitHub Pages <-> Banco Local no seu PC) e Licença Comercial"
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  bridgeOffline ? 'bg-rose-400 animate-pulse' : 'bg-emerald-400'
                }`}
              />
              <HardDrive className="w-3.5 h-3.5" />
              <span className="hidden xl:inline">
                {bridgeOffline
                  ? 'Conectar PC Local'
                  : isRunningOnRemotePagesUI()
                  ? 'Pages ➔ PC Local'
                  : 'PC Local Ativo'}
              </span>
            </button>

            <button
              onClick={() => setShowSettingsModal(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-800 bg-slate-900/80 hover:bg-slate-800 text-xs font-medium transition cursor-pointer shrink-0"
              title="Configurar Gemini API e Padrões"
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  settings?.has_api_key ? 'bg-emerald-400 shadow-sm shadow-emerald-400' : 'bg-amber-400'
                }`}
              />
              <Settings className="w-4 h-4 text-slate-400" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        {bridgeOffline && (
          <div className="mb-6 p-4 rounded-2xl bg-amber-950/60 border border-amber-500/40 flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-amber-100 text-xs sm:text-sm">
            <div className="space-y-1">
              <div className="font-bold text-amber-300 flex items-center gap-2">
                <HardDrive className="w-4 h-4 shrink-0" />
                <span>
                  Interface Web (GitHub Pages) aguardando conexão com o Banco Local no seu PC ({localServerInput})
                </span>
              </div>
              <p className="text-slate-300">
                Para acessar seus PDFs, banco SQL+NoSQL local, pastas do computador e drives de nuvem com total privacidade, execute{' '}
                <code className="px-1.5 py-0.5 rounded bg-slate-900 text-emerald-300 font-mono">
                  CebraspeLab-Universal.cmd
                </code>{' '}
                (ou <code className="px-1.5 py-0.5 rounded bg-slate-900 text-emerald-300 font-mono">CebraspeLab-Universal.pyz</code>) na sua máquina e clique em Reconectar.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => loadInitialData()}
                className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs cursor-pointer"
              >
                Reconectar Agora
              </button>
              <button
                onClick={() => setShowBridgeModal(true)}
                className="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-slate-200 font-semibold text-xs cursor-pointer"
              >
                Configurar Porta Local
              </button>
            </div>
          </div>
        )}
        {errorBanner && (
          <div className="mb-6 p-4 rounded-xl bg-rose-950/60 border border-rose-500/40 flex items-center justify-between text-rose-200 text-sm">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0" />
              <span>{errorBanner}</span>
            </div>
            <button onClick={() => setErrorBanner(null)} className="text-xs underline">
              Fechar
            </button>
          </div>
        )}

        {/* ===================================================================
            TAB 1: UPLOAD DE PDF, PERSISTÊNCIA SQL+NoSQL & PARSEAMENTO DE PERÍODOS
           =================================================================== */}
        {activeTab === 'generator' && (
          <div className="space-y-8">
            <div className="rounded-2xl bg-gradient-to-r from-indigo-950/70 via-slate-900 to-slate-900 border border-indigo-500/30 p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
              <div className="space-y-2 max-w-2xl">
                <div className="inline-flex items-center gap-2 text-xs font-semibold text-indigo-300 bg-indigo-500/15 px-3 py-1 rounded-full border border-indigo-500/30">
                  <Flame className="w-3.5 h-3.5 text-amber-400" />
                  Persistência Híbrida SQL + NoSQL • Períodos • Revisão 3 em 3 Dias
                </div>
                <h2 className="text-xl sm:text-2xl font-bold text-white">
                  Armazene seus PDFs e Extraia Múltiplas Questões de Cada Subtópico
                </h2>
                <p className="text-sm text-slate-300 leading-relaxed">
                  Todo PDF enviado é persistido no cofre binário <strong>SQL + NoSQL</strong>. O parser divide o
                  conteúdo em <strong>tópicos, subtópicos e períodos sintáticos</strong> para criar múltiplas
                  assertivas de Certo/Errado, questões discursivas de 5 linhas e revisões espaçadas de 3 em 3 dias.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-3 shrink-0 w-full md:w-auto">
                <button
                  onClick={handleLoadDemo}
                  disabled={generatingBattery}
                  className="px-4 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-100 text-sm font-medium flex items-center justify-center gap-2 transition cursor-pointer"
                >
                  {generatingBattery ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4 text-emerald-400" />
                  )}
                  <span>Testar Bateria Demo (Atos Adm.)</span>
                </button>
              </div>
            </div>

            <form
              onSubmit={handleAnalyzePdf}
              className="grid grid-cols-1 lg:grid-cols-3 gap-6 bg-slate-900/70 border border-slate-800 rounded-2xl p-6"
            >
              <div className="space-y-3">
                <label className="block text-sm font-semibold text-slate-200">
                  1. PDF(s) do Material de Estudo (Salvo no Banco SQL+NoSQL){' '}
                  <span className="text-rose-400">*</span>
                </label>
                <p className="text-xs text-slate-400">
                  Apostilas de cursinho (teoria + questões no mesmo PDF), resumos ou lei seca.
                </p>
                <label className="flex flex-col items-center justify-center border-2 border-dashed border-slate-700 hover:border-indigo-500/70 rounded-xl p-5 cursor-pointer bg-slate-950/50 transition group">
                  <Upload className="w-7 h-7 text-indigo-400 group-hover:scale-110 transition-transform mb-2" />
                  <span className="text-xs font-medium text-slate-200 text-center">
                    Clique para enviar e armazenar PDF(s)
                  </span>
                  <span className="text-[11px] text-slate-500 mt-1">PDF, TXT ou MD</span>
                  <input
                    type="file"
                    accept=".pdf,.txt,.md"
                    multiple
                    onChange={(e) => setStudyFiles(Array.from(e.target.files || []))}
                    className="hidden"
                  />
                </label>
                {studyFiles.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    {studyFiles.map((f, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between text-xs bg-indigo-950/40 border border-indigo-500/30 px-3 py-1.5 rounded-lg text-indigo-200"
                      >
                        <span className="truncate">{f.name}</span>
                        <span className="text-[10px] text-indigo-400 ml-2 shrink-0">
                          {(f.size / 1024 / 1024).toFixed(2)} MB
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-semibold text-slate-200">
                  2. Caderno de Questões Cebraspe{' '}
                  <span className="text-xs font-normal text-slate-400">(Opcional)</span>
                </label>
                <p className="text-xs text-slate-400">
                  Se seu PDF de teoria não tiver questões no final, anexe um PDF/JSON de questões da Cebraspe.
                </p>
                <label className="flex flex-col items-center justify-center border-2 border-dashed border-slate-800 hover:border-amber-500/60 rounded-xl p-5 cursor-pointer bg-slate-950/50 transition group">
                  <FileText className="w-7 h-7 text-amber-400 group-hover:scale-110 transition-transform mb-2" />
                  <span className="text-xs font-medium text-slate-200 text-center">
                    Anexar PDF/JSON de provas ou TEC/QC
                  </span>
                  <span className="text-[11px] text-slate-500 mt-1">
                    Opcional — também persistido no banco
                  </span>
                  <input
                    type="file"
                    accept=".pdf,.json,.txt,.md"
                    multiple
                    onChange={(e) => setQuestionFiles(Array.from(e.target.files || []))}
                    className="hidden"
                  />
                </label>
                {questionFiles.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    {questionFiles.map((f, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between text-xs bg-amber-950/40 border border-amber-500/30 px-3 py-1.5 rounded-lg text-amber-200"
                      >
                        <span className="truncate">{f.name}</span>
                        <button
                          type="button"
                          onClick={() =>
                            setQuestionFiles((prev) => prev.filter((_, idx) => idx !== i))
                          }
                          className="text-[10px] text-amber-400 hover:underline ml-2"
                        >
                          Remover
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-4 flex flex-col justify-between">
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                      Área / Perfil de Prova Cebraspe
                    </label>
                    <select
                      value={selectedArea}
                      onChange={(e) => setSelectedArea(e.target.value)}
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500"
                    >
                      {AREAS.map((a) => (
                        <option key={a} value={a}>
                          {a}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                      Nível de Profundidade das Assertivas
                    </label>
                    <select
                      value={selectedDepth}
                      onChange={(e) => setSelectedDepth(e.target.value)}
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500"
                    >
                      {DEPTHS.map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">
                      Disciplina / Matéria (Opcional)
                    </label>
                    <input
                      type="text"
                      value={subjectHint}
                      onChange={(e) => setSubjectHint(e.target.value)}
                      placeholder="Ex: Direito Constitucional, Redes, AFO..."
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={analyzingPdf}
                  className="w-full py-3 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 font-semibold text-sm text-white shadow-lg shadow-indigo-600/25 flex items-center justify-center gap-2 transition cursor-pointer"
                >
                  {analyzingPdf ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Salvando no Banco & Parseando Períodos...</span>
                    </>
                  ) : (
                    <>
                      <TrendingUp className="w-4 h-4" />
                      <span>1. Armazenar PDF & Mapear Subtópicos/Períodos</span>
                    </>
                  )}
                </button>
              </div>
            </form>

            {analysisResult && (
              <div className="bg-slate-900/90 border border-indigo-500/40 rounded-2xl p-6 space-y-6 shadow-xl">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800 pb-5">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>
                        PDF Persistido no Banco (ID #{analysisResult.material_id}) •{' '}
                        {analysisResult.total_pages} página(s) •{' '}
                        {analysisResult.total_periods || 0} períodos extraídos
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 pt-1">
                      <input
                        type="text"
                        value={customSubject}
                        onChange={(e) => setCustomSubject(e.target.value)}
                        className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-sm font-bold text-indigo-300"
                      />
                      <span className="text-slate-600">/</span>
                      <input
                        type="text"
                        value={customTitle}
                        onChange={(e) => setCustomTitle(e.target.value)}
                        className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-sm font-semibold text-white min-w-[260px]"
                      />
                    </div>
                    <p className="text-xs text-slate-400 pt-1">{analysisResult.analysis_summary}</p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-slate-400 mr-1">Ajuste rápido:</span>
                    <button
                      type="button"
                      onClick={() => applyPresetMultiplier(1, false)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 cursor-pointer"
                    >
                      Mínimo Recomendado (1x)
                    </button>
                    <button
                      type="button"
                      onClick={() => applyPresetMultiplier(1.5, false)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-amber-300 border border-amber-500/30 cursor-pointer"
                    >
                      Bateria Intensiva (1.5x)
                    </button>
                    <button
                      type="button"
                      onClick={() => applyPresetMultiplier(1.2, true)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium bg-rose-950/60 hover:bg-rose-900/60 text-rose-200 border border-rose-500/30 cursor-pointer"
                    >
                      Foco Pareto 80/20
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4">
                  {editableSubtopics.map((sub, idx) => {
                    const count = sub.target_questions ?? sub.min_recommended_questions;
                    return (
                      <div
                        key={idx}
                        className="rounded-xl bg-slate-950/80 border border-slate-800 p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 hover:border-slate-700 transition"
                      >
                        <div className="space-y-2 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${getRecurrenceBadgeStyle(
                                sub.recurrence_level
                              )}`}
                            >
                              Recorrência {sub.recurrence_level} ({sub.recurrence_percentage}%)
                            </span>
                            {sub.topic && (
                              <span className="text-xs text-indigo-300 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-500/30">
                                {sub.topic}
                              </span>
                            )}
                            <span className="text-xs text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                              {sub.pages_reference}
                            </span>
                            {typeof sub.periods_count === 'number' && sub.periods_count > 0 && (
                              <span className="text-xs text-emerald-300 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                                {sub.periods_count} período(s) extraído(s)
                              </span>
                            )}
                          </div>

                          <h4 className="font-semibold text-base text-white">{sub.subtopic}</h4>

                          <div className="w-full max-w-md h-1.5 bg-slate-800 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-indigo-500 to-rose-500 rounded-full"
                              style={{
                                width: `${Math.min(100, Math.max(8, sub.recurrence_percentage))}%`,
                              }}
                            />
                          </div>

                          {sub.cebraspe_focus_points && sub.cebraspe_focus_points.length > 0 && (
                            <div className="pt-1">
                              <ul className="mt-1 space-y-0.5">
                                {sub.cebraspe_focus_points.map((fp, fpIdx) => (
                                  <li
                                    key={fpIdx}
                                    className="text-xs text-slate-300 flex items-start gap-1.5"
                                  >
                                    <ChevronRight className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
                                    <span>{fp}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>

                        <div className="flex md:flex-col items-center justify-between w-full md:w-auto bg-slate-900 px-4 py-3 rounded-xl border border-slate-800 shrink-0 gap-2">
                          <span className="text-[11px] text-slate-400 font-medium">
                            Nº de Assertivas (Mín. rec: {sub.min_recommended_questions})
                          </span>
                          <div className="flex items-center gap-3">
                            <button
                              type="button"
                              onClick={() => updateSubtopicQuestionCount(idx, -1)}
                              className="w-7 h-7 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 flex items-center justify-center font-bold cursor-pointer"
                            >
                              -
                            </button>
                            <span className="text-lg font-bold text-indigo-300 w-8 text-center">
                              {count}
                            </span>
                            <button
                              type="button"
                              onClick={() => updateSubtopicQuestionCount(idx, 1)}
                              className="w-7 h-7 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 flex items-center justify-center font-bold cursor-pointer"
                            >
                              +
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="flex flex-col lg:flex-row items-center justify-between gap-4 pt-4 border-t border-slate-800">
                  <div className="text-sm text-slate-300 space-y-1">
                    <div>
                      Total planejado para geração:{' '}
                      <strong className="text-white text-lg">
                        {totalPlannedQuestions} assertivas inéditas
                      </strong>{' '}
                      no padrão Cebraspe (~50% C / 50% E)
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto justify-end">
                    <button
                      type="button"
                      onClick={() => handleExtractAllPeriods(2)}
                      disabled={generatingBattery}
                      className="px-4 py-3 rounded-xl bg-emerald-950/70 hover:bg-emerald-900/80 border border-emerald-500/40 text-emerald-200 font-semibold text-xs sm:text-sm flex items-center gap-2 transition cursor-pointer"
                    >
                      <Layers className="w-4 h-4 text-emerald-400" />
                      <span>Extrair dos Períodos (2x por Período)</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleExtractAllPeriods(3)}
                      disabled={generatingBattery}
                      className="px-4 py-3 rounded-xl bg-amber-950/70 hover:bg-amber-900/80 border border-amber-500/40 text-amber-200 font-semibold text-xs sm:text-sm flex items-center gap-2 transition cursor-pointer"
                    >
                      <Flame className="w-4 h-4 text-amber-400" />
                      <span>Extração Máxima (3x por Período)</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleGenerateBattery}
                      disabled={generatingBattery || totalPlannedQuestions === 0}
                      className="px-6 py-3.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 text-white font-bold text-sm shadow-lg shadow-indigo-600/30 flex items-center justify-center gap-2 transition cursor-pointer"
                    >
                      {generatingBattery ? (
                        <>
                          <Loader2 className="w-5 h-5 animate-spin" />
                          <span>Elaborando Assertivas...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-5 h-5" />
                          <span>2. Gerar {totalPlannedQuestions} Assertivas Cebraspe</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ===================================================================
            TAB 2: AMBIENTE DE RESOLUÇÃO (TREINO & SIMULADO CEBRASPE)
           =================================================================== */}
        {activeTab === 'solver' && (
          <div>
            {!currentBattery ? (
              <div className="text-center py-16 bg-slate-900/50 rounded-2xl border border-slate-800 space-y-4">
                <BookOpen className="w-12 h-12 text-slate-500 mx-auto" />
                <h3 className="text-lg font-semibold text-white">
                  Nenhuma bateria selecionada no momento
                </h3>
                <button
                  onClick={handleLoadDemo}
                  className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-sm font-semibold text-white inline-flex items-center gap-2 cursor-pointer"
                >
                  <Play className="w-4 h-4" />
                  <span>Carregar Bateria Demonstrativa</span>
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="bg-slate-900/95 border border-slate-800 rounded-2xl p-4 sm:p-5 space-y-4 shadow-lg">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-indigo-300 font-semibold">
                        <span>{currentBattery.subject}</span>
                        <span>•</span>
                        <span>Área: {currentBattery.area}</span>
                        <span>•</span>
                        <span>{currentBattery.depth}</span>
                      </div>
                      <h2 className="text-lg sm:text-xl font-bold text-white mt-0.5">
                        {currentBattery.title}
                      </h2>
                    </div>

                    <div className="flex flex-wrap items-center gap-2.5">
                      <button
                        onClick={() => handleEvaluateAdaptiveIntervals(currentBattery.id)}
                        disabled={evaluatingAdaptive}
                        className="px-3 py-2 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-200 text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                        title="Se acertar ≥85% da revisão, avança o intervalo de 3 para 7, 15 e 30 dias!"
                      >
                        {evaluatingAdaptive ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <TrendingUp className="w-3.5 h-3.5" />
                        )}
                        <span>Avaliar Retenção (≥85%) ➔ 3/7/15/30d</span>
                      </button>

                      <button
                        onClick={() => setActiveTab('spaced')}
                        className="px-3 py-2 rounded-xl bg-indigo-500/20 hover:bg-indigo-500/30 border border-indigo-500/40 text-indigo-200 text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                      >
                        <CalendarClock className="w-3.5 h-3.5" />
                        <span>Anotar Resumos & Revisão 3 em 3 Dias</span>
                      </button>

                      <button
                        onClick={() => setActiveTab('tutor')}
                        className="px-3 py-2 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                      >
                        <PenTool className="w-3.5 h-3.5" />
                        <span>Discursiva 5 Linhas</span>
                      </button>

                      <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800">
                        <button
                          onClick={() => {
                            setSolverMode('training');
                            setSimuladoFinished(false);
                          }}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                            solverMode === 'training'
                              ? 'bg-indigo-600 text-white'
                              : 'text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          Modo Treino
                        </button>
                        <button
                          onClick={() => {
                            setSolverMode('simulado');
                            setSimuladoFinished(false);
                          }}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                            solverMode === 'simulado'
                              ? 'bg-rose-600 text-white'
                              : 'text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          Modo Simulado (1 E anula 1 C)
                        </button>
                      </div>

                      {solverMode === 'simulado' && !simuladoFinished && (
                        <button
                          onClick={() => setSimuladoFinished(true)}
                          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white shadow-md cursor-pointer"
                        >
                          Finalizar e Corrigir Simulado
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Cebraspe Live Scoreboard */}
                  <div className="grid grid-cols-2 sm:grid-cols-6 gap-2.5 pt-2 border-t border-slate-800/80">
                    <div className="bg-slate-950/90 border border-slate-800 rounded-xl px-3 py-2">
                      <span className="text-[11px] text-slate-400 block">Progresso</span>
                      <span className="text-base font-bold text-white">
                        {solverMetrics.answered} / {solverMetrics.total}
                      </span>
                    </div>

                    {(solverMode === 'training' || simuladoFinished) && (
                      <>
                        <div className="bg-emerald-950/40 border border-emerald-500/30 rounded-xl px-3 py-2">
                          <span className="text-[11px] text-emerald-300 block">Acertos (+)</span>
                          <span className="text-base font-bold text-emerald-400">
                            {solverMetrics.correct}
                          </span>
                        </div>

                        <div className="bg-rose-950/40 border border-rose-500/30 rounded-xl px-3 py-2">
                          <span className="text-[11px] text-rose-300 block">Erros (-1)</span>
                          <span className="text-base font-bold text-rose-400">
                            {solverMetrics.wrong}
                          </span>
                        </div>

                        <div className="bg-slate-950/90 border border-slate-800 rounded-xl px-3 py-2">
                          <span className="text-[11px] text-slate-400 block">Em Branco (0)</span>
                          <span className="text-base font-bold text-slate-300">
                            {solverMetrics.blank}
                          </span>
                        </div>

                        <div className="bg-indigo-950/50 border border-indigo-500/40 rounded-xl px-3 py-2">
                          <span className="text-[11px] text-indigo-300 block">
                            Nota Líquida Cebraspe
                          </span>
                          <span
                            className={`text-base font-extrabold ${
                              solverMetrics.netScore >= 0 ? 'text-indigo-300' : 'text-rose-400'
                            }`}
                          >
                            {solverMetrics.netScore > 0
                              ? `+${solverMetrics.netScore}`
                              : solverMetrics.netScore}{' '}
                            pts ({solverMetrics.netPct}%)
                          </span>
                        </div>

                        <div className="bg-slate-950/90 border border-slate-800 rounded-xl px-3 py-2">
                          <span className="text-[11px] text-slate-400 block">% Bruto</span>
                          <span className="text-base font-bold text-amber-300">
                            {solverMetrics.rawPct}%
                          </span>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Toolbars */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-slate-400 font-medium">Caneta de Prova:</span>
                      <button
                        type="button"
                        onClick={() =>
                          setAnnotationTool((t) => (t === 'strike' ? 'none' : 'strike'))
                        }
                        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition cursor-pointer ${
                          annotationTool === 'strike'
                            ? 'bg-rose-600/30 border-rose-500 text-rose-200 font-semibold'
                            : 'bg-slate-950 border-slate-800 text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        <Strikethrough className="w-3.5 h-3.5" />
                        <span>Riscar Palavra</span>
                      </button>

                      <button
                        type="button"
                        onClick={() =>
                          setAnnotationTool((t) => (t === 'highlight' ? 'none' : 'highlight'))
                        }
                        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition cursor-pointer ${
                          annotationTool === 'highlight'
                            ? 'bg-amber-500/30 border-amber-400 text-amber-200 font-semibold'
                            : 'bg-slate-950 border-slate-800 text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        <Highlighter className="w-3.5 h-3.5" />
                        <span>Marca-Texto</span>
                      </button>

                      <select
                        value={subtopicFilter}
                        onChange={(e) => setSubtopicFilter(e.target.value)}
                        className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-300"
                      >
                        <option value="ALL">Todos os Itens ({solverMetrics.total})</option>
                        <option value="ERRORS">Apenas Itens que Errei ({solverMetrics.wrong})</option>
                        <option value="FAVORITES">
                          Apenas Favoritas ({solverMetrics.favorites})
                        </option>
                        {Array.from(
                          new Set((currentBattery.assertions || []).map((a) => a.subtopic))
                        ).map((st) => (
                          <option key={st} value={st}>
                            Subtópico: {st}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        value={exportFilter}
                        onChange={(e) =>
                          setExportFilter(e.target.value as 'all' | 'errors_or_favorites')
                        }
                        className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-300"
                      >
                        <option value="all">Exportar: Todas</option>
                        <option value="errors_or_favorites">Exportar: Só Erros/Fav</option>
                      </select>

                      <a
                        href={getExportUrl(currentBattery.id, 'apkg', exportFilter)}
                        download
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/25 hover:bg-indigo-600/40 border border-indigo-500/40 text-indigo-200 font-semibold transition"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Anki (.apkg)</span>
                      </a>

                      <a
                        href={getExportUrl(currentBattery.id, 'csv', exportFilter)}
                        download
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 transition"
                      >
                        <FileSpreadsheet className="w-3.5 h-3.5" />
                        <span>.csv</span>
                      </a>

                      <a
                        href={getExportUrl(currentBattery.id, 'pdf', exportFilter)}
                        download
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/35 border border-rose-500/40 text-rose-200 font-semibold transition"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>PDF Prova</span>
                      </a>

                      <a
                        href={getExportUrl(currentBattery.id, 'md', exportFilter)}
                        download
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 transition"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>.md</span>
                      </a>
                    </div>
                  </div>
                </div>

                {/* Assertions List */}
                <div className="space-y-4">
                  {filteredAssertions.map((assertion, idx) => {
                    const prevAssertion = idx > 0 ? filteredAssertions[idx - 1] : null;
                    const showCommandHeader =
                      !prevAssertion || prevAssertion.command_text !== assertion.command_text;
                    const showFeedback =
                      (solverMode === 'training' && assertion.user_answer !== null) ||
                      (solverMode === 'simulado' && simuladoFinished);

                    const words = assertion.statement.split(' ');
                    const annMap = new Map(
                      (assertion.annotations || []).map((a) => [a.wordIndex, a.type])
                    );

                    return (
                      <React.Fragment key={assertion.id}>
                        {showCommandHeader && (
                          <div className="pt-3 pb-1 px-1">
                            <p className="text-sm font-semibold italic text-indigo-300 border-l-4 border-indigo-500 pl-3 py-1 bg-indigo-950/20 rounded-r-lg">
                              {assertion.command_text}
                            </p>
                          </div>
                        )}

                        <div
                          className={`rounded-2xl border p-5 transition ${
                            showFeedback && assertion.user_answer && assertion.user_answer !== 'BLANK'
                              ? assertion.is_correct === 1
                                ? 'bg-slate-900/90 border-emerald-500/40'
                                : 'bg-slate-900/90 border-rose-500/40'
                              : 'bg-slate-900/75 border-slate-800 hover:border-slate-700'
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs font-extrabold px-2.5 py-1 rounded-lg bg-slate-800 text-white">
                                Item #{assertion.item_number}
                              </span>
                              <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-slate-800/90 text-slate-300 border border-slate-700">
                                {assertion.subtopic}
                              </span>
                              <span
                                className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${getRecurrenceBadgeStyle(
                                  assertion.recurrence_level
                                )}`}
                              >
                                Recorrência {assertion.recurrence_level}
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => openErrorSummaryNoteFromAssertion(assertion)}
                                className="px-2.5 py-1 rounded-lg bg-indigo-950/70 hover:bg-indigo-900 border border-indigo-500/40 text-indigo-200 text-xs font-semibold flex items-center gap-1 cursor-pointer"
                                title="Escrever resumo desta resposta para revisar de 3 em 3 dias"
                              >
                                <NotebookPen className="w-3.5 h-3.5" />
                                <span>Resumir p/ Revisão 3 Dias</span>
                              </button>

                              <button
                                onClick={() => handleToggleFavorite(assertion)}
                                className={`p-1.5 rounded-lg border transition cursor-pointer ${
                                  assertion.is_favorite
                                    ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                                    : 'bg-slate-950 border-slate-800 text-slate-500 hover:text-slate-300'
                                }`}
                              >
                                <Star
                                  className="w-4 h-4"
                                  fill={assertion.is_favorite ? 'currentColor' : 'none'}
                                />
                              </button>
                            </div>
                          </div>

                          <div
                            className={`text-base leading-relaxed text-slate-100 mb-5 ${
                              annotationTool !== 'none' ? 'cursor-crosshair select-none' : ''
                            }`}
                          >
                            {words.map((word, wIdx) => {
                              const aType = annMap.get(wIdx);
                              return (
                                <React.Fragment key={wIdx}>
                                  <span
                                    onClick={() => handleWordClick(assertion, wIdx)}
                                    className={`rounded px-0.5 transition ${
                                      aType === 'strike'
                                        ? 'line-through decoration-rose-500 decoration-2 text-rose-400 bg-rose-950/50'
                                        : aType === 'highlight'
                                        ? 'bg-amber-400/30 text-amber-200 font-medium'
                                        : annotationTool !== 'none'
                                        ? 'hover:bg-slate-800'
                                        : ''
                                    }`}
                                  >
                                    {word}
                                  </span>{' '}
                                </React.Fragment>
                              );
                            })}
                          </div>

                          <div className="flex flex-wrap items-center gap-3">
                            <button
                              onClick={() => handleAnswerAssertion(assertion, 'C')}
                              className={`px-5 py-2.5 rounded-xl font-bold text-xs sm:text-sm flex items-center gap-2 border transition cursor-pointer ${
                                assertion.user_answer === 'C'
                                  ? 'bg-emerald-600 border-emerald-400 text-white shadow-lg shadow-emerald-600/25'
                                  : 'bg-slate-950 hover:bg-emerald-950/50 border-slate-800 hover:border-emerald-500/50 text-slate-200'
                              }`}
                            >
                              <CheckCircle2 className="w-4 h-4" />
                              <span>CERTO (C)</span>
                            </button>

                            <button
                              onClick={() => handleAnswerAssertion(assertion, 'E')}
                              className={`px-5 py-2.5 rounded-xl font-bold text-xs sm:text-sm flex items-center gap-2 border transition cursor-pointer ${
                                assertion.user_answer === 'E'
                                  ? 'bg-rose-600 border-rose-400 text-white shadow-lg shadow-rose-600/25'
                                  : 'bg-slate-950 hover:bg-rose-950/50 border-slate-800 hover:border-rose-500/50 text-slate-200'
                              }`}
                            >
                              <XCircle className="w-4 h-4" />
                              <span>ERRADO (E)</span>
                            </button>

                            <button
                              onClick={() => handleAnswerAssertion(assertion, 'BLANK')}
                              className={`px-4 py-2.5 rounded-xl font-semibold text-xs flex items-center gap-1.5 border transition cursor-pointer ${
                                assertion.user_answer === 'BLANK'
                                  ? 'bg-slate-700 border-slate-500 text-white'
                                  : 'bg-slate-950 hover:bg-slate-800 border-slate-800 text-slate-400'
                              }`}
                            >
                              <MinusCircle className="w-3.5 h-3.5" />
                              <span>Deixar em Branco (0 pt)</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => handleQueueDoubtAssertion(assertion)}
                              disabled={queuingDoubtAssertionId === assertion.id}
                              className={`px-3.5 py-2.5 rounded-xl font-bold text-xs flex items-center gap-1.5 border transition cursor-pointer ${
                                assertion.answered_with_doubt
                                  ? 'bg-amber-500/25 border-amber-400 text-amber-200 shadow-sm'
                                  : 'bg-slate-950 hover:bg-amber-950/40 border-amber-500/40 text-amber-300'
                              }`}
                              title="Envia automaticamente este item (mesmo que tenha acertado no chute ou com insegurança) direto para o Caderno de Revisão de 3 em 3 Dias!"
                            >
                              {queuingDoubtAssertionId === assertion.id ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <AlertTriangle className="w-3.5 h-3.5" />
                              )}
                              <span>
                                {assertion.answered_with_doubt
                                  ? 'Salvo na Revisão de 3 Dias (Dúvida)'
                                  : 'Acertei com Dúvida (Revisar em 3d)'}
                              </span>
                            </button>

                            {assertion.user_answer && (
                              <button
                                onClick={() => handleAnswerAssertion(assertion, 'RESET')}
                                className="text-xs text-slate-500 hover:text-slate-300 underline ml-auto cursor-pointer"
                              >
                                Limpar resposta
                              </button>
                            )}
                          </div>

                          {showFeedback && (
                            <div className="mt-5 pt-4 border-t border-slate-800 space-y-3 bg-slate-950/60 -mx-5 -mb-5 p-5 rounded-b-2xl">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span
                                    className={`px-3 py-1 rounded-lg text-xs font-extrabold ${
                                      assertion.answer === 'C'
                                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                        : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                                    }`}
                                  >
                                    GABARITO OFICIAL:{' '}
                                    {assertion.answer === 'C' ? 'CERTO' : 'ERRADO'}
                                  </span>

                                  {assertion.user_answer && assertion.user_answer !== 'BLANK' && (
                                    <span
                                      className={`text-xs font-bold px-2.5 py-1 rounded-lg ${
                                        assertion.is_correct === 1
                                          ? 'bg-emerald-600 text-white'
                                          : 'bg-rose-600 text-white'
                                      }`}
                                    >
                                      {assertion.is_correct === 1
                                        ? 'VOCÊ ACERTOU (+1 pt líquido)'
                                        : 'VOCÊ ERROU (-1 pt líquido)'}
                                    </span>
                                  )}

                                  {assertion.trap_type && (
                                    <span className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-violet-500/20 text-violet-300 border border-violet-500/30">
                                      Armadilha: {assertion.trap_type}
                                    </span>
                                  )}
                                </div>

                                {assertion.is_correct === 0 && (
                                  <button
                                    onClick={() => openErrorSummaryNoteFromAssertion(assertion)}
                                    className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                                  >
                                    <NotebookPen className="w-3.5 h-3.5" />
                                    <span>Anotar Resumo deste Erro (Revisar de 3 em 3 Dias)</span>
                                  </button>
                                )}
                              </div>

                              <p className="text-sm text-slate-200 leading-relaxed">
                                <strong className="text-white">Comentário: </strong>
                                {assertion.explanation}
                              </p>

                              {(assertion.pdf_quote || assertion.pdf_page) && (
                                <div className="p-3 rounded-xl bg-slate-900 border-l-4 border-indigo-500 text-xs text-slate-300 space-y-1">
                                  <div className="font-semibold text-indigo-300 flex items-center gap-1.5">
                                    <BookOpen className="w-3.5 h-3.5" />
                                    <span>
                                      Fundamentação no seu Material PDF{' '}
                                      {assertion.pdf_page ? `(${assertion.pdf_page})` : ''}:
                                    </span>
                                  </div>
                                  <p className="italic text-slate-300">"{assertion.pdf_quote}"</p>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ===================================================================
            TAB 3: MENTORIA DO PDF ARMAZENADO, RESUMO DIRECIONADO & DISCURSIVA 5 LINHAS
           =================================================================== */}
        {activeTab === 'tutor' && (
          <div className="space-y-6">
            {loadingTutor || !tutorData ? (
              <div className="p-12 text-center bg-slate-900/60 border border-slate-800 rounded-2xl space-y-3">
                <Loader2 className="w-8 h-8 animate-spin text-indigo-400 mx-auto" />
                <p className="text-sm text-slate-300">
                  Consultando PDF armazenado (SQL+NoSQL), avaliando seus erros e preparando resumo + questão discursiva de 5 linhas...
                </p>
              </div>
            ) : (
              <>
                <div className="rounded-2xl bg-gradient-to-r from-indigo-950/80 via-slate-900 to-slate-900 border border-indigo-500/40 p-6 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-bold border border-indigo-500/30">
                        PDF Armazenado #{tutorData.material_id}: {tutorData.material_title}
                      </span>
                      <span className="px-2.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 font-semibold border border-rose-500/30">
                        Foco de Erro Detectado: {tutorData.content_summary.target_subtopic}
                      </span>
                    </div>
                    <h2 className="text-xl font-bold text-white">
                      Diagnóstico de Erros, Resumo do Conteúdo & Discursiva Cebraspe (5 Linhas)
                    </h2>
                    <p className="text-xs sm:text-sm text-slate-300 max-w-3xl">
                      {tutorData.content_summary.executive_overview}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 shrink-0">
                    <button
                      onClick={() => loadTutorAndDiscursive(tutorData.material_id)}
                      className="px-3.5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 flex items-center gap-1.5 cursor-pointer"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      <span>Atualizar Diagnóstico</span>
                    </button>

                    <button
                      onClick={handleGenerateFixationFromTutor}
                      disabled={generatingFixation}
                      className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs sm:text-sm font-bold text-white shadow-lg shadow-emerald-600/25 flex items-center gap-2 cursor-pointer"
                    >
                      {generatingFixation ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Sparkles className="w-4 h-4" />
                      )}
                      <span>Gerar Mais Questões de Fixação deste Tópico</span>
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                      <div className="flex items-center gap-2">
                        <BookOpen className="w-5 h-5 text-indigo-400" />
                        <h3 className="text-base font-bold text-white">
                          Resumo Direcionado do Conteúdo (Extraído do PDF Armazenado)
                        </h3>
                      </div>
                      <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/30 font-semibold">
                        Armadilha: {tutorData.content_summary.dominant_trap}
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-500/30 space-y-1">
                      <span className="text-xs font-bold uppercase tracking-wider text-amber-300">
                        Regra de Ouro para Não Cair Mais Nessa Pegadinha:
                      </span>
                      <p className="text-xs sm:text-sm text-amber-100 leading-relaxed">
                        {tutorData.content_summary.golden_rule}
                      </p>
                    </div>

                    <div className="space-y-3">
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-400 block">
                        Períodos-Chave do seu PDF para Revisão e Fixação:
                      </span>
                      {tutorData.content_summary.key_periods_from_pdf.map((kp, i) => (
                        <div
                          key={i}
                          className="p-3.5 rounded-xl bg-slate-950/90 border border-slate-800 space-y-1.5"
                        >
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-bold text-indigo-300 bg-indigo-500/15 px-2 py-0.5 rounded">
                              Página {kp.page}
                            </span>
                            <span className="text-slate-400">{kp.focus}</span>
                          </div>
                          <p className="text-xs sm:text-sm text-slate-200 leading-relaxed">
                            "{kp.text}"
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="bg-slate-900/80 border border-indigo-500/40 rounded-2xl p-6 space-y-4">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                      <div className="flex items-center gap-2">
                        <PenTool className="w-5 h-5 text-emerald-400" />
                        <h3 className="text-base font-bold text-white">
                          Questão Discursiva Cebraspe (Até 5 Linhas)
                        </h3>
                      </div>
                      <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        Salva no Banco SQL + NoSQL
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                      <div className="text-xs font-bold text-indigo-300">
                        Conceito Alvo: {tutorData.discursive_question.target_concept}
                      </div>
                      <p className="text-xs sm:text-sm text-slate-100 whitespace-pre-line leading-relaxed">
                        {tutorData.discursive_question.prompt_text}
                      </p>
                    </div>

                    <form onSubmit={handleSubmitDiscursive} className="space-y-3">
                      <div className="flex items-center justify-between text-xs">
                        <label className="font-semibold text-slate-300">
                          Folha de Resposta Definitiva (Digite até 5 linhas):
                        </label>
                        <span
                          className={`font-bold px-2 py-0.5 rounded ${
                            discursiveLinesCount > 5
                              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                              : 'bg-slate-800 text-emerald-300'
                          }`}
                        >
                          Linhas: {discursiveLinesCount} / 5 ({discursiveText.length} caracteres)
                        </span>
                      </div>

                      <textarea
                        rows={5}
                        maxLength={600}
                        value={discursiveText}
                        onChange={(e) => setDiscursiveText(e.target.value)}
                        placeholder="Linha 1: Apresente o conceito/regra geral prevista no material...&#10;Linha 2-3: Explique a distinção/exceção que afasta a pegadinha da Cebraspe...&#10;Linha 4-5: Conclua de forma objetiva e técnica."
                        className="w-full rounded-xl bg-slate-950 border border-slate-700 focus:border-indigo-500 focus:outline-none p-3.5 text-sm text-white leading-7 font-mono"
                      />

                      <button
                        type="submit"
                        disabled={submittingDiscursive}
                        className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-emerald-600 hover:from-indigo-500 hover:to-emerald-500 text-white font-bold text-sm shadow-lg flex items-center justify-center gap-2 transition cursor-pointer"
                      >
                        {submittingDiscursive ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span>Salvando no Banco e Avaliando Discursiva...</span>
                          </>
                        ) : (
                          <>
                            <Send className="w-4 h-4" />
                            <span>Salvar Resposta no Banco de Dados & Avaliar (5 Linhas)</span>
                          </>
                        )}
                      </button>
                    </form>

                    {lastDiscursiveResult && (
                      <div className="p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/40 space-y-2.5 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-extrabold text-emerald-300 text-sm flex items-center gap-1.5">
                            <Award className="w-4 h-4" />
                            <span>
                              Resposta #{lastDiscursiveResult.response_id} Salva! Nota:{' '}
                              {lastDiscursiveResult.score} / 10.0
                            </span>
                          </span>
                          <span className="text-slate-400">
                            {lastDiscursiveResult.lines_used} linha(s)
                          </span>
                        </div>
                        <p className="text-slate-200 leading-relaxed">
                          {lastDiscursiveResult.feedback_text}
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 space-y-4">
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <Database className="w-4 h-4 text-indigo-400" />
                    <span>
                      Histórico de Respostas Discursivas de 5 Linhas Salvas no Banco (
                      {discursiveHistory.length})
                    </span>
                  </h3>

                  {discursiveHistory.length === 0 ? (
                    <p className="text-xs text-slate-400">
                      Nenhuma resposta discursiva enviada ainda. Digite sua resposta acima para salvá-la no banco!
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {discursiveHistory.map((item, idx) => (
                        <div
                          key={item.id || item.response_id || idx}
                          className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-indigo-300">{item.subtopic}</span>
                            <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold">
                              Nota: {item.score} / 10.0 ({item.lines_used} linhas)
                            </span>
                          </div>
                          <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-200 font-mono">
                            "{item.student_text}"
                          </div>
                          <p className="text-slate-400 leading-relaxed">{item.feedback_text}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* ===================================================================
            TAB 4: REVISÃO DE 3 EM 3 DIAS, MEUS RESUMOS DE ERROS & HIERARQUIA DE CONCEITOS
           =================================================================== */}
        {activeTab === 'spaced' && (
          <div className="space-y-6">
            {/* Top 3-Day Review Trigger Banner */}
            <div className="rounded-2xl bg-gradient-to-r from-indigo-950/90 via-violet-950/60 to-slate-900 border border-indigo-500/40 p-6 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-5 shadow-xl">
              <div className="space-y-1.5 max-w-2xl">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30 flex items-center gap-1">
                    <Bell className="w-3.5 h-3.5" />
                    <span>Ciclo Automático: Revisão de 3 em 3 Dias</span>
                  </span>
                  <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-semibold border border-indigo-500/30">
                    {spacedOverview?.total_summaries || 0} resumo(s) salvo(s) no banco
                  </span>
                </div>
                <h2 className="text-xl font-bold text-white">
                  Meus Resumos de Respostas Erradas & Revisão Espaçada (3 em 3 Dias)
                </h2>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  Escreva com suas palavras o resumo das questões que você errou, vincule à árvore{' '}
                  <strong>Tópico ➔ Subtópico ➔ Conceito ➔ Subconceito</strong> e salve no banco. De{' '}
                  <strong>3 em 3 dias</strong>, o sistema dispara a revisão gerando{' '}
                  <strong>+10 questões inéditas</strong> sobre os seus resumos!
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3 shrink-0">
                <button
                  onClick={() => handleEvaluateAdaptiveIntervals()}
                  disabled={evaluatingAdaptive || !spacedOverview?.total_summaries}
                  className="px-4 py-3.5 rounded-xl bg-emerald-600/25 hover:bg-emerald-600/40 border border-emerald-500/50 disabled:opacity-40 text-emerald-200 font-bold text-xs sm:text-sm flex items-center gap-2 transition cursor-pointer"
                  title="Avalia a última bateria de revisão: se ≥85% de acerto, evolui o intervalo de 3 ➔ 7 ➔ 15 ➔ 30 dias!"
                >
                  {evaluatingAdaptive ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <TrendingUp className="w-4 h-4" />
                  )}
                  <span>Avaliar ≥85% (3 ➔ 7 ➔ 15 ➔ 30d)</span>
                </button>

                <button
                  onClick={() => handleTrigger3DayReview()}
                  disabled={triggering3DayReview || !spacedOverview?.total_summaries}
                  className="px-5 py-3.5 rounded-xl bg-gradient-to-r from-amber-500 to-rose-600 hover:from-amber-400 hover:to-rose-500 disabled:opacity-40 text-white font-extrabold text-xs sm:text-sm shadow-lg shadow-rose-600/25 flex items-center gap-2 transition cursor-pointer shrink-0"
                >
                  {triggering3DayReview ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Disparando Revisão (+10 Questões)...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>Disparar Revisão de 3 em 3 Dias (+10 Questões Agora)</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {lastAdaptiveResult && (
              <div className="rounded-2xl bg-emerald-950/35 border border-emerald-500/40 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                <div className="space-y-1">
                  <div className="font-extrabold text-emerald-300 text-sm flex items-center gap-2">
                    <TrendingUp className="w-4 h-4" />
                    <span>
                      Avaliação Adaptativa (Escada 3 ➔ 7 ➔ 15 ➔ 30 Dias): Taxa de Acerto de{' '}
                      {lastAdaptiveResult.accuracy_percentage}% (Meta: ≥
                      {lastAdaptiveResult.mastery_threshold_percentage}%)
                    </span>
                  </div>
                  <p className="text-slate-300">
                    {lastAdaptiveResult.achieved_mastery
                      ? `Excelente! Domínio ≥85% atingido. ${lastAdaptiveResult.updated_count} resumo(s) avançaram para o próximo degrau de intervalo espaçado (3 ➔ 7 ➔ 15 ➔ 30 dias)!`
                      : `Atenção: Acurácia abaixo de 85%. Os conceitos com erro foram mantidos/reiniciados no ciclo intensivo de 3 em 3 dias para blindar sua retenção.`}
                  </p>
                </div>
                <button
                  onClick={() => setLastAdaptiveResult(null)}
                  className="text-slate-400 hover:text-white underline shrink-0"
                >
                  Ocultar
                </button>
              </div>
            )}

            {/* GERADOR DE PARES CONTRASTIVOS CEBRASPE (BATALHA DE SUBCONCEITOS IRMÃOS) */}
            <div className="bg-slate-900/90 border border-amber-500/40 rounded-2xl p-5 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase bg-amber-500/20 text-amber-300 border border-amber-500/40">
                      Treino Anti-Inversão Cebraspe
                    </span>
                    <h3 className="text-base font-bold text-white">
                      Gerador de Pares Contrastivos (Subconceitos Irmãos que a Cebraspe Troca entre Si)
                    </h3>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    A maior armadilha da Cebraspe é trocar a definição de um instituto pelo seu irmão gêmeo. Gere baterias curtas confrontando lado a lado os pares mais cobrados!
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {contrastivePairs.map((pair) => (
                  <div
                    key={pair.id}
                    className="p-4 rounded-xl bg-slate-950 border border-slate-800 hover:border-amber-500/40 transition flex flex-col justify-between gap-3"
                  >
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-indigo-300 font-semibold">{pair.subject}</span>
                        <span className="text-slate-500">{pair.subtopic}</span>
                      </div>
                      <div className="text-xs sm:text-sm font-extrabold text-amber-300">
                        ⚔️ {pair.concept_a} <span className="text-slate-500 font-normal">vs.</span>{' '}
                        {pair.concept_b}
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">
                        {pair.key_distinction}
                      </p>
                    </div>

                    <div className="flex justify-end pt-2 border-t border-slate-800/80">
                      <button
                        type="button"
                        onClick={() => handleGenerateContrastiveBattle(pair.id)}
                        disabled={generatingContrastivePairId !== null}
                        className="px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                      >
                        {generatingContrastivePairId === pair.id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Flame className="w-3.5 h-3.5" />
                        )}
                        <span>Gerar Batalha Contrastiva (6 Itens)</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column (5 cols): Presented Concepts from Errors & Hierarchy Picker */}
              <div className="lg:col-span-5 bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-indigo-300 flex items-center gap-2">
                    <BookOpen className="w-4 h-4" />
                    <span>1. Conceitos das Questões que Você Errou</span>
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    Clique para carregar no formulário
                  </span>
                </div>

                {!conceptsHierarchy?.presented_concepts_from_errors.length ? (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-400">
                    Você também pode preencher livremente o formulário ao lado ou selecionar um Tópico/Subtópico do PDF abaixo!
                  </div>
                ) : (
                  <div className="space-y-2.5 max-h-[360px] overflow-y-auto pr-1">
                    {conceptsHierarchy.presented_concepts_from_errors.map((pc, idx) => (
                      <div
                        key={idx}
                        onClick={() => prefillFromPresentedConcept(pc)}
                        className="p-3.5 rounded-xl bg-slate-950/90 hover:bg-indigo-950/40 border border-slate-800 hover:border-indigo-500/40 transition cursor-pointer space-y-1.5"
                      >
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="font-bold text-rose-300">{pc.suggested_subtopic}</span>
                          <span className="px-2 py-0.5 rounded bg-violet-500/20 text-violet-300">
                            {pc.trap_type}
                          </span>
                        </div>
                        <p className="text-xs text-slate-200 line-clamp-3">
                          <strong>Conceito Apresentado:</strong> "{pc.presented_concept_context}"
                        </p>
                        <div className="text-[11px] text-indigo-400 font-semibold flex items-center gap-1">
                          <span>Selecionar este conceito e indicar Tópico/Subtópico</span>
                          <ChevronRight className="w-3.5 h-3.5" />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Quick selector from PDF Topics & Subtopics */}
                {conceptsHierarchy &&
                  conceptsHierarchy.available_topics_and_subtopics.length > 0 && (
                    <div className="pt-3 border-t border-slate-800 space-y-2">
                      <label className="block text-xs font-semibold text-slate-300">
                        Ou escolha rápido um Tópico / Subtópico do seu PDF Armazenado:
                      </label>
                      <select
                        onChange={(e) => {
                          const idx = Number(e.target.value);
                          const opt = conceptsHierarchy.available_topics_and_subtopics[idx];
                          if (opt) {
                            setSrMaterialId(opt.material_id);
                            setSrSubject(opt.subject);
                            setSrTopic(opt.topic);
                            setSrSubtopic(opt.subtopic);
                          }
                        }}
                        defaultValue=""
                        className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                      >
                        <option value="" disabled>
                          -- Selecionar Tópico e Subtópico do PDF --
                        </option>
                        {conceptsHierarchy.available_topics_and_subtopics.map((opt, i) => (
                          <option key={i} value={i}>
                            [{opt.subject}] {opt.topic} ➔ {opt.subtopic}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
              </div>

              {/* Right Column (7 cols): Form to Write Error Summary & Map Topic -> Subtopic -> Concept -> Subconcept */}
              <form
                onSubmit={handleSaveErrorSummaryNote}
                className="lg:col-span-7 bg-slate-900/80 border border-indigo-500/40 rounded-2xl p-6 space-y-4"
              >
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <NotebookPen className="w-5 h-5 text-emerald-400" />
                    <span>
                      2. Escrever Resumo da Resposta Errada & Relacionar Tópico/Subtópico/Conceito
                    </span>
                  </h3>
                  <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-semibold">
                    Salva no Banco (+3 Dias)
                  </span>
                </div>

                {/* Presented Concept Box */}
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5">
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-indigo-300">
                    Conceito Base Apresentado (do Erro / PDF):
                  </label>
                  <textarea
                    rows={2}
                    value={srPresentedContext}
                    onChange={(e) => setSrPresentedContext(e.target.value)}
                    placeholder="Conceito da questão que você errou..."
                    className="w-full bg-transparent text-xs text-slate-200 focus:outline-none"
                  />
                </div>

                {/* 4-Level Concept Hierarchy Inputs: Tópico -> Subtópico -> Conceito -> Subconceito */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      1º Nível: Tópico Principal <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={srTopic}
                      onChange={(e) => setSrTopic(e.target.value)}
                      placeholder="Ex: 1. Atos Administrativos"
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs sm:text-sm text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      2º Nível: Subtópico <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={srSubtopic}
                      onChange={(e) => setSrSubtopic(e.target.value)}
                      placeholder="Ex: 1.1. Extinção: Anulação e Revogação"
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs sm:text-sm text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      3º Nível: Conceito <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={srConcept}
                      onChange={(e) => setSrConcept(e.target.value)}
                      placeholder="Ex: Competência Privativa para Revogação"
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs sm:text-sm text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">
                      4º Nível: Subconceito / Especificidade
                    </label>
                    <input
                      type="text"
                      value={srSubconcept}
                      onChange={(e) => setSrSubconcept(e.target.value)}
                      placeholder="Ex: Vedação ao Judiciário revogar ato de outro Poder"
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs sm:text-sm text-white"
                    />
                  </div>
                </div>

                {/* Student's Written Summary & Notes */}
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-200 mb-1">
                      Seu Resumo da Resposta que Errou (Explique com suas palavras o conceito correto):{' '}
                      <span className="text-rose-400">*</span>
                    </label>
                    <textarea
                      rows={3}
                      required
                      value={srStudentSummary}
                      onChange={(e) => setSrStudentSummary(e.target.value)}
                      placeholder="Escreva aqui o seu resumo do erro: por que você errou e qual é a regra correta que deve lembrar daqui a 3 dias..."
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3.5 py-2.5 text-sm text-white focus:border-indigo-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-400 mb-1">
                      Anotações Extras / Gatilho de Prova / Mnemônico (Opcional):
                    </label>
                    <input
                      type="text"
                      value={srPersonalNotes}
                      onChange={(e) => setSrPersonalNotes(e.target.value)}
                      placeholder="Ex: Cuidado! Judiciário SÓ ANULA (ex tunc), NUNCA REVOGA ato de outro Poder!"
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3.5 py-2 text-xs sm:text-sm text-white"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={savingSummaryNote}
                  className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-emerald-600 hover:from-indigo-500 hover:to-emerald-500 text-white font-bold text-sm shadow-lg flex items-center justify-center gap-2 transition cursor-pointer"
                >
                  {savingSummaryNote ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Salvando no Banco e Criando Relacionamentos...</span>
                    </>
                  ) : (
                    <>
                      <NotebookPen className="w-4 h-4" />
                      <span>
                        Salvar Resumo de Erro no Banco & Agendar Revisão (De 3 em 3 Dias)
                      </span>
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* Section 3: Concept Relationships Graph (Tópico -> Subtópico -> Conceito -> Subconceito) */}
            {conceptsHierarchy && conceptsHierarchy.concept_relationships.length > 0 && (
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <GitBranch className="w-5 h-5 text-violet-400" />
                    <span>
                      Mapa de Relacionamentos Criados (Tópico ➔ Subtópico ➔ Conceito ➔ Subconceito)
                    </span>
                  </h3>
                  <span className="text-xs text-slate-400">
                    Gere +10 questões diretamente de qualquer relacionamento conceitual
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {conceptsHierarchy.concept_relationships.map((rel) => (
                    <div
                      key={rel.id}
                      className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between gap-3 hover:border-violet-500/40 transition"
                    >
                      <div className="space-y-1.5">
                        <div className="flex flex-wrap items-center gap-1.5 text-xs">
                          <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-semibold">
                            {rel.topic}
                          </span>
                          <span className="text-slate-500">➔</span>
                          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 font-semibold">
                            {rel.subtopic}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs pt-0.5">
                          <span className="text-slate-500">↳ Conceito:</span>
                          <span className="font-bold text-emerald-300">{rel.concept}</span>
                          {rel.subconcept && (
                            <>
                              <span className="text-slate-500">➔ Subconceito:</span>
                              <span className="font-semibold text-amber-300">
                                {rel.subconcept}
                              </span>
                            </>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 text-xs">
                        <span className="text-slate-400">
                          {rel.summary_ids.length} resumo(s) • {rel.generated_questions_count}{' '}
                          questões já geradas
                        </span>
                        <button
                          onClick={() =>
                            handleTrigger3DayReview({ relationshipLinkId: rel.id })
                          }
                          disabled={triggering3DayReview}
                          className="px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white font-bold flex items-center gap-1.5 cursor-pointer"
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Gerar +10 Questões deste Conceito</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Section 4: Saved Overview of Student Error Summaries & 3-Day Schedule */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <CalendarClock className="w-5 h-5 text-amber-400" />
                  <span>
                    Overview Salvo no Banco: Meus Resumos de Respostas Erradas (
                    {spacedOverview?.items.length || 0})
                  </span>
                </h3>
                <span className="text-xs text-slate-400">
                  Ciclo programado de 3 em 3 dias (+10 questões por ciclo)
                </span>
              </div>

              {!spacedOverview || spacedOverview.items.length === 0 ? (
                <div className="p-8 text-center bg-slate-950/60 rounded-xl border border-slate-800 text-slate-400 text-xs sm:text-sm">
                  Nenhum resumo de erro salvo ainda. Preencha o quadro acima para criar seu primeiro resumo e iniciar o ciclo de revisão de 3 em 3 dias!
                </div>
              ) : (
                <div className="space-y-3">
                  {spacedOverview.items.map((item) => (
                    <div
                      key={item.id}
                      className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2.5"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                        <span className="font-bold text-indigo-300">{item.hierarchy_path}</span>
                        <div className="flex items-center gap-2">
                          <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold">
                            Degrau Atual: {item.review_interval_days || 3} dias (3➔7➔15➔30d)
                          </span>
                          <span className="px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300">
                            Ciclos concluídos: {item.review_cycle_count}
                          </span>
                          <span
                            className={`px-2.5 py-0.5 rounded-full font-bold ${
                              item.is_due_for_3day_review
                                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            }`}
                          >
                            {item.is_due_for_3day_review
                              ? 'Revisão de 3 Dias Vencida — Revisar Agora!'
                              : `Próxima revisão em ${item.days_until_review} dia(s) (${new Date(
                                  item.next_review_at
                                ).toLocaleDateString('pt-BR')})`}
                          </span>
                        </div>
                      </div>

                      <div className="p-3 rounded-lg bg-slate-900 border-l-4 border-emerald-500 text-xs sm:text-sm text-white">
                        <strong>Meu Resumo:</strong> {item.student_summary}
                      </div>

                      {item.personal_notes && (
                        <p className="text-xs text-amber-300">
                          <strong>Minha Anotação / Bizu:</strong> {item.personal_notes}
                        </p>
                      )}

                      <div className="flex items-center justify-between pt-1 text-xs">
                        <span className="text-slate-500">
                          Salvo em: {new Date(item.created_at).toLocaleDateString('pt-BR')}
                        </span>
                        <button
                          onClick={() => handleTrigger3DayReview({ summaryIds: [item.id] })}
                          disabled={triggering3DayReview}
                          className="px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 border border-indigo-500/40 text-indigo-200 font-semibold cursor-pointer"
                        >
                          Revisar Este Resumo Agora (+10 Questões)
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 5: CONECTORES DE DADOS (FS LOCAL, REDE, GOOGLE DRIVE, DROPBOX E NUVEM)
           =================================================================== */}
        {activeTab === 'connectors' && (
          <div className="space-y-6">
            {/* Banner Explicativo */}
            <div className="rounded-2xl bg-gradient-to-r from-indigo-950/90 via-slate-900 to-sky-950/80 border border-indigo-500/40 p-6 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
              <div className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider bg-sky-500/20 text-sky-300 border border-sky-500/40">
                    Ingestão Automática Multi-Formato
                  </span>
                  <span className="text-xs text-slate-300 font-mono">
                    PDF • JSON • CSV • XML • TXT • MD
                  </span>
                </div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <Cloud className="w-6 h-6 text-sky-400" />
                  <span>
                    Conexões File System Local (Downloads, Documentos, Rede) & Nuvem (Google Drive / Dropbox)
                  </span>
                </h2>
                <p className="text-xs sm:text-sm text-slate-300 max-w-4xl">
                  Conecte pastas locais do computador, diretórios de rede SMB/UNC ou contas de nuvem (Google Drive e Dropbox com cadastro de chaves). Ao sincronizar, o banco descobre, rastreia por hash SHA-256, relaciona os conceitos (`Tópico ➔ Subtópico ➔ Conceito ➔ Subconceito`) e apresenta as questões Cebraspe ao aluno!
                </p>
              </div>
            </div>

            {/* SELETOR DE MÚLTIPLAS PASTAS PARA USUÁRIOS LEIGOS E AVANÇADOS */}
            <div className="rounded-2xl bg-slate-900/95 border border-emerald-500/40 p-5 space-y-4 shadow-xl">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                      Novo • Escolha 1 ou Várias Pastas
                    </span>
                    <h3 className="text-base font-bold text-white">
                      Estudo Multi-Pasta: Selecione Múltiplas Pastas com Seus Arquivos de Estudo
                    </h3>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    Escolha quantas pastas quiser no seu computador (ex: uma pasta com PDFs de Direito, outra com resumos em Documentos e outra em Downloads). O sistema elimina arquivos repetidos automaticamente e cria um Caderno Unificado!
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <label className="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 shadow cursor-pointer">
                    {syncingBrowserFolder ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Upload className="w-4 h-4" />
                    )}
                    <span>
                      {syncingBrowserFolder
                        ? 'Sincronizando Pasta com Banco Local...'
                        : '+ Selecionar Pasta pelo Navegador (GitHub Pages / Local)'}
                    </span>
                    <input
                      type="file"
                      multiple
                      // @ts-expect-error webkitdirectory is supported across Chromium/Firefox/Safari browsers
                      webkitdirectory="true"
                      directory="true"
                      onChange={handleBrowserDirectoryUpload}
                      className="hidden"
                    />
                  </label>

                  <button
                    type="button"
                    onClick={handlePickNativeFolder}
                    className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5 shadow cursor-pointer"
                  >
                    <FolderSearch className="w-4 h-4" />
                    <span>+ Escolher Pasta na Janela do Windows</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      if (showFolderBrowser) {
                        setShowFolderBrowser(false);
                      } else {
                        handleBrowseFolder(folderBrowser?.current_path);
                      }
                    }}
                    className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
                  >
                    <HardDrive className="w-4 h-4 text-indigo-400" />
                    <span>{showFolderBrowser ? 'Fechar Navegador Visual' : 'Navegar Pastas na Tela'}</span>
                  </button>
                </div>
              </div>

              {/* Atalhos Rápidos para Adicionar Múltiplas Pastas com 1 Clique */}
              {providersInfo && providersInfo.default_local_directories.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-bold uppercase text-slate-400">
                    Adicionar Rápido à Seleção:
                  </span>
                  {providersInfo.default_local_directories.map((dir, idx) => {
                    const alreadyAdded = selectedMultiFolders.includes(dir.path);
                    return (
                      <button
                        key={idx}
                        type="button"
                        onClick={() =>
                          alreadyAdded
                            ? removePathFromMultiSelection(dir.path)
                            : addPathToMultiSelection(dir.path)
                        }
                        className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                          alreadyAdded
                            ? 'bg-emerald-600/30 border-emerald-400 text-emerald-200'
                            : 'bg-slate-950 hover:bg-slate-800 border-slate-800 text-slate-300'
                        }`}
                      >
                        {alreadyAdded ? `✓ ${dir.label} (Selecionada)` : `+ ${dir.label}`}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Navegador Visual de Pastas (para escolher clicando sem digitar caminhos) */}
              {showFolderBrowser && folderBrowser && (
                <div className="p-4 rounded-xl bg-slate-950 border border-indigo-500/40 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-xs font-mono text-indigo-300 break-all">
                      📂 Pasta Atual: <strong>{folderBrowser.current_path}</strong> ({folderBrowser.study_files_count} arquivo(s) de estudo aqui)
                    </div>
                    <div className="flex items-center gap-2">
                      {folderBrowser.parent_path && (
                        <button
                          type="button"
                          onClick={() => handleBrowseFolder(folderBrowser.parent_path!)}
                          className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 cursor-pointer"
                        >
                          ⬆ Subir para Pasta Pai
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => addPathToMultiSelection(folderBrowser.current_path)}
                        className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold cursor-pointer"
                      >
                        + Incluir Esta Pasta na Seleção
                      </button>
                    </div>
                  </div>

                  {folderBrowser.subfolders.length > 0 && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 max-h-48 overflow-y-auto pt-2 border-t border-slate-900">
                      {folderBrowser.subfolders.map((sf, idx) => {
                        const isPicked = selectedMultiFolders.includes(sf.path);
                        return (
                          <div
                            key={idx}
                            className="flex items-center justify-between gap-1 p-2 rounded-lg bg-slate-900/90 border border-slate-800 text-xs"
                          >
                            <button
                              type="button"
                              onClick={() => handleBrowseFolder(sf.path)}
                              className="text-left text-slate-200 hover:text-indigo-300 truncate flex-1 font-medium cursor-pointer"
                              title={`Abrir ${sf.path}`}
                            >
                              📁 {sf.name}
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                isPicked
                                  ? removePathFromMultiSelection(sf.path)
                                  : addPathToMultiSelection(sf.path)
                              }
                              className={`px-2 py-0.5 rounded text-[10px] font-bold cursor-pointer ${
                                isPicked
                                  ? 'bg-emerald-600 text-white'
                                  : 'bg-indigo-600/30 hover:bg-indigo-600 text-indigo-200 hover:text-white'
                              }`}
                            >
                              {isPicked ? '✓ Incluída' : '+ Incluir'}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Lista de Pastas Selecionadas + Botão de Escanear Conjunto */}
              <form onSubmit={handleScanSelectedMultiFolders} className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] font-bold uppercase text-slate-400 mb-1">
                      Nome do Conjunto de Pastas
                    </label>
                    <input
                      type="text"
                      value={multiWorkspaceName}
                      onChange={(e) => setMultiWorkspaceName(e.target.value)}
                      placeholder="Ex: Edital Polícia Federal (3 Pastas)"
                      className="w-full rounded-xl bg-slate-950 border border-slate-800 px-3 py-2 text-xs text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold uppercase text-slate-400 mb-1">
                      Disciplina / Foco Geral
                    </label>
                    <input
                      type="text"
                      value={multiSubjectHint}
                      onChange={(e) => setMultiSubjectHint(e.target.value)}
                      placeholder="Ex: Direito & Informática"
                      className="w-full rounded-xl bg-slate-950 border border-slate-800 px-3 py-2 text-xs text-white"
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      type="submit"
                      disabled={scanningMultiFolders || selectedMultiFolders.length === 0}
                      className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-40 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg cursor-pointer"
                    >
                      {scanningMultiFolders ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Escaneando {selectedMultiFolders.length} Pasta(s) e Gerando Questões...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-4 h-4" />
                          <span>
                            Escanear {selectedMultiFolders.length || ''} Pasta(s) Selecionada(s) & Gerar Caderno Unificado
                          </span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {selectedMultiFolders.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <span className="text-[11px] font-semibold text-emerald-300">
                      Pastas selecionadas ({selectedMultiFolders.length}):
                    </span>
                    {selectedMultiFolders.map((p, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-1 rounded-lg bg-slate-950 border border-emerald-500/40 text-xs text-slate-200 font-mono flex items-center gap-2"
                      >
                        <span>{p}</span>
                        <button
                          type="button"
                          onClick={() => removePathFromMultiSelection(p)}
                          className="text-rose-400 hover:text-rose-300 font-bold cursor-pointer"
                          title="Remover pasta da seleção"
                        >
                          ✕
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </form>

              {/* Conjuntos de Múltiplas Pastas Já Salvos */}
              {multiWorkspacesList.length > 0 && (
                <div className="pt-3 border-t border-slate-800 space-y-2">
                  <div className="text-xs font-bold text-slate-300">
                    Conjuntos de Múltiplas Pastas Salvos ({multiWorkspacesList.length}):
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {multiWorkspacesList.map((ws) => (
                      <div
                        key={ws.id}
                        className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between gap-2"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h4 className="text-xs font-bold text-white">
                              {ws.name} ({ws.folders_count} pasta(s) • {ws.total_files_found} arquivo(s) único(s))
                            </h4>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {ws.folders.map((f, i) => (
                                <span
                                  key={i}
                                  className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] text-slate-300 font-mono"
                                  title={f.path}
                                >
                                  📁 {f.label}
                                </span>
                              ))}
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleDeleteMultiWorkspace(ws.id)}
                            className="text-slate-500 hover:text-rose-400 p-1 cursor-pointer"
                            title="Excluir conjunto"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>

                        <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-900">
                          {ws.unified_battery_id && (
                            <button
                              type="button"
                              onClick={async () => {
                                const full = await fetchBattery(ws.unified_battery_id!);
                                setCurrentBattery(full);
                                setSimuladoFinished(false);
                                setSubtopicFilter('ALL');
                                setActiveTab('solver');
                              }}
                              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold flex items-center gap-1 cursor-pointer"
                            >
                              <Play className="w-3 h-3" />
                              <span>Abrir Caderno Unificado</span>
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleResyncMultiWorkspace(ws.id)}
                            disabled={scanningMultiFolders}
                            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-bold flex items-center gap-1 cursor-pointer"
                          >
                            <RefreshCw className="w-3 h-3" />
                            <span>Ressincronizar Todas as Pastas</span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Coluna Esquerda: Cadastro de Conexão & Atalhos Locais */}
              <div className="lg:col-span-5 space-y-4">
                <form
                  onSubmit={handleSaveConnection}
                  className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 space-y-4"
                >
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div className="flex items-center gap-2">
                      <HardDrive className="w-5 h-5 text-indigo-400" />
                      <h3 className="text-sm font-bold text-white">
                        Nova Conexão de Dados (Local / Rede / Nuvem)
                      </h3>
                    </div>
                  </div>

                  {/* Atalhos Rápidos para Downloads / Documentos / Desktop */}
                  {providersInfo && providersInfo.default_local_directories.length > 0 && (
                    <div className="space-y-1.5">
                      <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Atalhos Rápidos do seu Sistema (1 Clique):
                      </label>
                      <div className="flex flex-wrap gap-1.5">
                        {providersInfo.default_local_directories.map((dir, i) => (
                          <button
                            key={i}
                            type="button"
                            onClick={() => {
                              setConnProviderType('local_fs');
                              setConnName(dir.label);
                              setConnTargetPath(dir.path);
                            }}
                            className="px-2.5 py-1.5 rounded-lg bg-slate-950 hover:bg-indigo-950/60 border border-slate-800 hover:border-indigo-500/50 text-xs text-slate-200 flex items-center gap-1.5 cursor-pointer"
                          >
                            <FolderSearch className="w-3.5 h-3.5 text-indigo-400" />
                            <span>{dir.label}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-bold uppercase text-slate-300 mb-1">
                        Provedor de Armazenamento
                      </label>
                      <select
                        value={connProviderType}
                        onChange={(e) => setConnProviderType(e.target.value)}
                        className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                      >
                        <option value="local_fs">File System Local (Downloads / Documentos)</option>
                        <option value="network_share">Pasta de Rede (SMB / UNC / Drive Mapeado)</option>
                        <option value="google_drive">Google Drive (API Key / OAuth Token)</option>
                        <option value="dropbox">Dropbox (Access Token / App Key)</option>
                        <option value="cloud_custom">Nuvem Customizada (OneDrive / S3 / WebDAV)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] font-bold uppercase text-slate-300 mb-1">
                        Nome da Conexão
                      </label>
                      <input
                        type="text"
                        value={connName}
                        onChange={(e) => setConnName(e.target.value)}
                        placeholder="Ex: Meus PDFs em Downloads"
                        className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-[11px] font-bold uppercase text-slate-300 mb-1">
                      {connProviderType === 'google_drive'
                        ? 'Google Drive Folder ID (ou Caminho Local do Drive)'
                        : connProviderType === 'dropbox'
                        ? 'Caminho da Pasta no Dropbox (ex: /Estudos_Cebraspe)'
                        : connProviderType === 'network_share'
                        ? 'Caminho de Rede UNC ou Drive Mapeado (ex: \\\\servidor\\estudos)'
                        : 'Caminho da Pasta Local (ex: C:\\Users\\...\\Downloads)'}
                    </label>
                    <input
                      type="text"
                      value={connTargetPath}
                      onChange={(e) => setConnTargetPath(e.target.value)}
                      placeholder={
                        connProviderType === 'google_drive'
                          ? '1AbCdEfGhIjKlMnOpQrStUvWxYz ou G:\\Meu Drive\\Concursos'
                          : connProviderType === 'dropbox'
                          ? '/Concursos/Cebraspe'
                          : 'C:\\Users\\julio\\Downloads'
                      }
                      className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white font-mono"
                    />
                  </div>

                  {/* Campos de Chaves de API / Tokens para Nuvem (Google Drive / Dropbox / Cloud) */}
                  {['google_drive', 'dropbox', 'cloud_custom'].includes(connProviderType) && (
                    <div className="p-3.5 rounded-xl bg-slate-950/90 border border-indigo-500/30 space-y-3">
                      <div className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                        <KeyRound className="w-3.5 h-3.5" />
                        <span>Credenciais e Chaves da Nuvem (Cadastradas pelo Usuário)</span>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        <div>
                          <label className="block text-[10px] font-semibold uppercase text-slate-400 mb-1">
                            API Key (Google Drive / Cloud)
                          </label>
                          <input
                            type="password"
                            value={connApiKey}
                            onChange={(e) => setConnApiKey(e.target.value)}
                            placeholder="AIzaSy..."
                            className="w-full rounded-lg bg-slate-900 border border-slate-700 px-2.5 py-1.5 text-xs text-white"
                          />
                        </div>

                        <div>
                          <label className="block text-[10px] font-semibold uppercase text-slate-400 mb-1">
                            Access Token OAuth2 / Bearer (Drive / Dropbox)
                          </label>
                          <input
                            type="password"
                            value={connAccessToken}
                            onChange={(e) => setConnAccessToken(e.target.value)}
                            placeholder="ya29... ou sl.B..."
                            className="w-full rounded-lg bg-slate-900 border border-slate-700 px-2.5 py-1.5 text-xs text-white"
                          />
                        </div>

                        {connProviderType === 'dropbox' && (
                          <>
                            <div>
                              <label className="block text-[10px] font-semibold uppercase text-slate-400 mb-1">
                                Dropbox App Key (Opcional)
                              </label>
                              <input
                                type="text"
                                value={connAppKey}
                                onChange={(e) => setConnAppKey(e.target.value)}
                                placeholder="App Key"
                                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-2.5 py-1.5 text-xs text-white"
                              />
                            </div>
                            <div>
                              <label className="block text-[10px] font-semibold uppercase text-slate-400 mb-1">
                                Dropbox App Secret (Opcional)
                              </label>
                              <input
                                type="password"
                                value={connAppSecret}
                                onChange={(e) => setConnAppSecret(e.target.value)}
                                placeholder="App Secret"
                                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-2.5 py-1.5 text-xs text-white"
                              />
                            </div>
                          </>
                        )}
                      </div>

                      <div>
                        <label className="block text-[10px] font-semibold uppercase text-slate-400 mb-1">
                          Pasta Espelho de Sincronização Local (Opcional — para modo offline/híbrido)
                        </label>
                        <input
                          type="text"
                          value={connMirrorPath}
                          onChange={(e) => setConnMirrorPath(e.target.value)}
                          placeholder="Ex: C:\Users\julio\Google Drive\Estudos"
                          className="w-full rounded-lg bg-slate-900 border border-slate-700 px-2.5 py-1.5 text-xs text-white font-mono"
                        />
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-bold uppercase text-slate-300 mb-1">
                        Disciplina Padrão dos Arquivos
                      </label>
                      <input
                        type="text"
                        value={connSubjectHint}
                        onChange={(e) => setConnSubjectHint(e.target.value)}
                        placeholder="Ex: Direito Constitucional"
                        className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-bold uppercase text-slate-300 mb-1">
                        Área do Concurso
                      </label>
                      <select
                        value={connAreaHint}
                        onChange={(e) => setConnAreaHint(e.target.value)}
                        className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                      >
                        {AREAS.map((a) => (
                          <option key={a} value={a}>
                            {a}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={connAutoGenerate}
                      onChange={(e) => setConnAutoGenerate(e.target.checked)}
                      className="rounded border-slate-700 bg-slate-950 text-indigo-600"
                    />
                    <span>
                      Ao conectar/sincronizar, indexar relacionamentos e já gerar bateria de questões Cebraspe automaticamente
                    </span>
                  </label>

                  <button
                    type="submit"
                    disabled={savingConnection}
                    className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-sky-600 hover:from-indigo-500 hover:to-sky-500 text-white font-bold text-xs sm:text-sm flex items-center justify-center gap-2 shadow-lg cursor-pointer"
                  >
                    {savingConnection ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Conectando, Rastreando e Gerando Questões...</span>
                      </>
                    ) : (
                      <>
                        <Cloud className="w-4 h-4" />
                        <span>Salvar Conexão & Buscar Arquivos de Estudo</span>
                      </>
                    )}
                  </button>
                </form>

                {/* Lista de Conexões Ativas */}
                <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 space-y-3">
                  <h3 className="text-sm font-bold text-white flex items-center justify-between">
                    <span>Conexões Cadastradas ({connectionsList.length})</span>
                  </h3>

                  {connectionsList.length === 0 ? (
                    <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-400">
                      Nenhuma conexão cadastrada ainda. Use um dos atalhos acima (Downloads / Documentos) ou cadastre Google Drive / Dropbox.
                    </div>
                  ) : (
                    <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
                      {connectionsList.map((c) => (
                        <div
                          key={c.id}
                          className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 text-[10px] font-bold uppercase">
                                {c.provider_type}
                              </span>
                              <h4 className="text-xs font-bold text-white mt-1">{c.name}</h4>
                              <p className="text-[11px] text-slate-400 font-mono truncate max-w-xs">
                                {c.target_path_or_folder_id}
                              </p>
                            </div>
                            <button
                              onClick={() => handleDeleteConnection(c.id)}
                              className="text-slate-500 hover:text-rose-400 p-1 cursor-pointer"
                              title="Remover conexão"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>

                          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800/80 text-[11px] text-slate-400">
                            <span>
                              {c.discovered_files_count || 0} arquivo(s) •{' '}
                              {c.files_with_questions_count || 0} com questões
                            </span>
                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={() => handleScanConnection(c.id, true)}
                                disabled={scanningConnId === c.id}
                                className="px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-[11px] flex items-center gap-1 cursor-pointer"
                              >
                                {scanningConnId === c.id ? (
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                ) : (
                                  <RefreshCw className="w-3 h-3" />
                                )}
                                <span>Sincronizar & Gerar Questões</span>
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Coluna Direita: Arquivos Encontrados, Rastreados, Relacionados e Apresentação de Questões */}
              <div className="lg:col-span-7 space-y-4">
                <div className="rounded-2xl bg-slate-900/90 border border-slate-800 p-5 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                    <div>
                      <h3 className="text-base font-bold text-white flex items-center gap-2">
                        <FolderSearch className="w-5 h-5 text-emerald-400" />
                        <span>
                          Arquivos de Estudo Rastreados no Banco ({discoveredFilesList.length})
                        </span>
                      </h3>
                      <p className="text-xs text-slate-400">
                        Arquivos descobertos nas conexões (PDF, JSON, CSV, XML, TXT, MD), com relacionamentos conceituais e baterias de questões prontas para estudo.
                      </p>
                    </div>
                  </div>

                  {discoveredFilesList.length === 0 ? (
                    <div className="p-8 text-center rounded-xl bg-slate-950/60 border border-slate-800 text-slate-400 text-xs space-y-2">
                      <p className="font-semibold text-slate-300">
                        Nenhum arquivo rastreado ainda.
                      </p>
                      <p>
                        Clique em um dos atalhos à esquerda (ex: <strong>Downloads</strong> ou <strong>Documentos</strong>) e clique em <strong>"Salvar Conexão & Buscar Arquivos de Estudo"</strong> para localizar seus arquivos e gerar questões!
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3 max-h-[640px] overflow-y-auto pr-1">
                      {discoveredFilesList.map((df) => (
                        <div
                          key={df.id}
                          className="p-4 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 space-y-3"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div className="space-y-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 text-[10px] font-extrabold uppercase">
                                  {df.file_ext.replace('.', '')}
                                </span>
                                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-semibold">
                                  {df.provider_type}
                                </span>
                                <span
                                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    df.status === 'questions_generated'
                                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                      : 'bg-amber-500/20 text-amber-300'
                                  }`}
                                >
                                  {df.status === 'questions_generated'
                                    ? `✓ ${df.extracted_questions_count} Questões Prontas`
                                    : 'Descoberto (Aguardando Geração)'}
                                </span>
                              </div>
                              <h4 className="text-sm font-bold text-white">{df.file_name}</h4>
                              <p className="text-[11px] text-slate-500 font-mono break-all">
                                {df.file_path_or_remote_id} • {(df.file_size / 1024).toFixed(1)} KB • SHA-256: {df.sha256_hash.slice(0, 12)}...
                              </p>
                            </div>

                            <div className="flex items-center gap-2">
                              {df.battery_id ? (
                                <button
                                  onClick={async () => {
                                    const full = await fetchBattery(df.battery_id!);
                                    setCurrentBattery(full);
                                    setSimuladoFinished(false);
                                    setSubtopicFilter('ALL');
                                    setActiveTab('solver');
                                  }}
                                  className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md cursor-pointer"
                                >
                                  <Play className="w-3.5 h-3.5" />
                                  <span>Apresentar & Resolver Questões</span>
                                </button>
                              ) : null}

                              <button
                                onClick={() => handleIngestSingleFile(df.id)}
                                disabled={ingestingFileId === df.id}
                                className="px-3 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                              >
                                {ingestingFileId === df.id ? (
                                  <>
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    <span>Gerando...</span>
                                  </>
                                ) : (
                                  <>
                                    <Sparkles className="w-3.5 h-3.5" />
                                    <span>{df.battery_id ? '+10 Novas Questões' : 'Importar & Gerar Questões'}</span>
                                  </>
                                )}
                              </button>
                            </div>
                          </div>

                          {/* Relacionamentos extraídos do arquivo */}
                          {df.related_topics && df.related_topics.length > 0 && (
                            <div className="pt-2 border-t border-slate-900 space-y-1.5">
                              <div className="text-[11px] font-semibold text-indigo-300 flex items-center gap-1">
                                <GitBranch className="w-3 h-3" />
                                <span>Relacionamentos Conceituais Extraídos (`Tópico ➔ Subtópico ➔ Conceito`):</span>
                              </div>
                              <div className="flex flex-wrap gap-1.5">
                                {df.related_topics.slice(0, 4).map((rt, idx) => (
                                  <span
                                    key={idx}
                                    className="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800 text-[11px] text-slate-300"
                                  >
                                    {rt.topic} ➔ <strong className="text-indigo-300">{rt.subtopic}</strong> ➔ {rt.concept}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 6: CADERNO DE ERROS, ESTATÍSTICAS DE ARMADILHAS & REFORÇO IA
           =================================================================== */}
        {activeTab === 'errors' && (
          <div className="space-y-6">
            <div className="rounded-2xl bg-slate-900/80 border border-slate-800 p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <ShieldAlert className="w-6 h-6 text-rose-400" />
                  <span>Caderno de Erros, Favoritas & Diagnóstico de Pegadinhas</span>
                </h2>
                <p className="text-sm text-slate-400 mt-1">
                  Veja em quais subtópicos e em quais tipos de pegadinhas da Cebraspe você mais perde pontos líquidos.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => setActiveTab('spaced')}
                  className="px-3.5 py-2 rounded-xl bg-indigo-500/20 border border-indigo-500/40 text-indigo-200 text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                >
                  <CalendarClock className="w-4 h-4" />
                  <span>Resumir Erros (Revisão 3 em 3 Dias)</span>
                </button>

                <button
                  onClick={() => setOnlyFavoritesFilter((v) => !v)}
                  className={`px-3.5 py-2 rounded-xl border text-xs font-semibold flex items-center gap-1.5 cursor-pointer ${
                    onlyFavoritesFilter
                      ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                      : 'bg-slate-950 border-slate-800 text-slate-300'
                  }`}
                >
                  <Star className="w-4 h-4" />
                  <span>{onlyFavoritesFilter ? 'Mostrando Só Favoritas' : 'Erros + Favoritas'}</span>
                </button>

                <button
                  onClick={handleReinforceFromErrors}
                  disabled={reinforcingErrors || !errorNotebook?.items.length}
                  className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-rose-600 to-indigo-600 hover:from-rose-500 hover:to-indigo-500 disabled:opacity-40 text-white text-xs sm:text-sm font-bold flex items-center gap-2 shadow-lg cursor-pointer"
                >
                  {reinforcingErrors ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Gerando Variações...</span>
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      <span>Gerar Bateria de Reforço dos Meus Erros (2x)</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="space-y-4">
              {!errorNotebook || errorNotebook.items.length === 0 ? (
                <div className="text-center py-12 bg-slate-900/40 rounded-2xl border border-slate-800 text-slate-400 text-sm">
                  Nenhum item errado ou favoritado até o momento.
                </div>
              ) : (
                errorNotebook.items.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 space-y-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-semibold">
                          {item.subject}
                        </span>
                        <span className="px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300">
                          {item.subtopic}
                        </span>
                        <span className="px-2.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300">
                          {item.trap_type}
                        </span>
                      </div>
                      <button
                        onClick={() => openErrorSummaryNoteFromAssertion(item)}
                        className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold flex items-center gap-1 cursor-pointer"
                      >
                        <NotebookPen className="w-3.5 h-3.5" />
                        <span>Resumir p/ Revisão 3 em 3 Dias</span>
                      </button>
                    </div>

                    <p className="text-sm sm:text-base text-white font-medium">{item.statement}</p>

                    <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs space-y-1.5">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-bold px-2 py-0.5 rounded ${
                            item.answer === 'C'
                              ? 'bg-emerald-500/20 text-emerald-300'
                              : 'bg-rose-500/20 text-rose-300'
                          }`}
                        >
                          Gabarito Oficial: {item.answer === 'C' ? 'CERTO' : 'ERRADO'}
                        </span>
                      </div>
                      <p className="text-slate-300 leading-relaxed">{item.explanation}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ===================================================================
            TAB 6: BANCO DE PDFS ARMAZENADOS (SQL+NoSQL) & BATERIAS SALVAS
           =================================================================== */}
        {activeTab === 'history' && (
          <div className="space-y-8">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <Database className="w-5 h-5 text-emerald-400" />
                  <span>Arquivos PDF Armazenados no Cofre Híbrido (SQL + NoSQL)</span>
                </h2>
                <span className="text-xs text-slate-400">
                  {storedPdfsList.length} arquivo(s) persistido(s)
                </span>
              </div>

              {storedPdfsList.length === 0 ? (
                <div className="p-8 text-center bg-slate-900/40 rounded-2xl border border-slate-800 text-slate-400 text-sm">
                  Nenhum arquivo PDF binário enviado ainda.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {storedPdfsList.map((f) => {
                    const fid = f.id || f.file_id || 0;
                    return (
                      <div
                        key={fid}
                        className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-col justify-between gap-3"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center justify-between text-[11px] text-slate-400">
                            <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 font-semibold">
                              {f.file_role === 'study_pdf' ? 'PDF de Estudo' : 'Caderno Cebraspe'}
                            </span>
                            <span>{(f.file_size / 1024).toFixed(1)} KB</span>
                          </div>
                          <h4 className="font-bold text-sm text-white truncate" title={f.filename}>
                            {f.filename}
                          </h4>
                          <p className="text-[11px] text-slate-500 font-mono truncate">
                            SHA-256: {f.sha256_hash.slice(0, 16)}...
                          </p>
                        </div>

                        <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-800 text-xs">
                          <a
                            href={getStoredFileDownloadUrl(fid)}
                            download
                            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 flex items-center gap-1 ml-auto"
                          >
                            <Download className="w-3.5 h-3.5" />
                            <span>Baixar PDF</span>
                          </a>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="space-y-4">
              <h2 className="text-xl font-bold text-white">
                Baterias de Assertivas Salvas no Banco Local ({batteriesList.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {batteriesList.map((bat) => (
                  <div
                    key={bat.id}
                    className="rounded-2xl bg-slate-900/80 border border-slate-800 p-5 flex flex-col justify-between gap-4"
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-2 text-xs text-indigo-300 font-semibold">
                        <span>
                          {bat.subject} • {bat.area}
                        </span>
                        <span className="text-slate-500">
                          {new Date(bat.created_at).toLocaleDateString('pt-BR')}
                        </span>
                      </div>
                      <h3 className="text-base font-bold text-white">{bat.title}</h3>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-800">
                      <button
                        onClick={async () => {
                          const full = await fetchBattery(bat.id);
                          setCurrentBattery(full);
                          setSimuladoFinished(false);
                          setActiveTab('solver');
                        }}
                        className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold cursor-pointer"
                      >
                        Abrir Bateria
                      </button>

                      <div className="flex items-center gap-2 text-xs">
                        <a
                          href={getExportUrl(bat.id, 'apkg', 'all')}
                          download
                          className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200"
                        >
                          .apkg
                        </a>
                        <a
                          href={getExportUrl(bat.id, 'pdf', 'all')}
                          download
                          className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200"
                        >
                          .pdf
                        </a>
                        <a
                          href={getExportUrl(bat.id, 'md', 'all')}
                          download
                          className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200"
                        >
                          .md
                        </a>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ===================================================================
          MODAL: CONFIGURAÇÃO DA API GOOGLE GEMINI
         =================================================================== */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center gap-2.5">
                <KeyRound className="w-5 h-5 text-indigo-400" />
                <h3 className="text-lg font-bold text-white">
                  Configurações da IA (Google Gemini API)
                </h3>
              </div>
              <button
                onClick={() => setShowSettingsModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveSettings} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Chave da API Google Gemini (GEMINI_API_KEY)
                </label>
                <input
                  type="password"
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  placeholder="AIzaSy..."
                  className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1.5">
                  Modelo Gemini
                </label>
                <select
                  value={modelInput}
                  onChange={(e) => setModelInput(e.target.value)}
                  className="w-full rounded-xl bg-slate-950 border border-slate-700 px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-indigo-500"
                >
                  {MODELS.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>

              {apiTestStatus && (
                <div
                  className={`p-3 rounded-xl text-xs border ${
                    apiTestStatus.ok
                      ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-200'
                      : 'bg-rose-950/60 border-rose-500/40 text-rose-200'
                  }`}
                >
                  {apiTestStatus.message}
                </div>
              )}

              <div className="flex items-center justify-between gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={handleTestApi}
                  disabled={testingApi}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 flex items-center gap-2 cursor-pointer"
                >
                  {testingApi && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Testar Conexão</span>
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowSettingsModal(false)}
                    className="px-4 py-2 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-400 cursor-pointer"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white cursor-pointer"
                  >
                    Salvar Configurações
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Ponte GitHub Pages <-> Banco Local no PC & Licença Comercial Hotmart */}
      {showBridgeModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-xl w-full p-6 space-y-5 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <HardDrive className="w-5 h-5 text-emerald-400" />
                <h3 className="text-base font-bold text-white">
                  Ponte Híbrida (GitHub Pages ➔ Banco Local no seu PC) & Licença
                </h3>
              </div>
              <button
                onClick={() => setShowBridgeModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 font-semibold">Status do Agente Local no PC:</span>
                <span
                  className={`px-2.5 py-0.5 rounded-full font-bold ${
                    bridgeOffline
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  }`}
                >
                  {bridgeOffline ? 'Offline (Inicie o Agente Local)' : 'Conectado ao seu PC (Online)'}
                </span>
              </div>

              {bridgeStatus && (
                <>
                  <div className="text-slate-300">
                    <strong>Sistema / Arquitetura:</strong> {bridgeStatus.pc_environment.os} (
                    {bridgeStatus.pc_environment.arch})
                  </div>
                  <div className="text-slate-300 break-all">
                    <strong>Banco SQL Local (SQLite):</strong>{' '}
                    <code className="text-indigo-300">{bridgeStatus.local_storage.sql_db_path}</code>
                  </div>
                  <div className="text-slate-300 break-all">
                    <strong>Banco NoSQL Local:</strong>{' '}
                    <code className="text-indigo-300">
                      {bridgeStatus.local_storage.nosql_store_path}
                    </code>
                  </div>
                  <div className="text-slate-300">
                    <strong>URL de Alto Nível (GitHub Pages):</strong>{' '}
                    <code className="text-emerald-300">{bridgeStatus.top_level_pages_url}</code>
                  </div>
                </>
              )}
            </div>

            <form onSubmit={handleSaveLocalBridgeServer} className="space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Endereço do Banco/Agente Local no Seu Computador
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={localServerInput}
                  onChange={(e) => setLocalServerInput(e.target.value)}
                  placeholder="http://127.0.0.1:8000"
                  className="flex-1 rounded-xl bg-slate-950 border border-slate-700 px-3.5 py-2 text-xs sm:text-sm text-white font-mono"
                />
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white cursor-pointer"
                >
                  Conectar
                </button>
              </div>
              <p className="text-[11px] text-slate-400">
                Mesmo usando a interface pela URL de alto nível do GitHub Pages, todos os seus PDFs, resumos, pastas locais e chaves de nuvem ficam salvos exclusivamente neste endereço local do seu computador.
              </p>
            </form>

            <form
              onSubmit={handleActivateLicense}
              className="pt-4 border-t border-slate-800 space-y-3"
            >
              <div className="flex items-center justify-between">
                <label className="block text-xs font-semibold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
                  <KeyRound className="w-3.5 h-3.5" />
                  <span>Licença do Aluno (Hotmart / Código de Transação)</span>
                </label>
                <span className="text-xs font-bold text-emerald-300">
                  {bridgeStatus?.license.plan || 'Edição Local Completa'}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <input
                  type="text"
                  value={licenseKeyInput}
                  onChange={(e) => setLicenseKeyInput(e.target.value)}
                  placeholder="Código Hotmart (ex: HP123456789)"
                  className="rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                />
                <input
                  type="email"
                  value={buyerEmailInput}
                  onChange={(e) => setBuyerEmailInput(e.target.value)}
                  placeholder="E-mail de compra (opcional)"
                  className="rounded-xl bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white"
                />
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[11px] text-slate-400">
                  {bridgeStatus?.license.is_activated
                    ? `Licença ativa (${bridgeStatus.license.license_key_masked})`
                    : 'Você pode registrar seu código HP da Hotmart para suporte e atualizações.'}
                </span>
                <button
                  type="submit"
                  disabled={activatingLicense}
                  className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white cursor-pointer"
                >
                  {activatingLicense ? 'Ativando...' : 'Ativar Código'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
