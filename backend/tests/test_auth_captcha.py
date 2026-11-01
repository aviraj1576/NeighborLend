import os
import sys
import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import CaptchaChallenge
from app.services.auth import issue_captcha, verify_captcha


class TestCaptchaChallenges(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        CaptchaChallenge.__table__.create(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def issue_with_answer(self):
        challenge = issue_captcha(self.session)
        first, second = challenge["question"].split(" = ?")[0].split(" + ")
        return challenge, int(first) + int(second)

    def test_correct_answer_is_accepted_once(self):
        challenge, answer = self.issue_with_answer()

        self.assertTrue(verify_captcha(challenge["captcha_id"], str(answer), self.session))
        self.assertFalse(verify_captcha(challenge["captcha_id"], answer, self.session))

    def test_incorrect_answer_consumes_challenge(self):
        challenge, answer = self.issue_with_answer()

        self.assertFalse(verify_captcha(challenge["captcha_id"], answer + 1, self.session))
        self.assertFalse(verify_captcha(challenge["captcha_id"], answer, self.session))

    def test_expired_challenge_is_rejected(self):
        challenge, answer = self.issue_with_answer()
        stored_challenge = self.session.get(CaptchaChallenge, challenge["captcha_id"])
        stored_challenge.expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.session.commit()

        self.assertFalse(verify_captcha(challenge["captcha_id"], answer, self.session))


if __name__ == "__main__":
    unittest.main()
