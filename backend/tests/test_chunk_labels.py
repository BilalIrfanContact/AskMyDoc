import unittest

from backend.services.chunk_labels import label_document


class ChunkLabelsTestCase(unittest.TestCase):
    def test_label_document_titles_the_document_and_labels_each_chunk(self):
        def generate(prompt):
            if prompt.startswith("Below is the start"):
                return "Acme Corp, Form 10-K"
            return "Label for " + prompt.rsplit("Passage:\n", 1)[1]

        labels = label_document(["alpha", "beta"], generate)

        self.assertEqual(labels.title, "Acme Corp, Form 10-K")
        self.assertEqual(labels.labels, ["Label for alpha", "Label for beta"])

    def test_a_failed_label_is_empty_instead_of_failing_indexing(self):
        def generate(prompt):
            if "Passage:\nbeta" in prompt:
                raise RuntimeError("rate limited")
            return "ok"

        labels = label_document(["alpha", "beta"], generate)

        self.assertEqual(labels.labels, ["ok", ""])


if __name__ == "__main__":
    unittest.main()
