"""Shared Vietnamese pipeline. Defaults preserve accents and do not remove stopwords."""
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from underthesea import word_tokenize

@dataclass(frozen=True)
class PreprocessingConfig:
    segment_words: bool = True
    remove_stopwords: bool = False
    stopwords: frozenset[str] = frozenset()

@dataclass(frozen=True)
class PreprocessingResult:
    clean_text: str
    tokens: tuple[str, ...]
    word_count: int  # Before stopword removal.

def normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFC', text).lower()
    # Punctuation becomes a boundary. Accents and numbers remain intact.
    text = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in text)
    return re.sub(r'\s+', ' ', text).strip()

def preprocess_document(text: str, config: PreprocessingConfig | None = None) -> PreprocessingResult:
    config = config or PreprocessingConfig()
    normalized = normalize_text(text)
    if not normalized:
        return PreprocessingResult('', (), 0)
    if config.segment_words:
        # Retain sentence boundaries until segmentation; remove punctuation per sentence.
        sentences = re.split(r'[.!?。！？;\n]+', unicodedata.normalize('NFC', text))
        tokens = tuple(token for sentence in sentences
                       if (clean := normalize_text(sentence))
                       for token in word_tokenize(clean, format='text').split())
    else:
        tokens = tuple(normalized.split())
    count = len(tokens)
    if config.remove_stopwords:
        if not config.stopwords:
            raise ValueError('Provide an explicit stopword set when enabling removal.')
        # Stopwords use the same segmented token representation, e.g. "có_thể".
        tokens = tuple(t for t in tokens if t not in config.stopwords)
    return PreprocessingResult(' '.join(tokens), tokens, count)

def preprocess_text(text: str, config: PreprocessingConfig | None = None) -> str:
    """TV2 must call this with the same config for document and query text."""
    return preprocess_document(text, config).clean_text


@lru_cache(maxsize=1)
def _dependency_versions():
    from importlib.metadata import version
    return tuple(version(name) for name in ('underthesea', 'underthesea_core', 'pypdf', 'fonttools'))


def pipeline_manifest(config: PreprocessingConfig | None = None) -> dict:
    """Fingerprint code rules and dependencies, including the actual stopword set."""
    import hashlib
    import json
    import unicodedata
    config = config or PreprocessingConfig()
    tokenizer_version, core_version, pdf_version, font_version = _dependency_versions()
    settings = {
        'rules_version': 1,  # Increment when normalization/segmentation rules change.
        'unicode': 'NFC', 'unicode_database': unicodedata.unidata_version,
        'lowercase': True, 'sentence_boundaries': '[.!?。！？;\\n]+',
        'segment_words': config.segment_words,
        'tokenizer': 'underthesea' if config.segment_words else 'whitespace',
        'underthesea_version': tokenizer_version,
        'underthesea_core_version': core_version,
        'pdf_extractor_version': pdf_version,
        'fonttools_version': font_version,
        'remove_stopwords': config.remove_stopwords,
        'stopwords': sorted(config.stopwords) if config.remove_stopwords else [],
    }
    digest = hashlib.sha256(json.dumps(settings,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'fingerprint': digest, 'settings': settings}
