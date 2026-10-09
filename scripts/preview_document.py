"""Preview extracted text and features without inserting database records."""
import argparse
from smartdoc.document_loader import DocumentLoadError, load_document
from smartdoc.preprocessing import PreprocessingConfig, preprocess_document

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    parser.add_argument('--whitespace', action='store_true', help='Disable segmentation for the evaluation baseline.')
    args = parser.parse_args()
    try:
        raw = load_document(args.path)
        result = preprocess_document(raw, PreprocessingConfig(segment_words=not args.whitespace))
    except (DocumentLoadError, ValueError) as exc:
        parser.exit(1, f'Cannot process document: {exc}\n')
    print(f'Token count before stopword removal: {result.word_count}')
    print('Extracted text (first 500 characters):\n' + raw[:500])
    print('Processed text (first 500 characters):\n' + result.clean_text[:500])

if __name__ == '__main__': main()
