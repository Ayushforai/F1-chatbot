import os
import ollama
import torch
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from utils.router import route_query, extract_telemetry_params
from utils.f1_api import get_driver_telemetry

MODEL_NAME = 'qwen2.5:7b-instruct-q8_0'

def generate_f1_response(user_query: str, context_text: str) -> str:
    system_prompt = (
        "You are an elite Formula 1 expert — part race engineer, part statistician, part historian.\n\n"
        "CRITICAL RULES:\n"
        "1. Answer the user's query using ONLY the information provided in the CONTEXT DATA PACKET below.\n"
        "2. If the CONTEXT DATA PACKET contains a dict or structured record, extract and present the relevant fields clearly and conversationally.\n"
        "3. If the CONTEXT DATA PACKET contains an error message or says the driver did not compete, report that honestly. DO NOT guess or fabricate.\n"
        "4. NEVER invent race results, lap times, or team names not present in the context.\n\n"
        f"CONTEXT DATA PACKET:\n{context_text}"
    )

    try:
        response = ollama.generate(
            model=MODEL_NAME,
            system=system_prompt,
            prompt=user_query,
            options={'temperature': 0.1, 'top_p': 0.9}
        )
        return response['response']
    except Exception as e:
        return f"Telemetry stream interrupted. Error: {e}"

def main():
    print("Initializing Hybrid F1 Race Engineer Pipeline...")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-base-en-v1.5",
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )
    vector_store_root = "./vector_store"

    print(f"\nPit Wall Active [Model: {MODEL_NAME}]. Type 'exit' to close telemetry link.\n")

    conversation_history = []

    while True:
        user_query = input("Engineer Query > ").strip()
        if user_query.lower() in ['exit', 'quit']:
            break
        if not user_query:
            continue

        # 1. Routing Layer (with conversation context)
        category = route_query(user_query, history=conversation_history)
        print(f" [Router] Intent isolated to: {category.upper()}")

        # 2. Branching Execution Paths
        if category == "quantitative":
            print(" [Extractor] Processing query context via Qwen...")
            params = extract_telemetry_params(user_query, history=conversation_history)
            
            print(f" [Debug] Qwen Extracted JSON: {params}")
            
            # Extract parameters safely with fallbacks
            q_type = params.get("query_type")
            driver = params.get("driver_number") # Remains None if no driver is extracted
            year = params.get("year") or 2026
            country = params.get("country")
            lap = params.get("lap_number")
            
            if q_type == "fastest_lap" and country:
                print(f" [API Connection] Scanning {year} {country} archives for the fastest lap...")
                from utils.f1_api import get_fastest_lap_of_race
                telemetry_data = get_fastest_lap_of_race(year, country, driver) 
                context = f"Historical Fastest Lap Record: {str(telemetry_data)}"
                
            elif (q_type == "specific_lap" or lap is not None) and country:
                print(f" [API Connection] Accessing historical archives for {country} {year}, Lap {lap}...")
                from utils.f1_api import get_historical_lap
                d_num = driver or 44 
                telemetry_data = get_historical_lap(year, country, d_num, lap)
                context = f"Historical Lap Data Packet: {str(telemetry_data)}"
                
            else:
                d_num = driver or 44 
                print(f" [API Connection] Querying live OpenF1 data stream for Driver #{d_num}...")
                from utils.f1_api import get_driver_telemetry
                telemetry_data = get_driver_telemetry(driver_number=d_num)
                context = f"Live telemetry data from vehicle streams: {str(telemetry_data)}"

        elif category == "historical":
            # Historical CSV Database Path
            print(" [Extractor] Processing historical query via Qwen...")
            params = extract_telemetry_params(user_query, history=conversation_history)
            print(f" [Debug] Qwen Extracted JSON: {params}")

            year = params.get("year") or 2024
            country = params.get("country")
            driver_name = params.get("driver_name") or ""

            print(f" [CSV Lookup] Searching historical records: {driver_name} | {year} | {country}...")
            from utils.historical_db import get_historical_driver_info
            historical_data = get_historical_driver_info(year, driver_name, country)
            context = f"Historical Race Record: {str(historical_data)}"

        else:
            # Document Retrieval Path (Unstructured FAISS RAG)
            index_path = os.path.join(vector_store_root, category)
            if not os.path.exists(index_path):
                print(f" [Error] The index directory '{index_path}' hasn't been compiled yet.\n")
                continue

            db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
            docs = db.similarity_search(user_query, k=3)
            context = "\n\n".join([doc.page_content for doc in docs])

        # 3. Text Generation
        answer = generate_f1_response(user_query, context)
        print(f"\nResponse:\n{answer}\n")
        print("-" * 50)

        # 4. Update conversation history (keep last 5 turns)
        conversation_history.append({"query": user_query, "category": category})
        conversation_history = conversation_history[-5:]

if __name__ == "__main__":
    main()