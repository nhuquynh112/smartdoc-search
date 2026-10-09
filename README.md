# SmartDoc Search

A Vietnamese document retrieval project built around the Vector Space Model (VSM), TF-IDF, cosine similarity, and ranked search results.

Developed for the **Multimedia Database Systems** course, the project focuses on explainable retrieval, reproducible experiments, and reliable document ingestion. PostgreSQL manages document metadata; a separate storage layer manages source files and processed text.

> **Project status:** Repository scaffold. Document ingestion, database initialization, search, and the application interface are planned and are not implemented yet.

## Objectives

- Ingest UTF-8 TXT files and PDFs with an extractable text layer.
- Normalize and tokenize Vietnamese text through a shared preprocessing pipeline.
- Generate document metadata automatically during ingestion.
- Represent documents and queries in the same TF-IDF feature space.
- Use an inverted index to select candidate documents, then rank them by cosine similarity.
- Evaluate retrieval quality using human relevance judgments, Precision@5, and MRR.

## Project Scope

The initial target is **100–200 valid Vietnamese documents** and **20–30 labeled evaluation queries**. Search results will include document titles, scores, source references, and access to document content.

OCR, chatbots, neural embeddings, and incremental TF-IDF updates are outside the initial scope. These extensions can be considered after the core system passes acceptance checks.

## Planned Architecture

```text
TXT / PDF documents
        |
        v
Document loader -> Vietnamese preprocessing -> Metadata generation
        |                       |                       |
        v                       v                       v
Original files            Processed text           PostgreSQL
        |                       |                       |
        +-----------------------+-----------------------+
                                |
                                v
                    Ready document snapshot
                                |
                                v
             TF-IDF + inverted index + document ID mapping
                                |
                                v
             Query preprocessing -> candidates -> cosine -> Top-K
                                |
                                v
                       Streamlit application
```

### Storage Responsibilities

- **PostgreSQL:** Stable document IDs, metadata, ingestion status, file references, and corpus revision tracking.
- **File storage:** Original documents and processed text, accessed through a storage adapter.
- **Index artifacts:** Fitted vectorizer, sparse TF-IDF matrix, ordered document IDs, inverted index, and a version manifest.

The instructor's note about storing content on a **“feed”** still requires clarification. Local file storage is a provisional design; the storage adapter will isolate changes once this requirement is confirmed.

## Repository Structure

```text
smartdoc-search/
├── README.md
├── .gitignore
├── app/                    # TV3 application interface
├── database/               # TV1 PostgreSQL schema and database setup
├── smartdoc/               # Shared Python package
│   └── __init__.py
├── scripts/                # Initialization, ingestion and evaluation commands
├── data/
│   ├── samples/            # Small shareable integration fixtures
│   └── sources.csv         # Source provenance register
├── storage/
│   ├── originals/          # Local source files; ignored by Git
│   └── processed/          # Local processed text; ignored by Git
├── artifacts/              # Generated index files; ignored by Git
├── reports/                # Generated statistics and metrics; ignored by Git
├── tests/                  # Unit and integration tests
│   └── __init__.py
└── docs/                   # Architecture, contracts and project checklists
```

Empty directories contain `.gitkeep` files so they remain visible in Git. Add only small, permitted test documents to `data/samples/`; keep the full corpus and user uploads outside version control.

## Team Responsibilities

| Role | Ownership | Main Deliverables |
| --- | --- | --- |
| TV1 — Data and Storage | Corpus collection, ingestion, Vietnamese preprocessing, metadata, PostgreSQL, storage adapter | Valid document corpus, schema, ingestion services, quality report, indexing data contract |
| TV2 — Retrieval Engine | VSM, TF-IDF, inverted index, cosine similarity, ranking, index lifecycle | Verified retrieval engine, versioned index artifacts, hand-calculated examples, algorithm tests |
| TV3 — Application and Evaluation | Streamlit interface, integration, relevance judgments, metrics, presentation | Working demo, evaluation results, integration checklist, report and slides |

Every member documents their own module and participates in end-to-end testing and the final presentation.

## TV1 Implementation Plan

| Planned Module | Responsibility |
| --- | --- |
| `smartdoc/config.py` | Read environment settings and resolve storage paths |
| `smartdoc/db.py` | Provide PostgreSQL connections and document repository operations |
| `smartdoc/document_loader.py` | Read TXT and extract PDF text; reject empty or unsupported input |
| `smartdoc/preprocessing.py` | Apply the shared Vietnamese normalization and tokenization pipeline |
| `smartdoc/metadata_extractor.py` | Generate metadata and SHA-256 fingerprints |
| `smartdoc/storage_adapter.py` | Store and retrieve original files and processed text |
| `smartdoc/ingestion.py` | Coordinate ingestion, duplicate handling, status transitions and corpus changes |
| `database/schema.sql` | Define document metadata and corpus revision storage |
| `scripts/init_db.py` | Initialize the database schema |
| `scripts/ingest_documents.py` | Run document ingestion from the command line |

These filenames describe planned work; the implementation files have not been created yet.

## Integration Contract

TV1 will expose `load_documents_for_index()` returning a list of records with:

| Field | Meaning |
| --- | --- |
| `document_id` | Stable database document ID |
| `title` | Document title, with filename fallback when needed |
| `clean_text` | Text prepared using the shared preprocessing configuration |
| `source_uri` | Known source reference; nullable when unavailable |
| `storage_ref` | Storage reference for the original document |

Only documents with `ingest_status = ready` may enter the index. Document IDs must remain stable after deletion, and records must be returned in a deterministic ID order.

TV2 will return ranked records containing `document_id`, `score`, and `rank`. TV3 will retrieve metadata and content through service functions rather than writing database queries inside UI code.

### Consistency Rules

1. Mark a document `ready` only after the original file and processed text are stored successfully.
2. Use SHA-256 to detect exact duplicate uploads; record failed ingestion with a clear reason.
3. Increment the corpus revision after a successful change to the searchable document set.
4. Rebuild the complete index after document additions or deletions in the initial demo.
5. Validate and activate index artifacts as a single version; never mix matrices, vectorizers, postings, or ID mappings from different builds.
6. Serve search only when the index revision matches the current corpus revision.

## Development Setup

### Current Stage

The repository currently contains the folder structure and documentation only. No database server or application is started by this scaffold.

### Planned Toolchain

- Python 3.11 or 3.12
- PostgreSQL
- Psycopg 3 for database access
- A Vietnamese tokenizer, selected and shared by TV1 and TV2
- A PDF text extraction library
- scikit-learn for TV2 retrieval
- Streamlit for TV3 application work

Dependency versions will be recorded after installation and verification.

### Next Setup Tasks

1. Add `.env.example` with `DATABASE_URL` and storage settings. Keep the real `.env` local.
2. Add `compose.yaml` for a local PostgreSQL service with persistent storage.
3. Add and verify `requirements.txt`.
4. Implement `database/schema.sql` and `scripts/init_db.py`.
5. Complete ingestion for ten sample documents and hand off the indexing contract to TV2.

Verified installation and execution commands will be added here as each stage becomes runnable.

## Evaluation and Acceptance

- At least 100 valid, accessible documents.
- At least 20 queries with independently assigned relevance labels.
- A hand-calculated TF-IDF and cosine example that matches the implementation.
- Indexed retrieval agrees with full-corpus scoring for positive-score results.
- Precision@5 uses a denominator of five even when fewer results are returned.
- MRR evaluation depth is defined before running experiments; use `MRR@K` when truncated.
- Failed uploads, duplicate files, empty queries, out-of-vocabulary queries, index rebuild failures, and restarts are handled explicitly.
- The final system can be recreated using the documented setup procedure.

## Working with Git

Use a feature branch for each module and review changes before merging into the default branch. Keep credentials, virtual environments, local corpus files, and generated index artifacts out of commits.

Before committing:

```bash
git status
git diff --check
git diff
```

## Technical References

- [PostgreSQL documentation](https://www.postgresql.org/docs/)
- [Psycopg 3 installation](https://www.psycopg.org/psycopg3/docs/basic/install.html)
- [scikit-learn TF-IDF documentation](https://scikit-learn.org/stable/modules/feature_extraction.html#tfidf-term-weighting)
- [Introduction to Information Retrieval](https://nlp.stanford.edu/IR-book/)
