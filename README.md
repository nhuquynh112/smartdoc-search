# SmartDoc Search

**Vietnamese document retrieval with TF-IDF, cosine similarity, and PostgreSQL.**

SmartDoc Search is an academic project for the **Multimedia Database Systems** course. It brings document ingestion, Vietnamese text processing, feature indexing, ranked retrieval, and experimental evaluation into one system design.

The project is built around a concrete question: **given a Vietnamese query, which documents should appear first, and what evidence explains their ranking?** Its focus is a traceable path from source documents to searchable features, with retrieval results that can be checked against mathematical examples and human relevance judgments.

**Development stage on `Dat`:** the PostgreSQL data pipeline, shared Vietnamese preprocessing, TF-IDF/inverted-index retrieval and Streamlit application are integrated. Search, content reading, index freshness/rebuild, upload validation and ranking explanations have automated and live-database evidence. The local corpus checked on 10–11 October 2026 contains 200 ready documents at revision 235; cloning this repository does not copy that private database. The evaluation kit contains 25 draft queries and 500 blank pooled judgments. **Human relevance labels, Precision@5/MRR@20 results and final team acceptance are still pending.** See [the TV3 acceptance record](docs/tv3_acceptance.md) and [remaining delivery steps](docs/tv3_remaining.md).

## Contents

- [Project Goals](#project-goals)
- [Scope and User Experience](#scope-and-user-experience)
- [System Architecture](#system-architecture)
- [Retrieval Method](#retrieval-method)
- [Data and Storage Design](#data-and-storage-design)
- [Module Contracts](#module-contracts)
- [Repository Structure](#repository-structure)
- [Technology Choices](#technology-choices)
- [Getting Started](#getting-started)
- [Evaluation and Verification](#evaluation-and-verification)
- [Team Responsibilities](#team-responsibilities)
- [Development Workflow](#development-workflow)
- [Delivery Milestones](#delivery-milestones)
- [Limitations and Future Work](#limitations-and-future-work)
- [References](#references)

## Project Goals

The implementation addresses the four core requirements of the assignment:

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Text preprocessing | Shared Vietnamese normalization and tokenization for documents and queries | Documented before-and-after examples and edge-case tests |
| TF-IDF representation | A fitted vocabulary and weighted sparse document matrix | A small hand-calculated example checked against the configured library |
| Cosine similarity | Comparable query and document vectors in the same feature space | Numerical checks and full-corpus scoring comparisons |
| Result ranking | Descending similarity scores with deterministic tie handling and Top-K selection | Expected-order tests and retrieval evaluation |

The supporting work adds an inverted feature index, automatic metadata generation, PostgreSQL persistence, and a reproducible demonstration.

## Scope and User Experience

The assignment targets **100–200 valid Vietnamese documents** and **20–30 queries with human relevance labels**. The local demo database has 200 ready news documents; the committed evaluation queries remain drafts and their labels are blank. Database text and original files are transferred separately from source code.

The Streamlit application lets a user:

1. Upload a TXT file or a PDF with an extractable text layer.
2. Review automatically generated metadata and the ingestion outcome.
3. Enter a Vietnamese query and choose the number of results.
4. Inspect document titles, ranks, similarity scores, sources, and document content.
5. Examine selected preprocessing outputs, index postings, and term contributions to a result's score.

Image-only PDFs cannot become ready documents without extractable text. OCR is outside the baseline scope.

## System Architecture

The design separates data management, retrieval, and presentation so each component has a clear responsibility and a testable interface.

```text
                       DOCUMENT INGESTION

    TXT / text-based PDF
             |
             v
    Validation and extraction
             |
             v
    Vietnamese preprocessing
             |
             v
    Storage and metadata persistence
             |
       +-----+-------------------+
       |                         |
       v                         v
    File storage             PostgreSQL
    Original files           Document metadata
    Processed text           Ingestion state
                             Corpus revision
       |                         |
       +------------+------------+
                    |
                    v
            Ready corpus snapshot
                    |
                    v
       TF-IDF matrix + inverted index
       Ordered document IDs + manifest

                        QUERY RETRIEVAL

    Query -> shared preprocessing -> fitted vectorizer
                                          |
                                          v
                               Inverted-index candidates
                                          |
                                          v
                                Cosine scoring -> Top-K
                                          |
                                          v
                          Metadata and content resolution
                                          |
                                          v
                                  Streamlit interface
```

A storage adapter isolates access to document files. The instructor's note about storing content on a **“feed”** requires clarification; local file storage remains provisional until that requirement is resolved.

## Retrieval Method

### Vietnamese Preprocessing

Documents and queries use shared Unicode normalization, lowercase conversion, whitespace/punctuation handling and Vietnamese word segmentation. Vietnamese diacritics and underscore-joined compound tokens are preserved. Stopword removal is configurable and disabled in the current default pipeline.

Per-document preprocessing manifests and corpus fingerprints record the frozen configuration. Evaluation must use a matching installed pipeline; changing preprocessing requires reprocessing, rebuilding and reviewing a new experiment.

### TF-IDF and the Vector Space Model

Each document is represented by term weights in a shared vocabulary. The baseline design uses raw term counts, smoothed inverse document frequency, and L2 normalization:

```text
idf(t)       = log((1 + N) / (1 + df(t))) + 1
weight(t, d) = count(t, d) × idf(t)
vector(d)    = weight(d) / ||weight(d)||₂
```

Here, `N` is the number of indexed documents and `df(t)` is the number containing term `t`. The final library settings and the hand-calculated example must use the same conventions.

Queries are transformed using the fitted corpus vectorizer. They are not fitted independently or added to the corpus during search.

### Candidate Selection and Ranking

The inverted index maps each vocabulary term to document IDs containing that feature. Query candidates are the **union** of the postings for the query's known terms, allowing partial term overlap.

```text
cosine(q, d) = (q · d) / (||q||₂ × ||d||₂)
```

For L2-normalized nonzero vectors, cosine similarity equals the dot product. The engine ranks positive-score results by descending score, then ascending document ID for ties. Fewer than `K` results may be returned when fewer documents have positive scores.

Empty queries, queries with no known vocabulary terms, and an empty corpus have explicit outcomes. A similarity score measures lexical overlap under this representation; it is not a probability that a document is relevant.

### Ranking Explanations

For normalized vectors, each shared term contributes `q[t] × d[t]` to the score. The application displays query tokens, posting lists/candidates, normalized weights and per-term contributions for a selected result.

## Data and Storage Design

### Document Metadata

The implemented `documents` table captures identity, provenance, storage references, text and ingestion state.

| Field | Purpose |
| --- | --- |
| `id` | Stable document identifier |
| `title` | Document title with a filename fallback |
| `file_type` | Supported source format |
| `size_bytes` | Original file size |
| `sha256` | Exact-file duplicate detection |
| `word_count` | Token count after segmentation and before stopword removal |
| `source_uri` | Known provenance reference; nullable when unavailable |
| `storage_ref` | Reference to the original file |
| `text_ref` | Reference to an optional processed-text compatibility cache |
| `raw_text` | Extracted document text stored in PostgreSQL |
| `clean_text` | Preprocessed searchable text stored in PostgreSQL |
| `created_at` | Time of ingestion, distinct from publication time |
| `ingest_status` | `pending`, `ready`, or `failed` |
| `error_message` | Reason for failed ingestion |

Source references will be recorded when known rather than inferred. SHA-256 detects identical files; detection of near-duplicate content is outside the baseline duplicate policy.

### Storage Boundaries

| Layer | Stores |
| --- | --- |
| PostgreSQL | Metadata, raw text, clean text, document identity, ingestion state, and corpus revision |
| File storage | Original files and optional processed-text caches |
| Index artifacts | Vectorizer, sparse TF-IDF matrix, ordered ID mapping, inverted index, and version manifest |

### Consistency Rules

- A document becomes `ready` only after file writes succeed and metadata, raw text, clean text and the preprocessing manifest are committed to PostgreSQL.
- Only `ready` documents enter the searchable corpus; IDs remain stable after other documents are deleted.
- A successful change to the searchable corpus increments `corpus_revision`.
- The initial implementation rebuilds the complete index after additions or deletions.
- New artifacts are built and validated separately, then activated as one version.
- Search requires a matching corpus and index revision. Failed rebuilds must not expose a partially built index.

The baseline demo will serialize corpus mutations and index rebuilds. PostgreSQL transactions do not cover filesystem operations; ingestion and deletion services must handle failures across both storage layers.

## Module Contracts

The data-service and retrieval interfaces below are implemented. UI integration calls these services rather than writing SQL or fitting a separate model.

### Data to Retrieval

`load_documents_for_index()` returns records in deterministic document-ID order:

```python
{
    "document_id": 42,
    "title": "Example document",
    "clean_text": "segmented and normalized Vietnamese text",
    "source_uri": None,
    "storage_ref": "originals/example.pdf",
}
```

`load_corpus_snapshot()` returns `documents` together with `corpus_revision` under the ingestion lock. The index builder should use this snapshot. It must preserve the row-to-document mapping when saving the matrix and related artifacts.

### Retrieval to Application

`smartdoc.retrieval_engine.search_query(query, top_k=5)` returns a response dictionary:

```python
{
    "status": "ok",
    "message": "...",
    "results": [{"document_id": 42, "score": 0.856, "rank": 1}],
    "index_version": "...",
    "corpus_revision": 235,
}
```

The public engine accepts integer `top_k` from 1 to 20; the UI offers 5/10/20. Outcomes include `ok`, `empty_query`, `oov_query`, `empty_corpus`, `index_unavailable` and `stale_index`. Invalid argument types/ranges raise `InvalidRetrievalInputError`.

`app.search_service.SearchService` exposes `status()`, `search()`, `rebuild()` and `explain()`. It enriches hits with metadata by stable ID and checks freshness before/after retrieval. Rebuild returns `rebuilt`; a failed build is reported as `rebuild_failed`, and results from an incompatible version are hidden. Content comes from `smartdoc.ingestion.get_document_text()` and PostgreSQL `raw_text`. The UI does not own SQL queries or a separate preprocessing/indexing implementation.

## Repository Structure

```text
smartdoc-search/
├── README.md               # Shared project overview
├── .gitignore              # Local files excluded from version control
├── app/                    # Application interface
├── database/               # PostgreSQL schema and setup
├── smartdoc/               # Shared data and retrieval package
│   └── __init__.py
├── scripts/                # Initialization and pipeline commands
├── data/
│   ├── samples/            # Small, shareable integration fixtures
│   └── sources.csv         # Corpus source register
├── storage/
│   ├── originals/          # Local source files
│   └── processed/          # Local processed text
├── data/tv2_index/          # Generated UI retrieval index (ignored)
├── evaluation/             # Frozen manifest, draft queries and blank judgments
├── reports/                # Generated data-quality and evaluation results
├── tests/                  # Unit and integration tests
│   └── __init__.py
└── docs/                   # Design notes and contributor checklists
```

Empty directories are retained with `.gitkeep`. Local uploads, processed text, generated artifacts, and report outputs are ignored by Git. Only small sample documents with appropriate sharing permission belong in `data/samples/`. Final report assets intended for review will be added explicitly in a documented location.

## Technology Choices

| Component | Technology | Purpose |
| --- | --- | --- |
| Language | Python 3.12 for the tested integrated environment | Data pipeline and retrieval services |
| Metadata database | PostgreSQL | Persistent document management |
| Database adapter | Psycopg 3 | Parameterized database access |
| Retrieval | scikit-learn and sparse matrices | TF-IDF and numerical scoring |
| Application | Streamlit | Interactive demonstration |
| PDF extraction | pypdf | Text-layer extraction |
| Vietnamese segmentation | Underthesea | Shared document and query features |
| Collaboration | Git and GitHub | Version control and review |

`requirements_tv3.txt` includes shared dependencies and pins the tested application/numerical stack. PostgreSQL metadata indexes and the retrieval inverted index serve different purposes; the latter is the feature index used for search.

## Getting Started

### Prerequisites

- Git and Python 3.12 for the tested application dependency set.
- Ubuntu: Docker Engine with the Compose plugin, or Docker Desktop.
- Windows: Docker Desktop running Linux containers.

Docker runs PostgreSQL; Python and the application run on the host. Each contributor has an independent local database. See [the Docker setup guide](docs/docker_setup.md) for installation references and troubleshooting.

### 1. Clone the Repository

```bash
git clone --branch Dat https://github.com/nhuquynh112/smartdoc-search.git
cd smartdoc-search
```

### 2. Configure Local Environment Variables

Ubuntu:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` locally and replace both `CHANGE_ME` placeholders with the same password. For the initial setup, use letters and digits to avoid URI escaping. Host Python connects to port 5433. On Windows with the Docker IPv4 binding, use `127.0.0.1` as the `DATABASE_URL` host if `localhost` incurs an IPv6 timeout. Keep `.env` out of version control.

### 3. Start PostgreSQL

Run from the repository root on either operating system:

```bash
docker compose up -d --wait
docker compose ps
```

The `db` service should report `healthy`, with port mapping `127.0.0.1:5433->5432/tcp`. Port 5433 avoids a conflict with a native PostgreSQL installation on port 5432.

Check the database and role inside the container:

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

At the psql prompt:

```sql
SELECT current_database(), current_user;
\q
```

The defaults are database `smartdoc` and role `smartdoc_app`. This container-local check does not yet verify host-side Python authentication or the project schema.

### 4. Create a Python Virtual Environment

Ubuntu:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python --version
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

If PowerShell blocks activation, the environment's interpreter can be used directly as `.\.venv\Scripts\python.exe`. Creating the environment does not install project dependencies.

### 5. Stop and Resume the Database

```bash
docker compose down
docker compose up -d --wait
```

The named volume retains database contents after `down`. Adding `-v` deletes the volume and its data. Changing credentials in `.env` does not update an already initialized database; changes must also be applied to the existing database role.

### Verified Setup Status

Ubuntu setup has been demonstrated with Python **3.12.3**, PostgreSQL **16.15**, host-side authentication and schema initialization. The integrated app has also been verified on Windows with Python **3.12.6**, PostgreSQL **16**, Streamlit **1.65.0** and 200 ready documents. On 11 October, a fresh virtual environment installed `requirements_tv3.txt`, passed `pip check` and passed the final **236 tests plus 38 subtests in 65.80 seconds** on a disposable database; demo count/revision remained unchanged. This verifies the tested dependency/schema path; it does not mean a clean clone includes the private corpus or certify every restore scenario on another machine.

### 6. Install Dependencies and Choose a Data Setup

With the virtual environment active:

```bash
python -m pip install -r requirements_tv3.txt
```

For a new empty development dataset, initialize the schema and import the included small fixture:

```bash
python -m scripts.init_db
python -m scripts.ingest_documents data/samples
python -m scripts.check_db
```

Immediately after schema initialization, before importing documents, a fresh database should report:

```text
Database schema initialized successfully.
Connected to database: smartdoc
Corpus revision: 0; ready documents: 0
```

To receive the team's 200-document corpus, obtain the private dump and matching manifest, then follow [the database transfer guide](docs/database_transfer.md). **Do not initialize the schema before restore:** restore requires an empty schema. An existing populated database should be retained; use a separate empty database for a restore test. The Git repository does not contain the dump or original corpus files.

The schema contains `documents` and `corpus_state`. Initialization creates the base schema and applies SQL files from `database/migrations/` in filename order. Current migrations are additive and idempotent, so rerunning preserves existing records. This is a simple migration runner without a migration-history table; future migration files must remain safe to rerun. Commands must be run from the repository root.

### Preview Document Processing

```bash
python -m scripts.preview_document data/samples/intro_information_systems.txt
python -m unittest tests.test_text_pipeline -v
```

The preview does not insert records into PostgreSQL. TXT inputs must be UTF-8 (a BOM is accepted); PDFs must contain extractable text and must not be encrypted. Default preprocessing uses Underthesea segmentation, preserves diacritics and disables stopword removal. TV2 must use the same `PreprocessingConfig` for documents and queries and preserve underscore-joined tokens in its vectorizer.

### Export Corpus Quality Checks

```bash
python -m scripts.report_data_quality
```

This read-only command writes `reports/data_quality_report.csv` and `reports/data_quality_summary.json`, including document states, word counts, missing database sources and storage integrity checks. Generated reports are excluded from Git. Duplicate upload attempts are not persisted, so their count is reported as unavailable rather than zero. These checks do not certify PDF reading order or linguistic quality; review extracted text manually. Source entries in `data/sources.csv` are not automatically imported into database metadata.

### Run the Application

```bash
python -m streamlit run app/main.py
```

Open the URL printed by Streamlit. On the search page, use **Xây lại chỉ mục** when no index exists or the corpus has changed. The application reads the whole ready library and stores its generated index in ignored `data/tv2_index/`. A stale revision/fingerprint/version cannot serve ranked results. See [the application guide](docs/tv3_ui_pro_v2.md) for the complete workflow.

### Import Documents

```bash
python -m scripts.ingest_documents data/samples
python -m scripts.check_db
```

The importer reports `ready`, `duplicate`, or `failed` per file. It saves originals and processed text outside Git, generates metadata, and increments the corpus revision for new ready documents. Failed records do not enter the index. A failed file with the same hash can be retried using `--retry-failed`, preserving its ID and metadata. Ready documents remain duplicates and are not overwritten. If the file bytes change, the new hash represents a new document. The included sample is self-authored integration data, not a labeled evaluation corpus.

```bash
python -m scripts.ingest_documents path/to/file.pdf --retry-failed
```

Run text-pipeline tests:

```bash
python -m unittest tests.test_text_pipeline -v
```

Run mutation tests through the disposable-database runner:

```bash
python -m scripts.test_tv3_isolated_database
```

It requires the configured PostgreSQL role to have `CREATEDB`, creates a unique test database and temporary storage, then removes only the database it created. It verifies that the demo ready count/revision are unchanged. Direct ingestion/recovery tests create/delete records and advance revision, so do not point them at the frozen demo/evaluation database.

Ingestion serializes operations through a PostgreSQL advisory lock. Individual filesystem writes are atomic, but database and filesystem storage are not one transaction. Recovery tests and [storage reconciliation](docs/recovery.md) cover known failure paths; a crash may still leave orphan files requiring audit. Segmentation respects basic sentence punctuation/newlines before tokenization; linguistic accuracy still requires corpus review.

### Export Data for TV2

```bash
python -m scripts.export_corpus
```

This writes `reports/tv2_corpus.json` with ready document text, stable IDs, corpus revision and a snapshot fingerprint. TV2 can load it without PostgreSQL; follow [the handoff guide](docs/tv2_handoff.md). The export does not include original PDFs, and its storage references remain local to TV1. Per-document preprocessing manifests are persisted and verified before export. See [the version lifecycle](docs/preprocessing_version.md).

## Evaluation and Verification

### Evaluation Collection

The experiment uses a fixed corpus, documented queries, and human-assigned relevance judgments. The committed kit currently has 25 draft queries and 500 blank Top-20-plus-seed judgments. Labels must be assigned from content independently of cosine scores/ranks, then reviewed. See [the labeling procedure](evaluation/README.md); no real relevance score is available before this work is complete.

Queries will cover individual terms, multiword information needs, Vietnamese compounds, ambiguous terms, and lexical limitations such as synonyms. Queries with no relevant documents in the corpus will be reported separately as behavioral checks.

### Metrics

| Measure | Convention |
| --- | --- |
| Precision@5 | Relevant documents in the first five positions divided by five; missing positions count as nonrelevant |
| MRR@20 | Mean reciprocal rank of the first relevant result in the first 20; zero when none is retrieved |
| Query latency | Measured after loading the index, with the timed steps and environment specified |
| Index build time | Reported separately from query latency |

The protocol fixes the depth at **MRR@20**. Reports include per-query results, aggregate metrics, corpus size, preprocessing configuration and timing samples. The CLI refuses draft/incomplete labels, corpus changes and unmatched preprocessing. Every actual Top-20 result must have a human label; unjudged documents never silently count as nonrelevant. Pooled judgments do not establish full-corpus recall. No Precision@5/MRR@20 benchmark scores are claimed yet.

Timing can be measured independently with `python -m scripts.benchmark_tv3_latency --source database --corpus vietonline_news_200 --rebuild --repeats 5 --warmups 1`. It uses a separate frozen-input index, records API and preloaded-core samples, and excludes build/load/warmup from query samples. A draft timing workload is explicitly marked provisional and never produces relevance metrics. API timing excludes the UI, result metadata and document content; the application stopwatch has a broader scope. See [the application guide](docs/tv3_ui_pro_v2.md) before comparing these measurements.

If time permits, a controlled comparison will evaluate whitespace tokenization against Vietnamese word segmentation while keeping the corpus, queries, labels, and other settings fixed.

### Acceptance Criteria

The assignment requires at least 100 valid documents, correct preprocessing/TF-IDF/cosine/ranking, a checked hand-calculated example, real inverted-index use, safe index lifecycle, clear error outcomes, at least 20 labeled queries with metrics, reproducible setup and a coherent final demonstration. [The acceptance record](docs/tv3_acceptance.md) distinguishes code, fixture tests, real PostgreSQL checks and observed browser actions. [The remaining steps](docs/tv3_remaining.md) identify work that still needs human decisions/evidence; passing code tests alone does not complete team acceptance.

## Team Responsibilities

| Role | Ownership | Evidence to Deliver |
| --- | --- | --- |
| TV1 — Data and Storage | Corpus, loaders, shared preprocessing, metadata, PostgreSQL, storage adapter | Source register, validated corpus, schema, ingestion tests, data-quality report |
| TV2 — Retrieval Engine | VSM, TF-IDF, inverted index, scoring, ranking, index lifecycle | Mathematical example, verified engine, artifact manifest, ranking explanations |
| TV3 — Application and Evaluation | Interface, integration, relevance labels, metrics, presentation | Working demo, evaluation collection, measured results, integration checklist |

All members contribute to integration, document their own modules, and prepare to explain the complete system. Contributor-specific implementation steps belong in `docs/`; this README describes the shared project.

## Development Workflow

The default branch contains shared foundations and reviewed changes. This integrated application handoff is on **`Dat`**; use that branch to reproduce the TV3 version. Keep this handoff's pushes on `Dat`. Other workstreams retain their own branches and review process.

| Workstream | Suggested Branch |
| --- | --- |
| Data and storage | `feat/data` |
| Retrieval engine | `feat/search-engine` |
| Application and evaluation in this handoff | `Dat` |

Keep commits focused on a coherent change. Pull requests should describe the resulting behavior, the verification performed, and any unresolved integration dependency. Before committing, inspect the changed files and check formatting:

```bash
git status
git diff --check
git diff
```

Never commit credentials, virtual environments, user uploads, or generated index files. Do not change shared preprocessing behavior or record contracts without coordinating with the affected workstream.

## Delivery Milestones

| Milestone | Completion Evidence |
| --- | --- |
| Shared foundation | Repository structure, agreed contracts, storage clarification, environment setup |
| First integrated path | Ten documents flow from ingestion through indexing to visible search results |
| Retrieval correctness | Hand-calculated example, real inverted-index usage, deterministic ranking |
| Corpus and lifecycle | At least 100 ready documents; verified additions, deletions, rebuilds, and restarts |
| Experimental evaluation | Fixed labels, per-query metrics, timing, and error analysis |
| Final delivery | Clean-environment run, coherent report and slides, rehearsed demonstration |

Early integration takes priority over finishing modules in isolation. The ten-document path is the first functional checkpoint.

## Limitations and Future Work

TF-IDF retrieves through shared lexical features. It may miss semantically related documents that use different words, and it does not model word order in the baseline unigram configuration. Extraction quality and Vietnamese segmentation also affect ranking.

Possible extensions after the baseline is verified include OCR, near-duplicate detection, alternative retrieval baselines, richer relevance metrics, and semantic retrieval. Each extension should be evaluated against the same documented collection rather than assumed to improve quality.

## References

- [Introduction to Information Retrieval — Manning, Raghavan, and Schütze](https://nlp.stanford.edu/IR-book/)
- [scikit-learn — TF-IDF term weighting](https://scikit-learn.org/stable/modules/feature_extraction.html#tfidf-term-weighting)
- [PostgreSQL documentation](https://www.postgresql.org/docs/)
- [Psycopg 3 documentation](https://www.psycopg.org/psycopg3/docs/)
- [Streamlit documentation](https://docs.streamlit.io/)

### Upgrade Corpus Preprocessing

```bash
python -m scripts.init_db
python -m scripts.reprocess_corpus
python -m scripts.export_corpus
```

See [preprocessing version lifecycle](docs/preprocessing_version.md). Reprocessing preserves document IDs and original files; it increments corpus revision once when documents change. TV2 must rebuild after that change.

### News Dataset Corpus

See [news corpus preparation and import](docs/news_corpus.md). Use `python -m scripts.export_corpus --corpus vietonline_news_200 --output reports/tv2_news_corpus.json` to keep the selected news articles separate from integration fixtures.

### PostgreSQL Text Storage

`documents.raw_text` stores extracted text for content viewing; `documents.clean_text` stores preprocessed features for indexing. Data-service reads use PostgreSQL, not processed files. Original files remain outside the DB for download and verification. Processed files are retained as compatibility caches; historical cache cleanup is separate work.

For an existing database:

```bash
python -m scripts.init_db
python -m scripts.backfill_document_text
```

Backfill validates original hashes, copies text in one transaction and validates the ready-text constraint. IDs and corpus revision remain unchanged because indexed text is unchanged. Future preprocessing changes update DB text and metadata in one transaction and increment revision. Original file writes still require cross-storage failure handling. A DB backup now includes searchable text; original-file downloads require transferring the storage folder separately.

### Transfer the Database

Use [the database transfer guide](docs/database_transfer.md) to share all 200 records with teammates. `python -m scripts.backup_database` creates a private dump; `python -m scripts.restore_database reports/smartdoc.dump` restores into an empty schema without overwriting existing work. Original files are transferred separately.

### Recovery and Storage Reconciliation

See [recovery procedures](docs/recovery.md). Use `python -m scripts.reconcile_storage` for a read-only audit; add `--quarantine` to move unreferenced files into recoverable storage. Retry failed same-hash inputs with `python -m scripts.ingest_documents path/to/file.pdf --retry-failed`. Ready records are never overwritten by retry.

### TV2 Retrieval Engine Tests

Run the TV2 retrieval-focused test suites from the repository root with the project virtual environment activated:

```powershell
python -m pytest -q tests/test_tfidf_engine.py tests/test_inverted_index.py tests/test_search_engine.py tests/test_index_manager.py tests/test_retrieval_engine.py
```

The full suite includes database-backed ingestion, recovery and upload tests that create/delete records. Run it through the guarded disposable-database runner, with Docker/PostgreSQL healthy and a configured role that can create a database:

```powershell
python -m scripts.test_tv3_isolated_database --all-tests
```

The runner creates separate PostgreSQL/storage state and checks the demo before/after. Do not run the full suite directly against the frozen evaluation/demo database. Read-only live search/explanation checks can be repeated with `python -m scripts.verify_tv3 --rebuild --repeats 5`; `--rebuild` writes only local index artifacts. Diagnostic timing in this smoke check does not replace the labeled-query experiment.

The retrieval-focused tests verify TF-IDF behavior, inverted-index retrieval, ranking, index management, and the public retrieval API. A passing test suite does not replace the hand-calculated TF-IDF/cosine example or the labeled-query evaluation required for final acceptance.

### Streamlit Application and Evaluation (Dat)

Install `requirements_tv3.txt`, start PostgreSQL, then run `python -m streamlit run app/main.py` from the repository root. The application uses the real TF-IDF retrieval service with Top-5/10/20, rank, cosine score, sources, a content reader and keyword-contribution explanations. Search supports session query/Top-K persistence, a 12-item replayable query history and UTF-8 CSV export with index/revision provenance. These session conveniences do not add accounts or durable personal history. Use **Xây lại chỉ mục** after a corpus change; mismatched revision/fingerprint/index versions cannot serve search results. Search checks PostgreSQL without using the library's 600-second display cache.

On Windows with Docker bound to `127.0.0.1:5433`, use `127.0.0.1` as the local `DATABASE_URL` host if `localhost` incurs an IPv6 connection timeout; keep credentials in the ignored `.env` file.

See [application setup](docs/tv3_ui_pro_v2.md), [acceptance evidence](docs/tv3_acceptance.md), [evaluation and independent relevance labeling](evaluation/README.md), [member report](docs/tv3_report.md) and [demo script](docs/tv3_demo.md). The committed query/label kit is a draft. Precision@5 and MRR@20 remain pending human review and actual labels.

For human labeling, run `python -m streamlit run app/review.py --server.address 127.0.0.1 --server.port 8503`. This separate local workspace reads original PostgreSQL text and writes explicit human decisions to the evaluation kit; it does not show retrieval scores/ranks or infer relevance. Review queries/protocol and validate coverage before running the metric CLI. Changing query meaning requires a new prepared kit with blank labels; never edit hashes to reuse labels for a different information need. The final report/slides will be consolidated after this work, at the user's request.
