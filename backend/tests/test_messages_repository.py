import unittest

from backend.services.persistence.messages_repository import _decode_message


class MessageEnvelopeTests(unittest.TestCase):
    def test_only_assistant_rows_decode_valid_answer_envelopes(self):
        encoded = (
            "askmydoc:answer:v1:"
            '{"content":"Grounded answer","answer_status":"answered",'
            '"citations":[{"chunk_id":"chunk-1","excerpt":"Evidence"}]}'
        )

        self.assertEqual(
            _decode_message({"role": "assistant", "content": encoded}),
            {
                "role": "assistant",
                "content": "Grounded answer",
                "answer_status": "answered",
                "citations": [{"chunk_id": "chunk-1", "excerpt": "Evidence"}],
            },
        )

    def test_user_prefix_and_invalid_metadata_remain_plain_messages(self):
        user_content = 'askmydoc:answer:v1:{"content":"x","answer_status":"invalid"}'
        invalid_assistant_content = (
            "askmydoc:answer:v1:"
            '{"content":"Answer","answer_status":"invalid","citations":[]}'
        )

        self.assertEqual(
            _decode_message({"role": "user", "content": user_content}),
            {"role": "user", "content": user_content},
        )
        self.assertEqual(
            _decode_message({"role": "assistant", "content": invalid_assistant_content}),
            {"role": "assistant", "content": invalid_assistant_content},
        )


if __name__ == "__main__":
    unittest.main()
