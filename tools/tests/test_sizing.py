"""Pure parts of the S-013 sizing harness (tools/sizing): projection, JATS text, chunk counting,
statistics and the extrapolation. Synthetic fixtures, no network, stdlib only."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/sizing'))
from sizing import core, run  # noqa: E402

FIX = Path(__file__).parent / 'sizing-fixtures'
PAGE = json.loads((FIX / 'openalex-page.json').read_text())['results']
BULK = {'low': 0.4, 'central': 0.5, 'high': 0.8}


def factors(spread=0.2):
    base = {'chunks_350': 40, 'text_zst_bytes': 8e3, 'text_bytes': 30e3, 'meta_parquet_bytes': 600, 'refs': 40,
            'pdf_bytes': 5e5, 'jats_zst_bytes': 2e4, 'pdf_share': 0.4, 'bm25_ratio': 0.35, 'unresolved_share': 0.25}
    return {k: {'n': 100, 'mean': v, 'median': v, 'p90': v, 'ci95': [v * (1 - spread), v * (1 + spread)]} for k, v in base.items()}


class Sampling(unittest.TestCase):
    def test_route_follows_cascade_preference(self):
        self.assertEqual([core.route_of(r) for r in PAGE], ['jats', 'pdf', 'unresolved'])
        self.assertEqual(core.pmcid_of(PAGE[0]), 'PMC123')
        self.assertEqual(core.pmcid_of({'ids': {'pmcid': 'https://www.ncbi.nlm.nih.gov/pmc/articles/10022193'}}), 'PMC10022193')

    def test_manifest_counts_sources_and_ids(self):
        m = core.manifest(PAGE, 83, 'f', '2026-11-22', {'article': 2})
        self.assertEqual(m['work_ids'], ['W1', 'W2', 'W3'])
        self.assertEqual(m['per_source_top50'], {'Journal Two': 1, 'PubMed Central': 1, 'unknown': 1})
        self.assertEqual(m['routes'], {'jats': 1, 'pdf': 1, 'unresolved': 1})
        self.assertEqual(json.loads(core.dump_manifest(m)), m)

    def test_projection_keeps_only_hub_fields(self):
        p = core.project(PAGE[0])
        self.assertEqual(p['authorships'], [{'author': 'A1', 'name': 'X', 'institutions': ['I1']}])
        self.assertEqual(p['best_oa_location'], {'license': 'cc-by', 'pdf_url': None, 'landing_page_url': None, 'source': 'S1'})
        self.assertNotIn('abstract_inverted_index', p)

    def test_failed_pdf_fetches_take_the_mean_of_fetched_ones(self):
        rows = [{'route': 'pdf', 'pdf_bytes': 100}, {'route': 'pdf', 'pdf_bytes': 300},
                {'route': 'pdf', 'pdf_bytes': 0}, {'route': 'jats', 'pdf_bytes': 0}]
        self.assertEqual(core.pdf_contributions(rows), [100, 300, 200, 0])


class Text(unittest.TestCase):
    def test_jats_paragraphs_drop_tables_and_references(self):
        self.assertEqual(core.jats_paragraphs((FIX / 'sample.jats.xml').read_bytes()),
                         ['Synthetic abstract about nothing.', 'Introduction', 'First paragraph with a citation inside.', 'Kept figure caption.'])
        self.assertEqual(core.pdf_paragraphs('a  b\nc\n\n\n d\n'), ['a b c', 'd'])

    def test_chunk_packing(self):
        self.assertEqual([core.count_chunks(p, 350) for p in ([], [100] * 3, [200] * 3, [1000])], [0, 1, 3, 3])
        par = [37, 190, 410, 55, 300, 120, 80, 900]
        self.assertGreaterEqual(core.count_chunks(par, 300), core.count_chunks(par, 350))
        self.assertGreaterEqual(core.count_chunks(par, 350), core.count_chunks(par, 400))


class Stats(unittest.TestCase):
    def test_summary_is_seeded_and_brackets_the_mean(self):
        s = core.summarize(list(range(1, 101)), rounds=200)
        self.assertEqual((s['n'], s['mean'], s['median']), (100, 50.5, 50.5))
        self.assertAlmostEqual(s['p90'], 90.1)
        self.assertLess(s['ci95'][0], 50.5)
        self.assertGreater(s['ci95'][1], 50.5)
        self.assertEqual(core.summarize([1, 2, 3, 4, 10], 7, 100)['ci95'], core.summarize([1, 2, 3, 4, 10], 7, 100)['ci95'])


class Extrapolation(unittest.TestCase):
    def test_cases_use_ci_bounds(self):
        # Fails if the extrapolation uses the mean for every case: low < central < high must come
        # from the CI bounds of the measured factors, not only from the modelled constants.
        out, flat = core.extrapolate(20e6, factors(), BULK), core.extrapolate(20e6, factors(0.0), BULK)
        for key in ('B', 'R', 'hot_steady', 'warm_peak'):
            self.assertLess(out['low'][key], out['central'][key], key)
            self.assertLess(out['central'][key], out['high'][key], key)
        self.assertGreater(out['high']['vec'], flat['high']['vec'])
        self.assertLess(out['low']['text'], flat['low']['text'])
        self.assertLess(out['low']['idx'], flat['low']['idx'])

    def test_invariants(self):
        a, b = core.extrapolate(10e6, factors(), BULK), core.extrapolate(20e6, factors(), BULK)
        self.assertGreater(b['central']['B'], 1.5 * a['central']['B'])
        for c in core.CASES:
            x = b[c]
            self.assertGreater(x['warm_peak'], x['warm_steady'])
            self.assertGreater(x['hot_peak'], x['hot_steady'])
            self.assertLess(x['hot_steady'], x['warm_steady'])
            self.assertLess(x['hot_peak_int8'], x['hot_peak'])
            self.assertAlmostEqual(sum(x['raw'].values()), x['R'])
        self.assertAlmostEqual(b['central']['vec_int8'] / b['central']['vec'], 0.5 * (1 + 4 / 1024), places=6)

    def test_remainder_subtracts_the_first_models_vectors_and_text(self):
        # No measured text, chunks or metadata and full coverage: B is the modelled remainder, which is the
        # first model's per-paper size (1.75 TB / 7 M = 250 KB) less its 30 KB of vectors and 20 KB / 3.5 of
        # text, plus figure vectors (14.6 KB), patent vectors and text, and the drawings.
        z = {k: dict(v, mean=0.0, ci95=[0.0, 0.0]) for k, v in factors(0.0).items()}
        n = 10e6
        expect = n * (250e3 - 30e3 - 20e3 / 3.5) / 1e12 + n * 14.6e3 / 1e12 + 0.012 + 0.125 / 3.5 + 1.0
        self.assertAlmostEqual(core.extrapolate(n, dict(z, unresolved_share=z['pdf_share']), BULK)['central']['B'], expect, places=6)

    def test_hot_peak_adds_a_candidate_and_a_second_index_generation(self):
        x = core.extrapolate(20e6, factors(), BULK)['central']
        self.assertAlmostEqual(x['hot_peak'] - x['hot_steady'], x['hot_prod'] + x['idx'])

    def test_recompute_from_a_measurements_document(self):
        snap = {'openalex_jsonl': {'bytes': 7e11, 'works_records': 4e8, 'entities': {'works': 6e11}}, 'openalex_parquet': {'bytes': 8e11}}
        doc = {'population': {'all_types': 4e7, 'papers': 2.3e7, 'article': 2e7}, 'snapshots': snap, 'bases': {b: {'factors': factors()} for b in ('all_types', 'papers', 'article')}}
        run.extrapolations(doc)
        self.assertEqual(set(doc['bases']['article']['extrapolation']), set(core.CASES))
        self.assertGreater(doc['bases']['all_types']['extrapolation']['central']['B'], doc['bases']['article']['extrapolation']['central']['B'])
        self.assertLess(doc['model_scope_7M']['central']['B'], doc['bases']['article']['extrapolation']['central']['B'])


if __name__ == '__main__':
    unittest.main()
