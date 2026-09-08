"""Generate small, synthetic PDF fixtures for the interview demo."""

from pathlib import Path

import fitz


OUTPUT_DIR = Path(__file__).resolve().parent


def build_pdf(name: str, title: str, pages: list[tuple[str, list[str]]]) -> Path:
    """Build a readable PDF using only synthetic content defined in this file."""
    document = fitz.open()

    for page_number, (heading, paragraphs) in enumerate(pages, start=1):
        page = document.new_page(width=595, height=842)
        page.insert_text((54, 62), title, fontsize=20, color=(0.08, 0.16, 0.28))
        page.insert_text(
            (54, 88),
            f"{heading} · Página {page_number}",
            fontsize=12,
            color=(0.15, 0.45, 0.55),
        )

        vertical_position = 125
        for paragraph in paragraphs:
            remaining_space = page.insert_textbox(
                fitz.Rect(54, vertical_position, 541, vertical_position + 115),
                paragraph,
                fontsize=11,
                lineheight=1.45,
                color=(0.12, 0.14, 0.18),
            )
            if remaining_space < 0:
                raise ValueError(
                    f"Content does not fit on page {page_number} of {name}"
                )
            vertical_position += 125

        page.draw_line((54, 790), (541, 790), color=(0.75, 0.8, 0.85), width=0.7)
        page.insert_text(
            (54, 812),
            "Documento ficticio y seguro para demostraciones.",
            fontsize=8,
            color=(0.35, 0.4, 0.45),
        )

    document.set_metadata(
        {
            "title": title,
            "author": "AI Research Assistant demo",
            "subject": "Fixture ficticio para demostraciones",
        }
    )
    output_path = OUTPUT_DIR / name
    document.save(output_path, garbage=4, deflate=True)
    document.close()
    return output_path


def main() -> None:
    generated = [
        build_pdf(
            "guia-rag-seguro.pdf",
            "Guía breve de RAG trazable",
            [
                (
                    "Recuperación y reranking",
                    [
                        "Un sistema RAG recupera fragmentos antes de redactar una respuesta. "
                        "La búsqueda inicial prioriza cobertura aunque el primer orden no sea perfecto.",
                        "El reranking vuelve a puntuar los candidatos y coloca primero los fragmentos "
                        "más relacionados con la pregunta. Así reduce contexto irrelevante y facilita "
                        "respuestas fundamentadas.",
                        "Ejemplo ficticio: para una consulta sobre retención de copias, el recuperador "
                        "devuelve cinco fragmentos y el reranker prioriza el que contiene la política.",
                    ],
                ),
                (
                    "Citas y evaluación",
                    [
                        "Una cita trazable debe identificar como mínimo el archivo, la página y el "
                        "fragmento que sustenta la afirmación.",
                        "La evaluación recomendada combina Hit Rate, MRR y nDCG para retrieval con "
                        "revisión humana de fidelidad y utilidad.",
                        "Antes de una demo conviene probar una pregunta directa, otra de seguimiento "
                        "y una pregunta sin evidencia.",
                    ],
                ),
            ],
        ),
        build_pdf(
            "informe-solar-ficticio.pdf",
            "Informe solar Aurora · Datos ficticios",
            [
                (
                    "Resumen trimestral",
                    [
                        "Aurora es una instalación imaginaria creada para esta demostración. Durante "
                        "abril produjo 128 MWh, en mayo 141 MWh y en junio 136 MWh.",
                        "La disponibilidad mensual fue 97,8 % en abril, 98,4 % en mayo y 98,1 % en "
                        "junio. La disponibilidad media reportada fue 98,1 %.",
                        "Mes        Energía (MWh)        Disponibilidad\n"
                        "Abril             128                    97,8 %\n"
                        "Mayo              141                    98,4 %\n"
                        "Junio             136                    98,1 %",
                    ],
                ),
                (
                    "Hallazgos y acciones",
                    [
                        "El análisis ficticio atribuye la menor producción de abril a dos jornadas "
                        "nubladas y a una parada preventiva de cuatro horas.",
                        "La recomendación es revisar la limpieza de los paneles cada dos semanas y "
                        "comparar la producción observada con el pronóstico meteorológico.",
                        "El objetivo es mantener una disponibilidad igual o superior al 98 % y "
                        "documentar cualquier parada de más de dos horas.",
                    ],
                ),
            ],
        ),
    ]

    for path in generated:
        print(f"Generated {path.relative_to(OUTPUT_DIR.parent)}")


if __name__ == "__main__":
    main()
