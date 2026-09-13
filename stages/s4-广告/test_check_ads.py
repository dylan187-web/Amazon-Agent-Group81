"""离线回归：交接错误、缺失值、作用范围、预算改变与快照保护。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from check_ads import read_s3, render, validate

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


class AdsTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads((HERE / "sample_draft.json").read_text(encoding="utf-8"))
        self.s3 = read_s3(REPO / "samples" / "s3_listing.md")

    def errors(self):
        return {e["code"] for e in validate(self.d, self.s3)}

    def test_sample(self):
        self.assertEqual(self.errors(), set())
        text = render(self.d)
        for section in ("针对候选：C1", "投放词", "预算", "否定预案", "新调用 0 次", "全部虚构"):
            self.assertIn(section, text)

    def test_wrong_candidate(self):
        self.d["meta"]["candidate"] = "C99"
        self.assertIn("CANDIDATE", self.errors())

    def test_candidate_with_s3_annotation(self):
        # S3 v0.3 真实产出写成「C1（对标 B0…，…）」，只比较候选编号
        self.s3["meta"]["candidate"] = "C1（对标 B0SAMPLE01，做针对买家关心点的改良款）"
        self.assertNotIn("CANDIDATE", self.errors())
        self.d["meta"]["candidate"] = "C12"
        self.assertIn("CANDIDATE", self.errors())

    def test_keyword_outside_s3(self):
        self.d["ads"][0]["keyword"] = "unlisted drawer trays"
        self.assertIn("KEYWORD_SOURCE", self.errors())

    def test_singular_is_not_same_source(self):
        self.d["ads"][0]["keyword"] += "s"
        self.assertIn("KEYWORD_SOURCE", self.errors())

    def test_normalize_case_and_space(self):
        self.d["ads"][0]["keyword"] = " BAMBOO  DRAWER ORGANIZER "
        self.assertEqual(self.errors(), set())

    def test_budget_sum(self):
        self.d["budgets"][0]["percent"] = 61
        self.assertIn("BUDGET", self.errors())

    def test_strategy_weights_not_hardcoded(self):
        for row, percent in zip(self.d["budgets"], [40, 40, 20]):
            row["percent"] = percent
        self.assertEqual(self.errors(), set())

    def test_empty_group_redistribution(self):
        self.d["ads"][2]["match"] = "词组"
        self.assertIn("EMPTY_GROUP", self.errors())
        for row, percent in zip(self.d["budgets"], [66.67, 33.33, 0]):
            row["percent"] = percent
        self.assertEqual(self.errors(), set())

    def test_missing_bid_is_valid_but_null_zero_blank_are_not(self):
        self.assertEqual(self.errors(), set())
        for bad in (None, 0, "", -1, True, "NaN"):
            with self.subTest(bad=bad):
                self.d["ads"][0]["bid"] = bad
                self.assertIn("BID", self.errors())

    def test_missing_bid_needs_reason(self):
        del self.d["ads"][0]["missing_reason"]
        self.assertIn("FIELD", self.errors())

    def test_required_fields(self):
        del self.d["meta"]["data_period"]
        self.assertIn("FIELD", self.errors())

    def test_unaccounted_keyword(self):
        self.d["deferred"].pop()
        self.assertIn("COVERAGE", self.errors())

    def test_same_word_different_match_allowed(self):
        ad = copy.deepcopy(self.d["ads"][0])
        ad["match"] = "广泛"
        self.d["ads"].append(ad)
        self.assertEqual(self.errors(), set())

    def test_exact_negative_conflict(self):
        self.d["negatives"] = [{"keyword": "bamboo drawer organizer", "match": "否定精准",
                               "scopes": ["全部"], "reason": "test"}]
        self.assertIn("NEGATIVE_CONFLICT", self.errors())

    def test_phrase_negative_conflict_and_scope(self):
        self.d["negatives"] = [{"keyword": "drawer organizer", "match": "否定词组",
                               "scopes": ["精准"], "reason": "test"}]
        self.assertIn("NEGATIVE_CONFLICT", self.errors())
        self.d["negatives"][0]["scopes"] = ["广泛"]
        self.assertEqual(self.errors(), set())

    def test_negative_whole_phrase_not_substring(self):
        self.d["negatives"][0]["keyword"] = "tray"
        self.assertIn("NEGATIVE_CONFLICT", self.errors())
        self.d["negatives"][0]["keyword"] = "ray"
        self.assertEqual(self.errors(), set())

    def test_no_invented_budget_amount(self):
        self.d["budgets"][0]["amount"] = 12
        self.assertIn("BUDGET", self.errors())

    def test_user_budget_and_mismatch(self):
        self.d["daily_budget"] = {"amount": 20, "currency": "USD"}
        for row, amount in zip(self.d["budgets"], [12, 6, 2]):
            row["amount"] = amount
        self.assertEqual(self.errors(), set())
        self.d["budgets"][0]["amount"] = 14
        self.assertIn("BUDGET", self.errors())

    def test_malformed_s3_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.md"
            p.write_text("针对候选：C1", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_s3(p)

    def test_malformed_draft_collections(self):
        self.d["ads"] = "bad"
        self.assertIn("FIELD", self.errors())

    def test_malformed_budget_match(self):
        self.d["budgets"][0]["match"] = []
        self.assertIn("BUDGET", self.errors())




class SnapshotTests(unittest.TestCase):
    def setUp(self):
        from check_ads import sha
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name)
        self.d = json.loads((HERE / "sample_draft.json").read_text(encoding="utf-8"))
        (self.run / "s3_listing.md").write_text((REPO / "samples" / "s3_listing.md").read_text(encoding="utf-8"), encoding="utf-8")
        self.refresh()

    def refresh(self):
        from check_ads import sha
        (self.run / "s4_draft.json").write_text(json.dumps(self.d, ensure_ascii=False), encoding="utf-8")
        report = {"passed": True, "errors": [], "draft_sha256": sha(self.run / "s4_draft.json"),
                  "s3_sha256": sha(self.run / "s3_listing.md")}
        (self.run / "s4_validation.json").write_text(json.dumps(report), encoding="utf-8")
        (self.run / "s4_广告.md").write_text(render(self.d), encoding="utf-8")

    def test_same_input_strategy_comparison_and_preserve_baseline(self):
        from review_iteration import save
        from check_ads import sha
        first = save(self.run, "v1")
        before = sha(first / "s4_draft.json")
        for row, pct in zip(self.d["budgets"], [40, 40, 20]):
            row["percent"] = pct
        self.refresh()
        second = save(self.run, "v2", "v1")
        text = (second / "comparison.md").read_text(encoding="utf-8")
        self.assertIn("S3 输入与缓存相同", text)
        self.assertIn("变化", text)
        self.assertEqual(sha(first / "s4_draft.json"), before)

    def test_no_overwrite(self):
        from review_iteration import save
        save(self.run, "v1")
        with self.assertRaises(ValueError):
            save(self.run, "v1")

    def test_stale_validation_rejected(self):
        from review_iteration import save
        self.d["notes"].append("changed")
        (self.run / "s4_draft.json").write_text(json.dumps(self.d), encoding="utf-8")
        with self.assertRaises(ValueError):
            save(self.run, "v1")

    def test_stale_render_rejected(self):
        from review_iteration import save
        (self.run / "s4_广告.md").write_text("old report", encoding="utf-8")
        with self.assertRaises(ValueError):
            save(self.run, "v1")

    def test_path_traversal_rejected(self):
        from review_iteration import save
        with self.assertRaises(ValueError):
            save(self.run, "../escape")

    def test_changed_cache_not_attributed_to_strategy(self):
        from review_iteration import save
        save(self.run, "v1")
        (self.run / "raw").mkdir()
        (self.run / "raw" / "new_source.json").write_text("{}", encoding="utf-8")
        second = save(self.run, "v2", "v1")
        self.assertIn("不能只归因于广告策略", (second / "comparison.md").read_text(encoding="utf-8"))

    def test_changed_user_budget_not_attributed_to_strategy(self):
        from review_iteration import save
        save(self.run, "v1")
        self.d["daily_budget"] = {"amount": 20, "currency": "USD"}
        for row, amount in zip(self.d["budgets"], [12, 6, 2]):
            row["amount"] = amount
        self.refresh()
        second = save(self.run, "v2", "v1")
        self.assertIn("不能只归因于广告策略", (second / "comparison.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
