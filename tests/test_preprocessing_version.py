import unittest
from smartdoc.preprocessing import pipeline_manifest, PreprocessingConfig

class VersionTests(unittest.TestCase):
    def test_stable_and_config_sensitive(self):
        baseline = pipeline_manifest()
        self.assertEqual(baseline, pipeline_manifest())
        changed = pipeline_manifest(PreprocessingConfig(segment_words=False))
        self.assertNotEqual(baseline['fingerprint'], changed['fingerprint'])
        a = pipeline_manifest(PreprocessingConfig(remove_stopwords=True,stopwords=frozenset({'và','là'})))
        b = pipeline_manifest(PreprocessingConfig(remove_stopwords=True,stopwords=frozenset({'là','và'})))
        self.assertEqual(a,b)
        self.assertNotEqual(a['fingerprint'],baseline['fingerprint'])
