"""Upgrade ready documents to the current default preprocessing fingerprint."""
import json
from smartdoc.reprocessing import reprocess_corpus

def main():
    result = reprocess_corpus()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['updated_documents']:
        print('Corpus changed: TV2 must rebuild the index and replace the old export.')
    else: print('Corpus is already up to date; revision unchanged.')

if __name__ == '__main__': main()
