from app.backend.services.retrieval_service import build_corpus

if __name__ == "__main__":
    corpus = build_corpus()
    print(f"Loaded {len(corpus)} chunks")
    for item in corpus[:5]:
        print(item["source"], item["chunk_id"])