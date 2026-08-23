import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS

from utils.embeddings import get_embeddings
from utils.regulation_parser import (
    articles_to_documents,
    discover_regulation_pdfs,
    parse_regulation_text,
    regulation_year_from_filename,
    save_articles_index,
    section_from_filename,
    select_pdfs_for_indexing,
)


def process_rulebooks():
    output_dir = "./vector_store"
    grouped = discover_regulation_pdfs()
    selected = select_pdfs_for_indexing(grouped)

    if not any(selected.values()):
        print(
            "Error: No regulation PDFs found. Add FIA PDFs under ./data or ./data/archive "
            "(sporting, technical, financial, operational, or Section A–E files)."
        )
        return

    print("Loading embedding model...")
    embeddings = get_embeddings()

    for category, pdf_paths in selected.items():
        if not pdf_paths:
            print(f"Skipping category '{category}': no matching PDFs found.")
            continue

        print(f"\nProcessing {category} regulations...")
        all_documents = []
        parsed_articles = []

        for file_path in sorted(pdf_paths):
            file_name = os.path.basename(file_path)
            print(f" -> Parsing {file_name}")
            loader = PyPDFLoader(file_path)
            docs = loader.load()
            pages = [(doc.metadata.get("page", index), doc.page_content) for index, doc in enumerate(docs)]
            articles = parse_regulation_text(
                pages,
                source=file_path,
                regulation_year=regulation_year_from_filename(file_name),
                section=section_from_filename(file_name),
            )
            parsed_articles.extend(articles)
            all_documents.extend(articles_to_documents(articles))

        if not all_documents:
            print(f" -> No indexable content found for {category}.")
            continue

        articles_path = save_articles_index(category, parsed_articles, output_dir)
        print(f" -> Saved {len(parsed_articles)} structured articles to {articles_path}")
        print(f" -> Generating embeddings for {len(all_documents)} chunks...")
        vector_db = FAISS.from_documents(all_documents, embeddings)

        cat_output_path = os.path.join(output_dir, category)
        vector_db.save_local(cat_output_path)
        print(f" -> Successfully saved index to {cat_output_path}")

    print("\nVector database initialization complete.")


if __name__ == "__main__":
    process_rulebooks()
