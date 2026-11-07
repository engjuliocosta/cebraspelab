import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from adaptive_tutor import (
    build_weakness_diagnosis_and_study_plan,
    generate_more_fixation_questions_from_stored_pdf,
    list_saved_discursive_responses,
    submit_and_save_discursive_5lines_answer,
)
from database import (
    get_battery,
    get_error_notebook,
    get_settings,
    get_study_material,
    init_db,
    list_batteries,
    list_study_materials,
    record_assertion_answer,
    save_question_battery,
    save_study_material,
    update_material_recurrence,
    update_settings,
)
from exporters import (
    export_to_anki_apkg,
    export_to_anki_csv,
    export_to_markdown,
    export_to_pdf_bytes,
)
from gemini_service import (
    analyze_pdf_recurrence,
    generate_cebraspe_assertions,
    generate_error_reinforcement,
    test_gemini_connection,
)
from pdf_processor import (
    extract_pdf_pages,
    extract_questions_heuristic,
    parse_extra_questions_file,
)
from storage_manager import (
    get_material_knowledge_tree_nosql,
    get_stored_file_With_bytes,
    init_storage_tables,
    list_stored_files,
    save_material_knowledge_tree_nosql,
    store_uploaded_file,
)
from spaced_review import (
    create_student_error_summary_note,
    evaluate_spaced_review_cycle_and_adapt_intervals,
    generate_contrastive_concept_battle_battery,
    get_available_concepts_and_hierarchy,
    init_spaced_review_tables,
    list_contrastive_concept_pairs,
    list_student_error_summaries_overview,
    queue_doubt_assertion_to_3day_review,
    trigger_3day_spaced_review_and_generate_10_questions,
)
from data_connectors import (
    PROVIDER_TYPES,
    SUPPORTED_STUDY_EXTENSIONS,
    create_or_update_connection,
    delete_connection,
    get_default_local_directories,
    ingest_and_generate_questions_from_discovered_file,
    init_connectors_tables,
    list_connections,
    list_discovered_files,
    sync_connection_and_build_questions,
)
from multi_folder_workspace import (
    add_folders_to_workspace,
    browse_local_folders,
    create_or_update_multi_folder_workspace,
    delete_multi_folder_workspace,
    init_multi_folder_tables,
    list_available_drives_and_quick_folders,
    list_multi_folder_workspaces,
    pick_folder_native_dialog,
    remove_folder_from_workspace,
    scan_and_sync_multiple_folders,
)
from topic_parser import (
    extract_assertions_from_subtopics,
    parse_pdf_topics_and_subtopics,
)
from local_bridge import (
    activate_product_license,
    build_bridge_status,
    compute_pna_cors_headers,
    get_license_status,
    ingest_browser_selected_files_batch,
)

load_dotenv()
init_db()
init_storage_tables()
init_spaced_review_tables()
init_connectors_tables()
init_multi_folder_tables()

app = FastAPI(
    title="Gerador de Assertivas Cebraspe API",
    description="Motor híbrido SQL+NoSQL de armazenamento de PDFs, análise de recorrência Cebraspe, geração por períodos e mentoria adaptativa com discursiva de 5 linhas",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def github_pages_private_network_bridge_middleware(request: Request, call_next):
    """
    Suporte completo a W3C Private Network Access (CORS-RFC1918 / Chrome PNA) para permitir que
    a interface hospedada em domínio de alto nível no GitHub Pages (HTTPS) se conecte ao banco
    SQL+NoSQL local no PC do usuário (`http://127.0.0.1:8000`).
    """
    origin = request.headers.get("origin")
    req_pna = request.headers.get("access-control-request-private-network")
    pna_headers = compute_pna_cors_headers(origin=origin, request_pna=req_pna)

    if request.method == "OPTIONS":
        return Response(status_code=204, headers=pna_headers)

    response = await call_next(request)
    for k, v in pna_headers.items():
        response.headers[k] = v
    return response


class SettingsUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    default_area: Optional[str] = None
    default_depth: Optional[str] = None


class TestGeminiRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = "gemini-2.5-flash"


class GenerateBatteryRequest(BaseModel):
    material_id: int
    title: str
    subject: str
    area: str = "Geral"
    depth: str = "Misto Padrão Cebraspe"
    subtopic_plan: List[Dict[str, Any]]


class AnswerAssertionRequest(BaseModel):
    user_answer: Optional[str] = None
    is_favorite: Optional[bool] = None
    annotations: Optional[List[Dict[str, Any]]] = None
    answered_with_doubt: Optional[bool] = None


class EvaluateAdaptiveIntervalRequest(BaseModel):
    cycle_id: Optional[int] = None
    battery_id: Optional[int] = None


class QueueDoubtAssertionRequest(BaseModel):
    assertion_id: int
    student_doubt_note: str = ""


class GenerateContrastiveBattleRequest(BaseModel):
    pair_id: Optional[str] = None
    questions_count: int = 8


class ReinforceErrorsRequest(BaseModel):
    assertion_ids: Optional[List[int]] = None
    subject: Optional[str] = None
    questions_per_error: int = 2


class ExtractPeriodsRequest(BaseModel):
    variations_per_period: int = 2
    title: Optional[str] = None
    subject: Optional[str] = None
    area: Optional[str] = None


class GenerateFixationFromPdfRequest(BaseModel):
    material_id: int
    target_subtopic: Optional[str] = None
    variations_per_period: int = 3


class SubmitDiscursiveAnswerRequest(BaseModel):
    question_id: int
    student_text: str


class CreateErrorSummaryNoteRequest(BaseModel):
    material_id: Optional[int] = None
    assertion_id: Optional[int] = None
    subject: str = "Direito Administrativo"
    topic: str
    subtopic: str
    concept: str
    subconcept: str = ""
    presented_concept_context: str = ""
    student_summary: str
    personal_notes: str = ""
    trap_type: str = "Conceito / Regra"
    pdf_page: str = "p. 1"
    review_interval_days: int = 3


class TriggerSpacedReviewRequest(BaseModel):
    summary_ids: Optional[List[int]] = None
    relationship_link_id: Optional[int] = None
    questions_count: int = 10
    force_all_if_none_due: bool = True


class UpsertStorageConnectionRequest(BaseModel):
    connection_id: Optional[int] = None
    name: str
    provider_type: str = "local_fs"
    target_path_or_folder_id: str
    subject_hint: str = "Multidisciplinar"
    area_hint: str = "Geral"
    api_key: str = ""
    access_token: str = ""
    app_key: str = ""
    app_secret: str = ""
    endpoint_url: str = ""
    local_sync_mirror_path: str = ""
    recursive_scan: bool = True
    auto_generate_questions: bool = True


class ScanStorageConnectionRequest(BaseModel):
    auto_ingest_and_generate: Optional[bool] = None
    questions_per_file: int = 8
    max_files_to_ingest: int = 10


class IngestDiscoveredFileRequest(BaseModel):
    questions_count: int = 10


class UpsertMultiFolderWorkspaceRequest(BaseModel):
    workspace_id: Optional[int] = None
    name: str
    folders: List[Any]
    subject_hint: str = "Multidisciplinar"
    area_hint: str = "Geral"
    recursive_scan: bool = True
    auto_generate_questions: bool = True


class ModifyWorkspaceFoldersRequest(BaseModel):
    folders: Optional[List[Any]] = None
    folder_path_to_remove: Optional[str] = None


class ScanMultipleFoldersRequest(BaseModel):
    workspace_id: Optional[int] = None
    folders: Optional[List[Any]] = None
    workspace_name: str = "Minhas Pastas de Estudo"
    subject_hint: str = "Multidisciplinar"
    area_hint: str = "Geral"
    questions_per_file: int = 6
    create_unified_battery: bool = True


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "has_api_key": bool(settings.get("gemini_api_key", "").strip()),
        "model": settings.get("gemini_model", "gemini-2.5-flash"),
    }


@app.get("/api/settings")
def read_settings() -> Dict[str, Any]:
    s = get_settings()
    raw_key = s.get("gemini_api_key", "")
    masked = ""
    if raw_key:
        masked = raw_key[:6] + "..." + raw_key[-4:] if len(raw_key) > 10 else "***"
    return {
        "gemini_api_key": raw_key,
        "masked_api_key": masked,
        "has_api_key": bool(raw_key.strip()),
        "gemini_model": s.get("gemini_model", "gemini-2.5-flash"),
        "default_area": s.get("default_area", "Geral"),
        "default_depth": s.get("default_depth", "Misto Padrão Cebraspe"),
    }


@app.post("/api/settings")
def save_settings_endpoint(payload: SettingsUpdateRequest) -> Dict[str, Any]:
    update_settings(payload.model_dump(exclude_none=True))
    return read_settings()


@app.post("/api/settings/test-gemini")
def test_gemini_endpoint(payload: TestGeminiRequest) -> Dict[str, Any]:
    settings = get_settings()
    key = payload.gemini_api_key if payload.gemini_api_key is not None else settings.get("gemini_api_key", "")
    model = payload.gemini_model or settings.get("gemini_model", "gemini-2.5-flash")
    return test_gemini_connection(key, model)


@app.post("/api/materials/analyze")
async def analyze_materials_endpoint(
    study_pdfs: List[UploadFile] = File(..., description="PDFs do material de estudo / teoria"),
    question_files: Optional[List[UploadFile]] = File(default=None, description="PDFs/JSONs opcionais de cadernos de questões Cebraspe"),
    area: str = Form("Geral"),
    subject_hint: str = Form(""),
) -> Dict[str, Any]:
    all_pages: List[Dict[str, Any]] = []
    raw_uploaded_study: List[Dict[str, Any]] = []
    raw_uploaded_questions: List[Dict[str, Any]] = []

    for pdf_file in study_pdfs:
        content = await pdf_file.read()
        if not content:
            continue
        fname = pdf_file.filename or "documento.pdf"
        raw_uploaded_study.append(
            {
                "bytes": content,
                "filename": fname,
                "mime_type": pdf_file.content_type or "application/pdf",
            }
        )
        if fname.lower().endswith(".pdf"):
            extracted = extract_pdf_pages(content, fname)
            all_pages.extend(extracted)
        else:
            text_str = content.decode("utf-8", errors="ignore")
            all_pages.append(
                {
                    "page_number": len(all_pages) + 1,
                    "text": text_str,
                    "source_file": fname,
                }
            )

    if not all_pages:
        raise HTTPException(status_code=400, detail="Não foi possível extrair texto dos arquivos enviados.")

    for idx, p in enumerate(all_pages, start=1):
        p["page_number"] = idx

    detected_questions = extract_questions_heuristic(all_pages)

    if question_files:
        for qf in question_files:
            q_bytes = await qf.read()
            if q_bytes and qf.filename:
                raw_uploaded_questions.append(
                    {
                        "bytes": q_bytes,
                        "filename": qf.filename,
                        "mime_type": qf.content_type or "application/octet-stream",
                    }
                )
                extra_q = parse_extra_questions_file(q_bytes, qf.filename)
                detected_questions.extend(extra_q)

    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")

    analysis = analyze_pdf_recurrence(
        pages=all_pages,
        heuristic_questions=detected_questions,
        area=area,
        api_key=api_key,
        model_name=model_name,
        custom_subject_hint=subject_hint,
    )

    subject = analysis.get("detected_subject") or subject_hint or "Disciplina Geral"
    title = analysis.get("detected_title") or (study_pdfs[0].filename or "Material de Estudo")
    subtopics = analysis.get("subtopics", [])

    material_id = save_study_material(
        title=title,
        subject=subject,
        area=area,
        total_pages=len(all_pages),
        pages=all_pages,
        extracted_questions=detected_questions,
        recurrence_map=subtopics,
    )

    # Persistir arquivos binários no banco SQL + Vault físico
    stored_file_records: List[Dict[str, Any]] = []
    for uf in raw_uploaded_study:
        rec = store_uploaded_file(
            file_bytes=uf["bytes"],
            filename=uf["filename"],
            material_id=material_id,
            file_role="study_pdf",
            mime_type=uf["mime_type"],
        )
        stored_file_records.append(rec)

    for qf_rec in raw_uploaded_questions:
        rec = store_uploaded_file(
            file_bytes=qf_rec["bytes"],
            filename=qf_rec["filename"],
            material_id=material_id,
            file_role="question_bank",
            mime_type=qf_rec["mime_type"],
        )
        stored_file_records.append(rec)

    parsed_topics = analysis.get("parsed_topics") or parse_pdf_topics_and_subtopics(all_pages)
    total_periods = sum(t.get("periods_count", len(t.get("periods", []))) for t in parsed_topics)

    # Persistir árvore hierárquica de tópicos, subtópicos e períodos no banco NoSQL
    save_material_knowledge_tree_nosql(
        material_id=material_id,
        title=title,
        subject=subject,
        area=area,
        parsed_topics=parsed_topics,
        recurrence_map=subtopics,
        stored_file_ids=[r["file_id"] for r in stored_file_records],
    )

    return {
        "material_id": material_id,
        "title": title,
        "subject": subject,
        "area": area,
        "total_pages": len(all_pages),
        "total_periods": total_periods,
        "real_questions_count": max(len(detected_questions), int(analysis.get("total_real_questions_detected", 0))),
        "analysis_summary": analysis.get("analysis_summary", ""),
        "subtopics": subtopics,
        "parsed_topics": parsed_topics,
        "stored_files": stored_file_records,
        "sample_real_questions": detected_questions[:15],
    }


@app.get("/api/materials")
def list_materials_endpoint() -> List[Dict[str, Any]]:
    mats = list_study_materials()
    for m in mats:
        m["stored_files"] = list_stored_files(material_id=m["id"])
    return mats


@app.get("/api/materials/{material_id}")
def get_material_endpoint(material_id: int) -> Dict[str, Any]:
    mat = get_study_material(material_id)
    if not mat:
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    mat["stored_files"] = list_stored_files(material_id=material_id)
    mat["nosql_tree"] = get_material_knowledge_tree_nosql(material_id)
    return mat


@app.get("/api/storage/files")
def list_all_stored_files_endpoint(material_id: Optional[int] = Query(default=None)) -> List[Dict[str, Any]]:
    return list_stored_files(material_id=material_id)


@app.get("/api/storage/files/{file_id}/download")
def download_stored_file_endpoint(file_id: int) -> Response:
    rec = get_stored_file_With_bytes(file_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Arquivo armazenado não encontrado.")
    return Response(
        content=rec["bytes"],
        media_type=rec.get("mime_type", "application/pdf"),
        headers={"Content-Disposition": f'attachment; filename="{rec["filename"]}"'},
    )


@app.post("/api/materials/{material_id}/extract-period-assertions")
def extract_period_assertions_endpoint(
    material_id: int,
    payload: ExtractPeriodsRequest,
) -> Dict[str, Any]:
    mat = get_study_material(material_id)
    if not mat:
        raise HTTPException(status_code=404, detail="Material de estudo não encontrado.")

    pages = mat.get("pages", [])
    structured_topics = parse_pdf_topics_and_subtopics(pages)
    if not structured_topics:
        raise HTTPException(status_code=400, detail="Nenhum período válido encontrado para extração.")

    subject = payload.subject or mat.get("subject", "Disciplina")
    area = payload.area or mat.get("area", "Geral")
    variations = max(1, min(3, payload.variations_per_period))
    title = payload.title or f"{mat.get('title', 'Material')} — Extração Completa por Períodos ({variations}x)"

    assertions = extract_assertions_from_subtopics(
        structured_topics=structured_topics,
        subject=subject,
        area=area,
        questions_per_subtopic=None,
        variations_per_period=variations,
    )

    battery_id = save_question_battery(
        material_id=material_id,
        title=title,
        subject=subject,
        area=area,
        depth=f"Extração Intensiva de Períodos ({variations}x por período)",
        recurrence_summary=mat.get("recurrence_map", []),
        assertions=assertions,
    )
    return get_battery(battery_id)


@app.post("/api/batteries/generate")
def generate_battery_endpoint(payload: GenerateBatteryRequest) -> Dict[str, Any]:
    mat = get_study_material(payload.material_id)
    if not mat:
        raise HTTPException(status_code=404, detail="Material de estudo não encontrado.")

    update_material_recurrence(payload.material_id, payload.subtopic_plan)

    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")

    assertions = generate_cebraspe_assertions(
        pages=mat["pages"],
        real_questions=mat.get("extracted_questions", []),
        subtopic_plan=payload.subtopic_plan,
        subject=payload.subject,
        title=payload.title,
        area=payload.area,
        depth=payload.depth,
        api_key=api_key,
        model_name=model_name,
    )

    battery_id = save_question_battery(
        material_id=payload.material_id,
        title=payload.title,
        subject=payload.subject,
        area=payload.area,
        depth=payload.depth,
        recurrence_summary=payload.subtopic_plan,
        assertions=assertions,
    )

    return get_battery(battery_id)


@app.get("/api/batteries")
def get_all_batteries() -> List[Dict[str, Any]]:
    return list_batteries()


@app.get("/api/batteries/{battery_id}")
def get_single_battery(battery_id: int) -> Dict[str, Any]:
    battery = get_battery(battery_id)
    if not battery:
        raise HTTPException(status_code=404, detail="Bateria de questões não encontrada.")
    return battery


@app.post("/api/assertions/{assertion_id}/answer")
def answer_assertion_endpoint(assertion_id: int, payload: AnswerAssertionRequest) -> Dict[str, Any]:
    updated = record_assertion_answer(
        assertion_id=assertion_id,
        user_answer=payload.user_answer,
        is_favorite=payload.is_favorite,
        annotations=payload.annotations,
        answered_with_doubt=payload.answered_with_doubt,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Assertiva não encontrada.")
    return updated


@app.get("/api/errors")
def get_errors_endpoint(
    subject: Optional[str] = Query(default=None),
    only_favorites: bool = Query(default=False),
) -> Dict[str, Any]:
    return get_error_notebook(subject=subject, only_favorites=only_favorites)


@app.post("/api/errors/reinforce")
def reinforce_errors_endpoint(payload: ReinforceErrorsRequest) -> Dict[str, Any]:
    err_data = get_error_notebook(subject=payload.subject)
    items = err_data.get("items", [])
    if payload.assertion_ids:
        id_set = set(payload.assertion_ids)
        items = [i for i in items if i["id"] in id_set]

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Nenhum item errado ou favoritado encontrado para gerar reforço.",
        )

    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")

    new_assertions = generate_error_reinforcement(
        wrong_assertions=items,
        api_key=api_key,
        model_name=model_name,
        questions_per_error=payload.questions_per_error,
    )

    subject = payload.subject or items[0].get("subject", "Revisão Inteligente")
    title = f"Caderno de Reforço de Erros ({len(new_assertions)} itens)"

    battery_id = save_question_battery(
        material_id=items[0].get("material_id"),
        title=title,
        subject=subject,
        area=items[0].get("area", "Geral"),
        depth="Reforço Focado em Armadilhas",
        recurrence_summary=[],
        assertions=new_assertions,
    )
    return get_battery(battery_id)


# ===========================================================================
# ROTAS DE MENTORIA ADAPTATIVA, RESUMO DO PDF E DISCURSIVA DE 5 LINHAS
# ===========================================================================

@app.get("/api/tutor/diagnosis")
def tutor_diagnosis_endpoint(
    material_id: Optional[int] = Query(default=None),
) -> Dict[str, Any]:
    return build_weakness_diagnosis_and_study_plan(material_id=material_id)


@app.post("/api/tutor/generate-fixation")
def tutor_generate_fixation_endpoint(
    payload: GenerateFixationFromPdfRequest,
) -> Dict[str, Any]:
    try:
        return generate_more_fixation_questions_from_stored_pdf(
            material_id=payload.material_id,
            target_subtopic=payload.target_subtopic,
            variations_per_period=payload.variations_per_period,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/tutor/discursive/submit")
def tutor_submit_discursive_endpoint(
    payload: SubmitDiscursiveAnswerRequest,
) -> Dict[str, Any]:
    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")
    try:
        return submit_and_save_discursive_5lines_answer(
            question_id=payload.question_id,
            student_text=payload.student_text,
            api_key=api_key,
            model_name=model_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tutor/discursive/history")
def tutor_discursive_history_endpoint(
    material_id: Optional[int] = Query(default=None),
) -> List[Dict[str, Any]]:
    return list_saved_discursive_responses(material_id=material_id)


# ===========================================================================
# ROTAS DE RESUMO DE ERROS DO ALUNO, HIERARQUIA DE CONCEITOS E REVISÃO DE 3 EM 3 DIAS
# ===========================================================================

@app.get("/api/spaced-review/concepts-hierarchy")
def spaced_review_concepts_hierarchy_endpoint(
    material_id: Optional[int] = Query(default=None),
) -> Dict[str, Any]:
    return get_available_concepts_and_hierarchy(material_id=material_id)


@app.post("/api/spaced-review/summaries")
def create_spaced_review_summary_endpoint(
    payload: CreateErrorSummaryNoteRequest,
) -> Dict[str, Any]:
    try:
        return create_student_error_summary_note(
            topic=payload.topic,
            subtopic=payload.subtopic,
            concept=payload.concept,
            subconcept=payload.subconcept,
            student_summary=payload.student_summary,
            personal_notes=payload.personal_notes,
            presented_concept_context=payload.presented_concept_context,
            subject=payload.subject,
            material_id=payload.material_id,
            assertion_id=payload.assertion_id,
            trap_type=payload.trap_type,
            pdf_page=payload.pdf_page,
            review_interval_days=payload.review_interval_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/spaced-review/overview")
def spaced_review_overview_endpoint(
    material_id: Optional[int] = Query(default=None),
    only_due: bool = Query(default=False),
) -> Dict[str, Any]:
    return list_student_error_summaries_overview(
        material_id=material_id,
        only_due=only_due,
    )


@app.post("/api/spaced-review/trigger")
def trigger_spaced_review_endpoint(
    payload: TriggerSpacedReviewRequest,
) -> Dict[str, Any]:
    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")
    try:
        return trigger_3day_spaced_review_and_generate_10_questions(
            summary_ids=payload.summary_ids,
            relationship_link_id=payload.relationship_link_id,
            questions_count=payload.questions_count,
            force_all_if_none_due=payload.force_all_if_none_due,
            api_key=api_key,
            model_name=model_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/spaced-review/evaluate-adaptive")
def evaluate_adaptive_interval_endpoint(
    payload: EvaluateAdaptiveIntervalRequest,
) -> Dict[str, Any]:
    try:
        return evaluate_spaced_review_cycle_and_adapt_intervals(
            cycle_id=payload.cycle_id,
            battery_id=payload.battery_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/spaced-review/queue-doubt")
def queue_doubt_assertion_endpoint(
    payload: QueueDoubtAssertionRequest,
) -> Dict[str, Any]:
    try:
        return queue_doubt_assertion_to_3day_review(
            assertion_id=payload.assertion_id,
            student_doubt_note=payload.student_doubt_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/spaced-review/contrastive-pairs")
def list_contrastive_pairs_endpoint() -> List[Dict[str, Any]]:
    return list_contrastive_concept_pairs()


@app.post("/api/spaced-review/contrastive-battle")
def generate_contrastive_battle_endpoint(
    payload: GenerateContrastiveBattleRequest,
) -> Dict[str, Any]:
    return generate_contrastive_concept_battle_battery(
        pair_id=payload.pair_id,
        questions_count=payload.questions_count,
    )


# ===========================================================================
# ROTAS DE CONECTORES DE DADOS (FS LOCAL, PASTAS DE REDE, GOOGLE DRIVE, DROPBOX E NUVEM)
# ===========================================================================

@app.get("/api/connectors/providers")
def list_connector_providers_endpoint() -> Dict[str, Any]:
    return {
        "providers": list(PROVIDER_TYPES.values()),
        "supported_extensions": sorted(list(SUPPORTED_STUDY_EXTENSIONS)),
        "default_local_directories": get_default_local_directories(),
    }


@app.get("/api/connectors")
def list_storage_connections_endpoint() -> List[Dict[str, Any]]:
    return list_connections()


@app.post("/api/connectors")
def save_storage_connection_endpoint(
    payload: UpsertStorageConnectionRequest,
) -> Dict[str, Any]:
    try:
        return create_or_update_connection(
            connection_id=payload.connection_id,
            name=payload.name,
            provider_type=payload.provider_type,
            target_path_or_folder_id=payload.target_path_or_folder_id,
            subject_hint=payload.subject_hint,
            area_hint=payload.area_hint,
            api_key=payload.api_key,
            access_token=payload.access_token,
            app_key=payload.app_key,
            app_secret=payload.app_secret,
            endpoint_url=payload.endpoint_url,
            local_sync_mirror_path=payload.local_sync_mirror_path,
            recursive_scan=payload.recursive_scan,
            auto_generate_questions=payload.auto_generate_questions,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/connectors/{connection_id}")
def delete_storage_connection_endpoint(connection_id: int) -> Dict[str, Any]:
    deleted = delete_connection(connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return {"deleted": True, "connection_id": connection_id}


@app.post("/api/connectors/{connection_id}/scan")
def scan_and_sync_connection_endpoint(
    connection_id: int,
    payload: ScanStorageConnectionRequest,
) -> Dict[str, Any]:
    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")
    try:
        return sync_connection_and_build_questions(
            connection_id=connection_id,
            auto_ingest_and_generate=payload.auto_ingest_and_generate,
            questions_per_file=payload.questions_per_file,
            max_files_to_ingest=payload.max_files_to_ingest,
            api_key=api_key,
            model_name=model_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/connectors/files")
def list_discovered_files_endpoint(
    connection_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
) -> List[Dict[str, Any]]:
    return list_discovered_files(connection_id=connection_id, status=status)


@app.post("/api/connectors/files/{discovered_file_id}/ingest")
def ingest_discovered_file_endpoint(
    discovered_file_id: int,
    payload: IngestDiscoveredFileRequest,
) -> Dict[str, Any]:
    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")
    try:
        return ingest_and_generate_questions_from_discovered_file(
            discovered_file_id=discovered_file_id,
            questions_count=payload.questions_count,
            api_key=api_key,
            model_name=model_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===========================================================================
# ROTAS DE MÚLTIPLAS PASTAS DE ESTUDO (NAVEGADOR VISUAL, WORKSPACES E SCAN UNIFICADO)
# ===========================================================================

@app.get("/api/multi-folders/drives-and-quick")
def multi_folders_drives_endpoint() -> Dict[str, Any]:
    return list_available_drives_and_quick_folders()


@app.get("/api/multi-folders/browse")
def multi_folders_browse_endpoint(
    path: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    try:
        return browse_local_folders(current_path=path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/multi-folders/pick-native")
def multi_folders_pick_native_endpoint(
    initial_dir: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    return pick_folder_native_dialog(initial_dir=initial_dir)


@app.get("/api/multi-folders/workspaces")
def list_multi_folder_workspaces_endpoint() -> List[Dict[str, Any]]:
    return list_multi_folder_workspaces()


@app.post("/api/multi-folders/workspaces")
def save_multi_folder_workspace_endpoint(
    payload: UpsertMultiFolderWorkspaceRequest,
) -> Dict[str, Any]:
    try:
        return create_or_update_multi_folder_workspace(
            workspace_id=payload.workspace_id,
            name=payload.name,
            folders=payload.folders,
            subject_hint=payload.subject_hint,
            area_hint=payload.area_hint,
            recursive_scan=payload.recursive_scan,
            auto_generate_questions=payload.auto_generate_questions,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/multi-folders/workspaces/{workspace_id}/add-folders")
def add_folders_to_workspace_endpoint(
    workspace_id: int,
    payload: ModifyWorkspaceFoldersRequest,
) -> Dict[str, Any]:
    try:
        return add_folders_to_workspace(
            workspace_id=workspace_id,
            new_folders=payload.folders or [],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/multi-folders/workspaces/{workspace_id}/remove-folder")
def remove_folder_from_workspace_endpoint(
    workspace_id: int,
    payload: ModifyWorkspaceFoldersRequest,
) -> Dict[str, Any]:
    try:
        return remove_folder_from_workspace(
            workspace_id=workspace_id,
            folder_path_to_remove=payload.folder_path_to_remove or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/multi-folders/workspaces/{workspace_id}")
def delete_multi_folder_workspace_endpoint(workspace_id: int) -> Dict[str, Any]:
    deleted = delete_multi_folder_workspace(workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conjunto de pastas não encontrado.")
    return {"deleted": True, "workspace_id": workspace_id}


@app.post("/api/multi-folders/scan")
def scan_multiple_folders_endpoint(
    payload: ScanMultipleFoldersRequest,
) -> Dict[str, Any]:
    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")
    try:
        return scan_and_sync_multiple_folders(
            workspace_id=payload.workspace_id,
            folders=payload.folders,
            workspace_name=payload.workspace_name,
            subject_hint=payload.subject_hint,
            area_hint=payload.area_hint,
            questions_per_file=payload.questions_per_file,
            create_unified_battery=payload.create_unified_battery,
            api_key=api_key,
            model_name=model_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ActivateLicenseRequest(BaseModel):
    license_key: str
    buyer_email: str = ""
    custom_pages_url: Optional[str] = None


@app.get("/api/bridge/status")
def bridge_status_endpoint(request: Request = None) -> Dict[str, Any]:
    origin = request.headers.get("origin") if request is not None and hasattr(request, "headers") else None
    return build_bridge_status(request_origin=origin)


@app.post("/api/bridge/activate-license")
def activate_license_endpoint(payload: ActivateLicenseRequest) -> Dict[str, Any]:
    try:
        return activate_product_license(
            license_key=payload.license_key,
            buyer_email=payload.buyer_email,
            custom_pages_url=payload.custom_pages_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/bridge/ingest-browser-folder")
async def ingest_browser_folder_endpoint(
    files: List[UploadFile] = File(...),
    folder_label: str = Form("Pasta Selecionada no Navegador"),
    subject_hint: str = Form("Multidisciplinar"),
    area_hint: str = Form("Tribunais / Jurídico"),
    questions_per_file: int = Form(6),
) -> Dict[str, Any]:
    files_payload: List[Dict[str, Any]] = []
    for f in files:
        raw_bytes = await f.read()
        files_payload.append(
            {
                "filename": f.filename or "arquivo.txt",
                "content_bytes": raw_bytes,
            }
        )
    try:
        return ingest_browser_selected_files_batch(
            files_payload=files_payload,
            folder_label=folder_label,
            subject_hint=subject_hint,
            area_hint=area_hint,
            questions_per_file=questions_per_file,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/batteries/{battery_id}/export/{fmt}")
def export_battery_endpoint(
    battery_id: int,
    fmt: str,
    filter_mode: str = Query(default="all"),
) -> Response:
    battery = get_battery(battery_id)
    if not battery:
        raise HTTPException(status_code=404, detail="Bateria não encontrada.")

    safe_name = f"cebraspe_bateria_{battery_id}_{filter_mode}"
    fmt_lower = fmt.lower()

    if fmt_lower == "apkg":
        apkg_bytes = export_to_anki_apkg(battery, filter_mode=filter_mode)
        return Response(
            content=apkg_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.apkg"'},
        )
    if fmt_lower == "csv":
        csv_text = export_to_anki_csv(battery, filter_mode=filter_mode)
        return Response(
            content=csv_text.encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_anki.csv"'},
        )
    if fmt_lower == "pdf":
        pdf_bytes = export_to_pdf_bytes(battery, filter_mode=filter_mode)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
        )
    if fmt_lower in ("md", "markdown"):
        md_text = export_to_markdown(battery, filter_mode=filter_mode)
        return Response(
            content=md_text.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
        )

    raise HTTPException(status_code=400, detail=f"Formato de exportação inválido: {fmt}")


@app.post("/api/batteries/generate-demo")
def create_demo_battery() -> Dict[str, Any]:
    demo_subtopics = [
        {
            "topic": "1. Extinção dos Atos Administrativos",
            "subtopic": "Extinção dos Atos: Anulação, Revogação e Cassação",
            "recurrence_level": "Muito Alta",
            "recurrence_percentage": 36,
            "real_questions_found": 18,
            "periods_count": 4,
            "min_recommended_questions": 8,
            "pages_reference": "p. 14-22",
            "cebraspe_focus_points": [
                "Inversão entre anulação (ilegalidade, efeitos ex tunc, Administração ou Judiciário) e revogação (mérito, efeitos ex nunc, exclusiva da Administração)",
                "Atos irrevogáveis: atos vinculados, consumados, que geram direito adquirido e meros atos administrativos",
                "Prazo decadencial de 5 anos (art. 54 da Lei 9.784/1999) salvo comprovada má-fé",
            ],
        },
        {
            "topic": "2. Atributos e Requisitos",
            "subtopic": "Atributos do Ato Administrativo (PATI)",
            "recurrence_level": "Muito Alta",
            "recurrence_percentage": 28,
            "real_questions_found": 14,
            "periods_count": 3,
            "min_recommended_questions": 6,
            "pages_reference": "p. 7-13",
            "cebraspe_focus_points": [
                "Presunção de legitimidade/veracidade é relativa (juris tantum) e está presente em todos os atos",
                "Autoexecutoriedade não está presente em todos os atos: exige previsão legal expressa ou urgência",
            ],
        },
        {
            "topic": "2. Atributos e Requisitos",
            "subtopic": "Elementos / Requisitos de Validade e Convalidação (COFIFOMOOB)",
            "recurrence_level": "Alta",
            "recurrence_percentage": 24,
            "real_questions_found": 11,
            "periods_count": 3,
            "min_recommended_questions": 5,
            "pages_reference": "p. 1-6",
            "cebraspe_focus_points": [
                "Competência e Forma admitem convalidação (vícios sanáveis), desde que não seja competência exclusiva nem forma essencial à validade",
                "Teoria dos Motivos Determinantes: mesmo quando o ato não exige motivação, se for motivado, a validade fica vinculada à veracidade dos motivos",
            ],
        },
        {
            "topic": "3. Classificação dos Atos",
            "subtopic": "Classificação dos Atos (Simples, Composto e Complexo)",
            "recurrence_level": "Média",
            "recurrence_percentage": 12,
            "real_questions_found": 6,
            "periods_count": 2,
            "min_recommended_questions": 3,
            "pages_reference": "p. 23-28",
            "cebraspe_focus_points": [
                "Distinção entre ato complexo (conjugação de vontades autônomas de órgãos diversos) e ato composto (vontade principal + ato acessório/ratificador)",
            ],
        },
    ]

    demo_pages = [
        {
            "page_number": 1,
            "source_file": "atos_administrativos_demo.pdf",
            "text": (
                "1. EXTINÇÃO DOS ATOS ADMINISTRATIVOS\n"
                "1.1. Extinção dos Atos: Anulação, Revogação e Cassação\n"
                "A revogação funda-se no juízo de conveniência e oportunidade (mérito), sendo privativa da Administração Pública que praticou o ato; o Poder Judiciário jamais revoga ato administrativo no exercício da função jurisdicional.\n"
                "Não admitem revogação os atos vinculados, os atos consumados, os meros atos administrativos e os atos que geram direito adquirido.\n"
                "Enquanto a cassação decorre de descumprimento de requisitos pelo beneficiário, a caducidade advém de nova legislação que impede a permanência de situação anteriormente admitida.\n"
                "2. ATRIBUTOS E REQUISITOS DE VALIDADE\n"
                "2.1. Atributos do Ato Administrativo (PATI)\n"
                "Por ser uma presunção relativa (juris tantum), a presunção de legitimidade admite prova em contrário, operando a inversão do ônus da prova em desfavor do particular.\n"
                "A autoexecutoriedade não é atributo universal dos atos administrativos; no caso das multas, a imposição é autoexecutória, mas a execução forçada do pagamento depende da via judicial.\n"
                "2.2. Elementos / Requisitos de Validade e Convalidação (COFIFOMOOB)\n"
                "Em decisão na qual se evidencie não acarretarem lesão ao interesse público nem prejuízo a terceiros, os atos que apresentarem defeitos sanáveis de forma não essencial e competência não exclusiva poderão ser convalidados com efeitos ex tunc.\n"
                "Ainda que o ato administrativo dispense motivação por natureza, uma vez declarados os motivos pela autoridade, estes passam a vincular a validade do ato pela Teoria dos Motivos Determinantes.\n"
            ),
        }
    ]

    demo_assertions = [
        {
            "subtopic": "Extinção dos Atos: Anulação, Revogação e Cassação",
            "recurrence_level": "Muito Alta",
            "command_text": "Acerca da formação, dos atributos e da extinção dos atos administrativos, julgue os itens a seguir.",
            "statement": "Situação hipotética: O Poder Judiciário, provocado por particular lesado, constatou que determinado ato administrativo discricionário praticado pelo Poder Executivo mostrava-se flagrantemente inconveniente e inoportuno ao interesse público, embora respeitasse os limites legais. Assertiva: Nessa situação, em homenagem ao princípio da inafastabilidade da jurisdição, caberá ao Poder Judiciário revogar o referido ato administrativo, produzindo efeitos ex nunc.",
            "answer": "E",
            "explanation": "ITEM ERRADO. O Poder Judiciário NÃO pode revogar atos administrativos produzidos por outro Poder no exercício da função administrativa, pois o juízo de conveniência e oportunidade (mérito administrativo) é privativo da própria Administração que editou o ato. Ao Judiciário cabe apenas o controle de legalidade/legitimidade (anulação).",
            "pdf_quote": "A revogação funda-se no juízo de conveniência e oportunidade (mérito), sendo privativa da Administração Pública que praticou o ato; o Poder Judiciário jamais revoga ato administrativo no exercício da função jurisdicional.",
            "pdf_page": "p. 15",
            "trap_type": "Inversão de Conceito",
            "difficulty": "Média",
            "inspired_by_real_question": "Padrão Clássico CEBRASPE (Súmula 473 do STF — Controle Judicial vs. Mérito)",
        },
        {
            "subtopic": "Extinção dos Atos: Anulação, Revogação e Cassação",
            "recurrence_level": "Muito Alta",
            "command_text": "Acerca da formação, dos atributos e da extinção dos atos administrativos, julgue os itens a seguir.",
            "statement": "Os atos administrativos vinculados, assim como os atos que já exauriram seus efeitos (atos consumados) e aqueles que geraram direito adquirido, são insuscetíveis de revogação pela administração pública, embora possam ser objeto de anulação caso padeçam de vício de legalidade.",
            "answer": "C",
            "explanation": "ITEM CERTO. A revogação pressupõe juízo de mérito (conveniência e oportunidade), inexistente nos atos vinculados. Além disso, atos consumados e direitos adquiridos constituem limites materiais ao poder de revogar. Contudo, havendo ilegalidade, qualquer ato (vinculado ou discricionário) pode ser anulado.",
            "pdf_quote": "Não admitem revogação: os atos vinculados, os atos consumados, os meros atos administrativos (certidões, atestados), os atos que geram direito adquirido e os atos integrativos de procedimento após a preclusão.",
            "pdf_page": "p. 17",
            "trap_type": "Literalidade / Conceito Exato",
            "difficulty": "Média",
            "inspired_by_real_question": "Recorrência Muito Alta CEBRASPE — Atos Irrevogáveis",
        },
        {
            "subtopic": "Extinção dos Atos: Anulação, Revogação e Cassação",
            "recurrence_level": "Muito Alta",
            "command_text": "Acerca da formação, dos atributos e da extinção dos atos administrativos, julgue os itens a seguir.",
            "statement": "A cassação constitui modalidade de extinção do ato administrativo que ocorre quando sobrevém norma jurídica nova que torna inadmissível a situação antes permitida pelo direito na época da edição do ato.",
            "answer": "E",
            "explanation": "ITEM ERRADO. A definição trazida pelo item corresponde à CADUCIDADE (extinção por superveniência de norma jurídica incompatível). A CASSAÇÃO ocorre quando o próprio beneficiário descumpre as condições que deveria manter para continuar usufruindo do ato.",
            "pdf_quote": "Enquanto a cassação decorre de descumprimento de requisitos pelo beneficiário, a caducidade advém de nova legislação que impede a permanência de situação anteriormente admitida.",
            "pdf_page": "p. 20",
            "trap_type": "Inversão de Conceito",
            "difficulty": "Média",
            "inspired_by_real_question": "Pegadinha Campeã CEBRASPE — Cassação vs. Caducidade",
        },
        {
            "subtopic": "Atributos do Ato Administrativo (PATI)",
            "recurrence_level": "Muito Alta",
            "command_text": "No que se refere aos atributos dos atos administrativos e ao poder de polícia, julgue os itens que se seguem.",
            "statement": "Dado o atributo da autoexecutoriedade, inerente à totalidade dos atos administrativos, a administração pública pode inscrever em dívida ativa e executar diretamente, sem necessidade de intervenção do Poder Judiciário, o patrimônio do particular que deixe de pagar multa administrativa regularmente aplicada.",
            "answer": "E",
            "explanation": "ITEM ERRADO. A autoexecutoriedade NÃO está presente na totalidade dos atos administrativos; ademais, a cobrança coativa de multa pecuniária exige cobrança judicial (execução fiscal).",
            "pdf_quote": "A autoexecutoriedade não é atributo universal dos atos administrativos; ademais, no caso das multas, a imposição é autoexecutória, mas a execução forçada do pagamento depende da via judicial.",
            "pdf_page": "p. 10",
            "trap_type": "Termo Restritivo / Absoluto",
            "difficulty": "Média",
            "inspired_by_real_question": "Padrão CEBRASPE — Multa e Autoexecutoriedade",
        },
    ]

    mat_id = save_study_material(
        title="Aula Demonstrativa — Atos Administrativos (Cebraspe)",
        subject="Direito Administrativo",
        area="Tribunais / Jurídico",
        total_pages=28,
        pages=demo_pages,
        extracted_questions=[],
        recurrence_map=demo_subtopics,
    )

    parsed_topics = parse_pdf_topics_and_subtopics(demo_pages)
    save_material_knowledge_tree_nosql(
        material_id=mat_id,
        title="Aula Demonstrativa — Atos Administrativos (Cebraspe)",
        subject="Direito Administrativo",
        area="Tribunais / Jurídico",
        parsed_topics=parsed_topics,
        recurrence_map=demo_subtopics,
        stored_file_ids=[],
    )

    battery_id = save_question_battery(
        material_id=mat_id,
        title="Atos Administrativos — Pareto Cebraspe (Demo)",
        subject="Direito Administrativo",
        area="Tribunais / Jurídico",
        depth="Misto Padrão Cebraspe",
        recurrence_summary=demo_subtopics,
        assertions=demo_assertions,
    )
    return get_battery(battery_id)


# Servir build estático do frontend caso exista em ../frontend/dist ou CEBRASPELAB_FRONTEND_DIST
_env_frontend_dist = os.environ.get("CEBRASPELAB_FRONTEND_DIST")
FRONTEND_DIST = (
    Path(_env_frontend_dist)
    if _env_frontend_dist
    else Path(__file__).parent.parent / "frontend" / "dist"
)
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Rota de API não encontrada")
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404, detail="Frontend não encontrado")
