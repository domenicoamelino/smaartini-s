import unittest
from test_notes_backend import page
from notes_risk import annotate


class Risk(unittest.TestCase):
    def test_confident_model_still_gets_negation_and_number_flags(self):
        source=page(False);source['blocks'][0]['text']='Do not pay 300 euro.'
        result=annotate(source)
        self.assertEqual(len(result['blocks'][0]['uncertainties']),2)
        self.assertFalse(source['blocks'][0]['uncertainties'])
    def test_name_patterns_are_explainable_not_probability_scores(self):
        source=page(False);source['blocks'][0]['text']='Aster, Vela and Nora will check.'
        self.assertIn('Possible names',annotate(source)['blocks'][0]['uncertainties'][0])
    def test_list_index_alone_does_not_create_number_flag(self):
        source=page(False);source['blocks'][0]['text']='1) discuss the proposal'
        self.assertEqual(annotate(source)['blocks'][0]['uncertainties'],[])
    def test_triage_is_repeatable_and_does_not_duplicate_flags(self):
        source=page(False);source['blocks'][0]['text']='niet bevestigd'
        self.assertEqual(annotate(annotate(source)),annotate(source))


if __name__=='__main__':unittest.main()
