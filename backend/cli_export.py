"""
CLI para gerar e exportar baterias de assertivas Cebraspe diretamente pelo terminal
para Anki (.apkg / .csv), PDF (Prova + Gabarito) e Markdown.

Exemplo de uso:
  uv run --directory backend python cli_export.py --pdf ../minha_aula.pdf --area "Tribunais / Jurídico" --out-dir ../exports
"""
import argparse
from pathlib import Path
from database import get_battery, get_settings, init_db, save_question_battery, save_study_material
from exporters import export_to_anki_apkg, export_to_anki_csv, export_to_markdown, export_to_pdf_bytes
from gemini_service import analyze_pdf_recurrence, generate_cebraspe_assertions
from pdf_processor import extract_pdf_pages, extract_questions_heuristic


def main() -> None:
    parser = argparse.ArgumentParser(description="Gerador CLI de Assertivas Cebraspe por Recorrência")
    parser.add_argument("--pdf", required=True, help="Caminho para o arquivo PDF de estudo")
    parser.add_argument("--questions-pdf", default="", help="Caminho opcional para PDF/JSON de questões Cebraspe")
    parser.add_argument("--area", default="Geral", help="Área do concurso (Geral, Policial, Tribunais / Jurídico, Controle / Fiscal, TI, Administrativo)")
    parser.add_argument("--depth", default="Misto Padrão Cebraspe", help="Nível de profundidade")
    parser.add_argument("--subject", default="", help="Nome da disciplina/matéria")
    parser.add_argument("--out-dir", default="./exports", help="Pasta de saída para salvar .apkg, .csv, .pdf e .md")
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    api_key = settings.get("gemini_api_key", "")
    model_name = settings.get("gemini_model", "gemini-2.5-flash")

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

    print(f"[1/4] Extraindo páginas de {pdf_path.name}...")
    pages = extract_pdf_pages(pdf_path.read_bytes(), pdf_path.name)
    real_questions = extract_questions_heuristic(pages)

    print(f"[2/4] Analisando recorrência Cebraspe ({len(pages)} páginas, {len(real_questions)} questões detectadas)...")
    analysis = analyze_pdf_recurrence(
        pages=pages,
        heuristic_questions=real_questions,
        area=args.area,
        api_key=api_key,
        model_name=model_name,
        custom_subject_hint=args.subject,
    )

    subject = analysis.get("detected_subject") or args.subject or "Disciplina"
    title = analysis.get("detected_title") or pdf_path.stem
    subtopics = analysis.get("subtopics", [])

    mat_id = save_study_material(
        title=title,
        subject=subject,
        area=args.area,
        total_pages=len(pages),
        pages=pages,
        extracted_questions=real_questions,
        recurrence_map=subtopics,
    )

    total_min = sum(int(s.get("min_recommended_questions", 3)) for s in subtopics)
    print(f"[3/4] Gerando {total_min} assertivas inéditas distribuídas em {len(subtopics)} subtópicos...")
    assertions = generate_cebraspe_assertions(
        pages=pages,
        real_questions=real_questions,
        subtopic_plan=subtopics,
        subject=subject,
        title=title,
        area=args.area,
        depth=args.depth,
        api_key=api_key,
        model_name=model_name,
    )

    battery_id = save_question_battery(
        material_id=mat_id,
        title=title,
        subject=subject,
        area=args.area,
        depth=args.depth,
        recurrence_summary=subtopics,
        assertions=assertions,
    )
    battery = get_battery(battery_id)

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"cebraspe_{battery_id}_{pdf_path.stem}"

    print(f"[4/4] Exportando Anki (.apkg, .csv), PDF e Markdown em {out_dir}...")
    (out_dir / f"{base_name}.apkg").write_bytes(export_to_anki_apkg(battery))
    (out_dir / f"{base_name}_anki.csv").write_text(export_to_anki_csv(battery), encoding="utf-8-sig")
    (out_dir / f"{base_name}.pdf").write_bytes(export_to_pdf_bytes(battery))
    (out_dir / f"{base_name}.md").write_text(export_to_markdown(battery), encoding="utf-8")

    print(f"Concluído com sucesso! Bateria #{battery_id} salva no banco e exportada em: {out_dir}")


if __name__ == "__main__":
    main()

