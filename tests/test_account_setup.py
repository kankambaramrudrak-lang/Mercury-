import unittest

from core.account_setup import setup_twilio, setup_whatsapp


class FakeSecretStore:
    def __init__(self):
        self.values = {}

    def get(self, username):
        return self.values.get(username)

    def set(self, username, value):
        self.values[username] = value


class AccountSetupTests(unittest.TestCase):
    def test_whatsapp_secrets_are_stored_without_echoing_them(self):
        store = FakeSecretStore()
        prompts = iter(("987654321", "private-access-token", "app-secret", "verify-token"))
        secret_prompts = []

        result = setup_whatsapp(
            store,
            input_fn=lambda _prompt: next(prompts),
            secret_input=lambda prompt: secret_prompts.append(prompt) or next(prompts),
        )

        self.assertIn("stored in Windows", result)
        self.assertEqual(
            store.values,
            {
                "phone_number_id": "987654321",
                "access_token": "private-access-token",
                "app_secret": "app-secret",
                "verify_token": "verify-token",
            },
        )
        self.assertEqual(
            secret_prompts,
            [
                "Meta WhatsApp access token (hidden): ",
                "Meta app secret for inbound webhooks (hidden, optional): ",
                "Webhook verification token (hidden, optional): ",
            ],
        )

    def test_twilio_token_is_stored_with_validated_account_fields(self):
        store = FakeSecretStore()
        prompts = iter(("AC" + "a" * 32, "+14155550987"))
        result = setup_twilio(
            store,
            input_fn=lambda _prompt: next(prompts),
            secret_input=lambda _prompt: "private-auth-token",
        )

        self.assertIn("stored in Windows", result)
        self.assertEqual(store.values["auth_token"], "private-auth-token")
        self.assertNotIn("private-auth-token", result)

    def test_invalid_credentials_are_not_saved(self):
        store = FakeSecretStore()
        prompts = iter(("bad", "token", "bad-number"))

        result = setup_twilio(
            store,
            input_fn=lambda _prompt: next(prompts),
            secret_input=lambda _prompt: next(prompts),
        )

        self.assertIn("invalid", result)
        self.assertEqual(store.values, {})


if __name__ == "__main__":
    unittest.main()
