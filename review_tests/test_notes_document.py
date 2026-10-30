import copy
import unittest

from notes_document import fingerprint, validate_page, validate_recap


def page():
    return {'schema': 'smartinis-notes-page/1', 'image_sha256': 'a'*64,
        'edge_clipping': False, 'relations': [], 'blocks': [
            {'id': 'B000001', 'kind': 'paragraph', 'bbox': [0,0,1,.5],
             'text': 'Non approvato. Check vrijdag; no decision yet.',
             'reviewed': True, 'excluded': False, 'uncertainties': []}]}


def recap(source):
    return {'schema': 'smartinis-notes-recap/1', 'page_sha256': fingerprint(source),
        'items': [{'kind': 'open-question', 'text': 'Check Friday; decision pending.',
            'evidence': [{'block_id': 'B000001', 'quote': 'no decision yet.'}]}]}


class NotesContracts(unittest.TestCase):
    def test_valid_mixed_language_source_and_grounded_recap(self):
        source = page()
        self.assertEqual(validate_recap(recap(source), source), fingerprint(recap(source)))

    def test_layout_edit_invalidates_recap(self):
        source = page()
        draft = recap(source)
        source['blocks'][0]['bbox'][2] = .9
        with self.assertRaisesRegex(ValueError, 'different source'):
            validate_recap(draft, source)

    def test_source_or_original_change_invalidates_recap(self):
        for key in ['text', 'image_sha256']:
            source = page()
            draft = recap(source)
            if key == 'text': source['blocks'][0]['text'] += ' Later edit.'
            else: source[key] = 'b'*64
            with self.assertRaises(ValueError): validate_recap(draft, source)

    def test_reject_unreviewed_excluded_and_crossed_out_evidence(self):
        for change in [{'reviewed': False}, {'excluded': True}, {'kind': 'crossout', 'excluded': True}]:
            source = page()
            source['blocks'][0].update(change)
            with self.assertRaises(ValueError): validate_recap(recap(source), source)

    def test_reject_wrong_quote_missing_block_and_missing_evidence(self):
        source = page()
        for evidence in [[{'block_id': 'B000001', 'quote': 'decision approved'}],
                         [{'block_id': 'B999999', 'quote': 'no decision yet.'}], []]:
            draft = recap(source)
            draft['items'][0]['evidence'] = evidence
            with self.assertRaises(ValueError): validate_recap(draft, source)

    def test_invalid_geometry_and_bool_coordinates(self):
        for box in [[0,0,0,1], [0,0,float('nan'),1], [0,0,2,1], [False,0,1,1]]:
            source = page()
            source['blocks'][0]['bbox'] = box
            with self.assertRaises(ValueError): validate_page(source)

    def test_duplicate_ids_and_invalid_relations(self):
        source = page()
        source['blocks'].append(copy.deepcopy(source['blocks'][0]))
        with self.assertRaises(ValueError): validate_page(source)
        source = page()
        source['relations'] = [{'kind': 'arrow', 'from': 'B000001', 'to': 'B000002',
            'reviewed': False, 'uncertainties': ['Endpoint unclear']}]
        with self.assertRaises(ValueError): validate_page(source)

    def test_crossout_requires_explicit_restoration(self):
        source = page()
        source['blocks'][0]['kind'] = 'crossout'
        with self.assertRaises(ValueError): validate_page(source)

    def test_unknown_model_fields_are_not_silently_accepted(self):
        source = page()
        source['blocks'][0]['approved'] = True
        with self.assertRaises(ValueError): validate_page(source)


if __name__ == '__main__':
    unittest.main()
