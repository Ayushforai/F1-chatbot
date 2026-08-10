import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from utils.embeddings import get_embeddings

# Mapping categories to keywords in your filenames
CATEGORIES = {
    "sporting": "sporting",
    "technical": "technical",
    "financial": "financial",
    "operational": "operational"
}

def process_rulebooks():
    data_dir = "./data"
    output_dir = "./vector_store"
    
    if not os.path.exists(data_dir):
        print(f"Error: Add your FIA PDFs into a folder named '{data_dir}' first.")
        return

    print("Loading embedding model...")
    embeddings = get_embeddings()
    
    # Split text clean by paragraph boundaries without losing structural context
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        length_function=len
    )

    # Process files matching categories
    for category, keyword in CATEGORIES.items():
        matched_files = [f for f in os.listdir(data_dir) if keyword in f.lower() and f.endswith('.pdf')]
        
        if not matched_files:
            print(f"Skipping category '{category}': No matching PDF found containing keyword '{keyword}'")
            continue
            
        print(f"\nProcessing {category} regulations...")
        all_chunks = []
        
        for file in matched_files:
            file_path = os.path.join(data_dir, file)
            print(f" -> Parsing {file}")
            loader = PyPDFLoader(file_path)
            docs = loader.load()
            chunks = text_splitter.split_documents(docs)
            all_chunks.extend(chunks)
            
        if all_chunks:
            print(f" -> Generating embeddings for {len(all_chunks)} chunks...")
            vector_db = FAISS.from_documents(all_chunks, embeddings)
            
            # Save locally
            cat_output_path = os.path.join(output_dir, category)
            vector_db.save_local(cat_output_path)
            print(f" -> Successfully saved index to {cat_output_path}")

    print("\nVector database initialization complete.")

if __name__ == "__main__":
    process_rulebooks()