# SmartDoc Search

**Vietnamese document retrieval with TF-IDF, cosine similarity, and PostgreSQL.**

SmartDoc Search is an academic project for the **Multimedia Database Systems** course. It brings document ingestion, Vietnamese text processing, feature indexing, ranked retrieval, and experimental evaluation into one system design.

The project is built around a concrete question: **given a Vietnamese query, which documents should appear first, and what evidence explains their ranking?** Its focus is a traceable path from source documents to searchable features, with retrieval results that can be checked against mathematical examples and human relevance judgments.

**Development stage:** Foundation and system design. The repository currently contains the shared directory structure and documentation. The ingestion pipeline, database schema, retrieval engine, and user interface are pending implementation. All capabilities and acceptance criteria below describe the intended system unless explicitly marked complete.

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

The implementation will address the four core requirements of the assignment:

| Requirement | Intended Implementation | Verification |
| --- | --- | --- |
| Text preprocessing | Shared Vietnamese normalization and tokenization for documents and queries | Documented before-and-after examples and edge-case tests |
| TF-IDF representation | A fitted vocabulary and weighted sparse document matrix | A small hand-calculated example checked against the configured library |
| Cosine similarity | Comparable query and document vectors in the same feature space | Numerical checks and full-corpus scoring comparisons |
| Result ranking | Descending similarity scores with deterministic tie handling and Top-K selection | Expected-order tests and retrieval evaluation |

The supporting work adds an inverted feature index, automatic metadata generation, PostgreSQL persistence, and a reproducible demonstration.

## Scope and User Experience

The initial corpus target is **100–200 valid Vietnamese documents**. The evaluation target is **20–30 queries with human relevance labels**. These are delivery targets, not completed dataset counts.

The planned application will let a user:

1. Upload a TXT file or a PDF with an extractable text layer.
2. Review automatically generated metadata and the ingestion outcome.
3. Enter a Vietnamese query and choose the number of results.
4. Inspect document titles, ranks, similarity scores, sources, and document content.
5. Examine selected preprocessing outputs, index postings, and term contributions to a result's score.

Image-only PDFs will receive an explicit unsupported-input message in the initial release. OCR is outside the baseline scope.

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

Documents and queries will use the same preprocessing configuration: Unicode normalization, lowercase conversion, whitespace and punctuation handling, Vietnamese word segmentation, and configurable stopword removal. Vietnamese diacritics and segmented multiword tokens must be preserved consistently.

Tokenizer selection, stopword sources, and configuration changes will be documented before the evaluation corpus is frozen.

### TF-IDF and the Vector Space Model

Each document is represented by term weights in a shared vocabulary. The baseline design uses raw term counts, smoothed inverse document frequency, and L2 normalization:

```text
idf(t)       = log((1 + N) / (1 + df(t))) + 1
weight(t, d) = count(t, d) × idf(t)
vector(d)    = weight(d) / ||weight(d)||₂
```

Here, `N` is the number of indexed documents and `df(t)` is the number containing term `t`. The final library settings and the hand-calculated example must use the same conventions.

Queries will be transformed using the fitted corpus vectorizer. They will not be fitted independently or added to the corpus during search.

### Candidate Selection and Ranking

The inverted index maps each vocabulary term to document IDs containing that feature. Query candidates are the **union** of the postings for the query's known terms, allowing partial term overlap.

```text
cosine(q, d) = (q · d) / (||q||₂ × ||d||₂)
```

For L2-normalized nonzero vectors, cosine similarity equals the dot product. The engine will rank positive-score results by descending score, then ascending document ID for ties. Fewer than `K` results may be returned when fewer documents have positive scores.

Empty queries, queries with no known vocabulary terms, and an empty corpus will have explicit outcomes. A similarity score measures lexical overlap under this representation; it is not a probability that a document is relevant.

### Ranking Explanations

For normalized vectors, each shared term contributes `q[t] × d[t]` to the score. Showing the largest contributions will make a selected result explainable and provide a useful demonstration of the underlying model.

## Data and Storage Design

### Document Metadata

The proposed `documents` table captures identity, provenance, storage references, and ingestion state.

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
| `text_ref` | Reference to processed text |
| `created_at` | Time of ingestion, distinct from publication time |
| `ingest_status` | `pending`, `ready`, or `failed` |
| `error_message` | Reason for failed ingestion |

Source references will be recorded when known rather than inferred. SHA-256 detects identical files; detection of near-duplicate content is outside the baseline duplicate policy.

### Storage Boundaries

| Layer | Stores |
| --- | --- |
| PostgreSQL | Metadata, document identity, ingestion state, and corpus revision |
| File storage | Original files and processed text |
| Index artifacts | Vectorizer, sparse TF-IDF matrix, ordered ID mapping, inverted index, and version manifest |

### Consistency Rules

- A document becomes `ready` only after the original file and processed text have been stored successfully.
- Only `ready` documents enter the searchable corpus; IDs remain stable after other documents are deleted.
- A successful change to the searchable corpus increments `corpus_revision`.
- The initial implementation rebuilds the complete index after additions or deletions.
- New artifacts are built and validated separately, then activated as one version.
- Search requires a matching corpus and index revision. Failed rebuilds must not expose a partially built index.

The baseline demo will serialize corpus mutations and index rebuilds. PostgreSQL transactions do not cover filesystem operations; ingestion and deletion services must handle failures across both storage layers.

## Module Contracts

These are planned integration contracts, not currently available functions.

### Data to Retrieval

`load_documents_for_index()` will return records in deterministic document-ID order:

```python
{
    "document_id": 42,
    "title": "Example document",
    "clean_text": "segmented and normalized Vietnamese text",
    "source_uri": None,
    "storage_ref": "originals/example.pdf",
}
```

The index builder will receive a corpus snapshot and its revision. It must preserve the row-to-document mapping when saving the matrix and related artifacts.

### Retrieval to Application

`search_query(query, top_k)` will return ranked records containing `document_id`, `score`, and `rank`. Validation and index-availability outcomes will be defined explicitly during implementation.

The application will resolve document metadata and content through data-service functions. UI code will not own SQL queries, preprocessing logic, or index construction.

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
├── artifacts/              # Generated index artifacts
├── reports/                # Generated data-quality and evaluation results
├── tests/                  # Unit and integration tests
│   └── __init__.py
└── docs/                   # Design notes and contributor checklists
```

Empty directories are retained with `.gitkeep`. Local uploads, processed text, generated artifacts, and report outputs are ignored by Git. Only small sample documents with appropriate sharing permission belong in `data/samples/`. Final report assets intended for review will be added explicitly in a documented location.

## Technology Choices

| Component | Selected or Planned Technology | Purpose |
| --- | --- | --- |
| Language | Python; target environment 3.11 or 3.12 | Data pipeline and retrieval services |
| Metadata database | PostgreSQL | Persistent document management |
| Database adapter | Psycopg 3 | Parameterized database access |
| Retrieval | scikit-learn and sparse matrices | TF-IDF and numerical scoring |
| Application | Streamlit | Interactive demonstration |
| PDF extraction | Library selection pending | Text-layer extraction |
| Vietnamese segmentation | Tokenizer selection pending | Shared document and query features |
| Collaboration | Git and GitHub | Version control and review |

Dependency versions will be pinned after compatibility testing. PostgreSQL metadata indexes and the retrieval inverted index serve different purposes; the latter is the feature index used for search.

## Getting Started

### Prerequisites

- Git and Python 3.11 or 3.12.
- Ubuntu: Docker Engine with the Compose plugin, or Docker Desktop.
- Windows: Docker Desktop running Linux containers.

Docker runs PostgreSQL; Python and the application run on the host. Each contributor has an independent local database. See [the Docker setup guide](docs/docker_setup.md) for installation references and troubleshooting.

### 1. Clone the Repository

```bash
git clone https://github.com/nhuquynh112/smartdoc-search.git
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

Open `.env` locally and replace both `CHANGE_ME` placeholders with the same password. For the initial setup, use letters and digits to avoid URI escaping. The database connection for host Python uses `localhost:5433`. Keep `.env` out of version control.

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
python3 -m venv .venv
source .venv/bin/activate
python --version
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
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

Ubuntu setup has been demonstrated with Python **3.12.3**, a PostgreSQL **16.15** container reporting healthy, and a container-local query returning `smartdoc` / `smartdoc_app`. Host-side Python authentication, schema initialization, and Windows execution remain to be verified.

### Runtime Setup Roadmap

The following setup assets are pending:

- `requirements.txt` with verified dependencies.
- Database schema and initialization command.
- Ingestion, index-building, evaluation, and application entry points.

Runnable commands will be documented as these components are implemented and verified from a clean environment. Keep the actual `.env` local and use configurable paths rather than machine-specific absolute paths.

## Evaluation and Verification

### Evaluation Collection

The experiment will use a fixed corpus, documented queries, and human-assigned relevance judgments. Labels will be assigned independently of cosine scores and reviewed when annotators disagree.

Queries will cover individual terms, multiword information needs, Vietnamese compounds, ambiguous terms, and lexical limitations such as synonyms. Queries with no relevant documents in the corpus will be reported separately as behavioral checks.

### Metrics

| Measure | Convention |
| --- | --- |
| Precision@5 | Relevant documents in the first five positions divided by five; missing positions count as nonrelevant |
| MRR | Mean reciprocal rank of the first relevant result; zero when no relevant result is retrieved |
| Query latency | Measured after loading the index, with the timed steps and environment specified |
| Index build time | Reported separately from query latency |

The MRR evaluation depth must be fixed before experiments; truncated evaluation will be labeled `MRR@K`. Reports will include per-query results, aggregate metrics, corpus size, preprocessing configuration, and representative failure cases. No benchmark scores are claimed at the scaffold stage.

If time permits, a controlled comparison will evaluate whitespace tokenization against Vietnamese word segmentation while keeping the corpus, queries, labels, and other settings fixed.

### Acceptance Criteria

- [ ] At least 100 valid documents with recorded provenance where available.
- [ ] All four assignment requirements are implemented and demonstrated.
- [ ] A hand-calculated TF-IDF and cosine example matches the program within a documented tolerance.
- [ ] Inverted-index retrieval agrees with full-corpus scoring for positive-score results.
- [ ] Stable document IDs and consistent artifact versions survive additions, deletions, and restarts.
- [ ] Invalid files, duplicates, empty queries, unknown terms, and rebuild failures have clear outcomes.
- [ ] At least 20 labeled queries support documented Precision@5 and MRR results.
- [ ] Setup and execution are reproducible from a clean environment.
- [ ] The final demonstration, report, and slides agree with the implemented system.

## Team Responsibilities

| Role | Ownership | Evidence to Deliver |
| --- | --- | --- |
| TV1 — Data and Storage | Corpus, loaders, shared preprocessing, metadata, PostgreSQL, storage adapter | Source register, validated corpus, schema, ingestion tests, data-quality report |
| TV2 — Retrieval Engine | VSM, TF-IDF, inverted index, scoring, ranking, index lifecycle | Mathematical example, verified engine, artifact manifest, ranking explanations |
| TV3 — Application and Evaluation | Interface, integration, relevance labels, metrics, presentation | Working demo, evaluation collection, measured results, integration checklist |

All members contribute to integration, document their own modules, and prepare to explain the complete system. Contributor-specific implementation steps belong in `docs/`; this README describes the shared project.

## Development Workflow

The default branch contains shared foundations and reviewed changes. Contributors develop their modules on feature branches and submit pull requests before merging.

| Workstream | Suggested Branch |
| --- | --- |
| Data and storage | `feat/data` |
| Retrieval engine | `feat/search-engine` |
| Application and evaluation | `feat/app-evaluation` |

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
