import unittest

from main import reply_for


class ReplyTests(unittest.TestCase):
    def test_greetings_receive_hercules_reply(self):
        for greeting in ("hello", "Hi!", "hey there", "good morning"):
            with self.subTest(greeting=greeting):
                self.assertEqual(reply_for(greeting), "Hello! I'm Hercules.")

    def test_non_greetings_get_supported_scope_reply(self):
        self.assertIn("only knows simple greetings", reply_for("what is the weather"))
        self.assertIn("only knows simple greetings", reply_for("this is a test"))


if __name__ == "__main__":
    unittest.main()
