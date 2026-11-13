import unittest,random
from backend.pravo_tech_casebook_api_service.mock_data import generate_mock_casebook_response, _query_variants

class SourceContractTests(unittest.TestCase):
    def test_mock_returns_dictionary(self): self.assertIsInstance(generate_mock_casebook_response("Demo",count=2,rng=random.Random(7)),dict)
    def test_zero_count(self):
        result=generate_mock_casebook_response("Demo",count=0,rng=random.Random(7))
        self.assertIn("items",result);self.assertEqual(result["items"],[])
    def test_inn_normalization(self): self.assertIn("1234567890",_query_variants("ИНН: 1234567890","inn"))
    def test_empty_query(self): self.assertEqual(_query_variants("","fio"),[""])

    def test_fixed_seed_and_clock_are_reproducible(self):
        from datetime import datetime
        left=generate_mock_casebook_response("Demo",count=3,rng=random.Random(7),reference_time=datetime(2026,1,1))
        right=generate_mock_casebook_response("Demo",count=3,rng=random.Random(7),reference_time=datetime(2026,1,1))
        self.assertEqual(left,right)
