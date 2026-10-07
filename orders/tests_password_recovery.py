"""Self-service Forgot Password / Reset Password (orders/password_recovery.py).

Enabled only for dine_flash, dine_flash_buffet, hospital_flash.
Recovery email: Super Admin -> User.email; Company Admin -> AdminOutlet.customer_email.
"""
import contextlib
import io
import logging
import re
import smtplib
from datetime import datetime, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from orders import password_recovery
from orders.password_recovery import (
    GENERIC_SENT_MESSAGE,
    company_admin_token_generator,
)
from vendors.models import AdminOutlet, UserProfile

OLD_PASSWORD = "Old-Passw0rd!x"
NEW_PASSWORD = "N3w-Strong-Passw0rd!"
LINK_RE = re.compile(r"(\S*/reset-password/)#uid=([^&\s]+)&token=(\S+)")


def make_company_admin(username, customer_email, customer_id):
    user = User.objects.create_user(username=username, password=OLD_PASSWORD, is_staff=True)
    AdminOutlet.objects.create(
        user=user,
        customer_name=f"{username} Co",
        customer_email=customer_email,
        customer_id=customer_id,
    )
    return user


def make_super_admin(username, email):
    return User.objects.create_superuser(username=username, email=email, password=OLD_PASSWORD)


class RecoveryTestBase(TestCase):
    def setUp(self):
        cache.clear()
        patcher = patch.object(password_recovery, "_run_in_background", side_effect=lambda fn: fn())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = Client()
        self.forgot_url = reverse("forgot_password")
        self.reset_url = reverse("reset_password")

    def request_reset(self, username, client=None):
        return (client or self.client).post(self.forgot_url, {"username": username})

    def last_link(self):
        match = LINK_RE.search(mail.outbox[-1].body)
        self.assertIsNotNone(match, "reset link missing from email body")
        return match.group(2), match.group(3)

    def open_link(self, uid, token, client=None):
        client = client or self.client
        response = client.post(self.reset_url, {"action": "verify", "uid": uid, "token": token})
        self.assertEqual(response.status_code, 302)
        return client.get(self.reset_url)

    def set_password(self, p1, p2=None, client=None):
        return (client or self.client).post(
            self.reset_url,
            {"action": "set", "new_password1": p1, "new_password2": p1 if p2 is None else p2},
        )

    def assertResetForm(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="new_password1"')

    def assertInvalidLink(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid or has expired")
        self.assertNotContains(response, 'name="new_password1"')


@override_settings(PROJECT_NAME="dine_flash")
class ForgotPasswordRequestTests(RecoveryTestBase):
    def setUp(self):
        super().setUp()
        self.company = make_company_admin("acme_admin", "owner@acme.example", 1001)
        self.super_admin = make_super_admin("root_admin", "root@ops.example")

    def test_company_admin_email_goes_to_customer_email(self):
        response = self.request_reset("acme_admin")
        self.assertRedirects(response, self.forgot_url + "?sent=1", fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@acme.example"])
        self.company.refresh_from_db()
        self.assertEqual(self.company.email, "")  # never synchronised into User.email

    def test_super_admin_email_goes_to_user_email(self):
        self.request_reset("root_admin")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["root@ops.example"])

    def test_superuser_linked_to_company_uses_user_email_not_customer_email(self):
        linked = make_super_admin("linked_root", "linked@ops.example")
        AdminOutlet.objects.create(user=linked, customer_name="Linked", customer_email="company@x.example")
        self.request_reset("linked_root")
        self.assertEqual(mail.outbox[0].to, ["linked@ops.example"])

    def test_unknown_username_sends_nothing(self):
        self.request_reset("nobody_here")
        self.assertEqual(len(mail.outbox), 0)

    def test_company_admin_with_missing_or_invalid_customer_email_sends_nothing(self):
        make_company_admin("no_mail_co", "", 1002)
        make_company_admin("bad_mail_co", "not-an-email", 1003)
        with self.assertNoLogs("orders.password_recovery", level="DEBUG"):
            for username in ("no_mail_co", "bad_mail_co"):
                response = self.request_reset(username)
                self.assertEqual(response["Location"], self.forgot_url + "?sent=1")
        self.assertEqual(len(mail.outbox), 0)

    def test_super_admin_with_missing_email_sends_nothing(self):
        make_super_admin("root_no_mail", "")
        with self.assertNoLogs("orders.password_recovery", level="DEBUG"):
            response = self.request_reset("root_no_mail")
        self.assertEqual(response["Location"], self.forgot_url + "?sent=1")
        self.assertEqual(len(mail.outbox), 0)

    def test_ineligible_accounts_send_nothing(self):
        staff = User.objects.create_user(username="kitchen_1", password=OLD_PASSWORD)
        UserProfile.objects.create(user=staff, role="utility_user", admin_outlet=self.company.admin_outlet)
        inactive = make_company_admin("inactive_co", "inactive@x.example", 1004)
        inactive.is_active = False
        inactive.save()
        self.request_reset("kitchen_1")
        self.request_reset("inactive_co")
        self.assertEqual(len(mail.outbox), 0)

    def test_generic_response_is_identical_for_every_case(self):
        make_company_admin("no_mail_co", "", 1002)
        make_super_admin("root_no_mail", "")
        pages = []
        for username in ("acme_admin", "root_admin", "nobody_here", "no_mail_co", "root_no_mail"):
            response = self.request_reset(username)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], self.forgot_url + "?sent=1")
            pages.append(self.client.get(response["Location"]).content)
        self.assertEqual(len(set(pages)), 1)
        self.assertIn(GENERIC_SENT_MESSAGE.encode(), pages[0])

    def test_recovery_email_never_returned(self):
        response = self.request_reset("acme_admin")
        page = self.client.get(response["Location"])
        for body in (response.content, page.content):
            self.assertNotIn(b"owner@acme.example", body)
            self.assertNotIn(b"acme.example", body)

    def test_empty_username_is_rejected_without_email(self):
        response = self.request_reset("   ")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter your username.")
        self.assertEqual(len(mail.outbox), 0)

    def test_username_rate_limit_caps_emails(self):
        for _ in range(5):
            response = self.request_reset("acme_admin")
            self.assertEqual(response["Location"], self.forgot_url + "?sent=1")
        self.assertEqual(len(mail.outbox), password_recovery.FORGOT_PASSWORD_USERNAME_LIMIT[0])

    def test_ip_rate_limit_returns_429(self):
        with patch.object(password_recovery, "FORGOT_PASSWORD_IP_LIMIT", (2, 60)):
            self.request_reset("nobody_1")
            self.request_reset("nobody_2")
            response = self.request_reset("acme_admin")
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many requests", status_code=429)
        self.assertEqual(len(mail.outbox), 0)

    def test_link_carries_token_in_fragment_only(self):
        self.request_reset("acme_admin")
        match = LINK_RE.search(mail.outbox[0].body)
        page_url = match.group(1)
        self.assertTrue(page_url.endswith(self.reset_url))
        self.assertNotIn(match.group(3), page_url)

    @override_settings(PASSWORD_RESET_BASE_URL="https://portal.example.com/")
    def test_link_uses_configured_base_url(self):
        self.request_reset("acme_admin")
        self.assertIn(f"https://portal.example.com{self.reset_url}#uid=", mail.outbox[0].body)

    def test_csrf_is_enforced(self):
        response = self.request_reset("acme_admin", client=Client(enforce_csrf_checks=True))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_privacy_headers(self):
        response = self.client.get(self.forgot_url)
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertIn("no-store", response["Cache-Control"])


@override_settings(PROJECT_NAME="dine_flash")
class PasswordRecoveryLoggingTests(RecoveryTestBase):
    """Only non-identifying operational failures are logged, via the project's log config."""

    def setUp(self):
        super().setUp()
        make_company_admin("acme_admin", "owner@acme.example", 1001)

    def test_logger_uses_project_handler_not_stderr_fallback(self):
        log = logging.getLogger("orders.password_recovery")
        self.assertFalse(log.propagate)
        self.assertEqual(log.level, logging.ERROR)
        files = [getattr(h, "baseFilename", "") for h in log.handlers]
        self.assertTrue(any(f.endswith("orders.log") for f in files), files)

    def test_failed_email_send_is_logged_by_type_only(self):
        error = smtplib.SMTPRecipientsRefused({"owner@acme.example": (550, b"mailbox unavailable")})
        with patch.object(password_recovery, "send_mail", side_effect=error) as send, \
                self.assertLogs("orders.password_recovery", level="ERROR") as logs:
            response = self.request_reset("acme_admin")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.forgot_url + "?sent=1")
        page = self.client.get(response["Location"])
        self.assertContains(page, GENERIC_SENT_MESSAGE)

        output = "\n".join(logs.output)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("Password recovery email delivery failed: SMTPRecipientsRefused", output)
        self.assertIsNone(logs.records[0].exc_info)
        reset_link = LINK_RE.search(send.call_args.args[1])
        for secret in ("acme_admin", "owner@acme.example", "acme.example",
                       reset_link.group(0), reset_link.group(2), reset_link.group(3)):
            self.assertNotIn(secret, output)

    def test_failed_email_send_writes_nothing_to_stderr(self):
        stderr = io.StringIO()
        with patch.object(password_recovery, "send_mail", side_effect=OSError("smtp down")), \
                contextlib.redirect_stderr(stderr):
            response = self.request_reset("acme_admin")
            self.request_reset("nobody_here")
        self.assertEqual(response["Location"], self.forgot_url + "?sent=1")
        self.assertEqual(stderr.getvalue(), "")

    def test_successful_send_and_reset_log_nothing(self):
        with self.assertNoLogs("orders.password_recovery", level="DEBUG"):
            self.request_reset("acme_admin")
            self.open_link(*self.last_link())
            self.set_password(NEW_PASSWORD)
        self.assertEqual(len(mail.outbox), 1)


@override_settings(PROJECT_NAME="hospital_flash")
class ResetTokenTests(RecoveryTestBase):
    def setUp(self):
        super().setUp()
        self.company = make_company_admin("city_hospital", "admin@hospital.example", 2001)
        self.super_admin = make_super_admin("hf_root", "root@hf.example")

    def link_for(self, username):
        self.request_reset(username)
        return self.last_link()

    def test_valid_company_admin_token(self):
        self.assertResetForm(self.open_link(*self.link_for("city_hospital")))

    def test_valid_super_admin_token(self):
        self.assertResetForm(self.open_link(*self.link_for("hf_root")))

    def _clock(self, seconds_from_now):
        later = datetime.now() + timedelta(seconds=seconds_from_now)
        return patch.object(PasswordResetTokenGenerator, "_now", return_value=later)

    def test_expired_token(self):
        for username in ("city_hospital", "hf_root"):
            with self.subTest(username=username):
                uid, token = self.link_for(username)
                with self._clock(settings.PASSWORD_RESET_TIMEOUT + 60):
                    self.assertInvalidLink(self.open_link(uid, token))

    def test_token_within_lifetime_is_valid(self):
        uid, token = self.link_for("city_hospital")
        with self._clock(settings.PASSWORD_RESET_TIMEOUT - 120):
            self.assertResetForm(self.open_link(uid, token))

    def test_lifetime_is_short(self):
        self.assertLessEqual(settings.PASSWORD_RESET_TIMEOUT, 60 * 60)

    def test_invalid_token_and_uid(self):
        uid, token = self.link_for("city_hospital")
        self.assertInvalidLink(self.open_link(uid, "abc-123"))
        self.assertInvalidLink(self.open_link("bm9wZQ", token))
        self.assertInvalidLink(self.open_link("", ""))

    def test_missing_link_shows_invalid(self):
        self.assertInvalidLink(self.client.get(self.reset_url))

    def test_already_used_token(self):
        uid, token = self.link_for("city_hospital")
        self.open_link(uid, token)
        self.set_password(NEW_PASSWORD)
        self.assertInvalidLink(self.open_link(uid, token))

    def test_password_change_invalidates_token(self):
        uid, token = self.link_for("city_hospital")
        self.company.set_password("Another-Passw0rd!")
        self.company.save()
        self.assertInvalidLink(self.open_link(uid, token))

    def test_customer_email_change_invalidates_company_token(self):
        uid, token = self.link_for("city_hospital")
        outlet = self.company.admin_outlet
        outlet.customer_email = "new-admin@hospital.example"
        outlet.save()
        self.assertInvalidLink(self.open_link(uid, token))

    def test_company_token_follows_current_customer_email(self):
        outlet = self.company.admin_outlet
        outlet.customer_email = "current@hospital.example"
        outlet.save()
        uid, token = self.link_for("city_hospital")
        self.assertEqual(mail.outbox[-1].to, ["current@hospital.example"])
        user = User.objects.get(pk=self.company.pk)
        self.assertTrue(company_admin_token_generator.check_token(user, token))
        user.admin_outlet.customer_email = "other@hospital.example"
        self.assertFalse(company_admin_token_generator.check_token(user, token))
        self.assertResetForm(self.open_link(uid, token))

    def test_user_email_change_invalidates_super_admin_token(self):
        uid, token = self.link_for("hf_root")
        self.super_admin.email = "moved@hf.example"
        self.super_admin.save()
        self.assertInvalidLink(self.open_link(uid, token))

    def test_user_email_change_also_invalidates_company_token(self):
        uid, token = self.link_for("city_hospital")
        self.company.email = "irrelevant@x.example"
        self.company.save()
        # User.email stays in Django's base hash; invalidating here is the safe direction.
        self.assertInvalidLink(self.open_link(uid, token))

    def test_role_change_invalidates_token(self):
        uid, token = self.link_for("city_hospital")
        self.company.is_superuser = True
        self.company.save()
        self.assertInvalidLink(self.open_link(uid, token))


@override_settings(PROJECT_NAME="dine_flash_buffet")
class SetNewPasswordTests(RecoveryTestBase):
    def setUp(self):
        super().setUp()
        self.company = make_company_admin("buffet_co", "owner@buffet.example", 3001)
        self.request_reset("buffet_co")
        self.uid, self.token = self.last_link()
        self.assertResetForm(self.open_link(self.uid, self.token))

    def test_successful_reset_returns_to_login(self):
        response = self.set_password(NEW_PASSWORD)
        self.assertRedirects(response, self.reset_url, fetch_redirect_response=False)
        done = self.client.get(self.reset_url)
        self.assertContains(done, "Your password has been reset")
        self.assertContains(done, f'href="{reverse("login_view")}"')
        self.company.refresh_from_db()
        self.assertTrue(self.company.check_password(NEW_PASSWORD))
        self.assertFalse(self.company.check_password(OLD_PASSWORD))

    def test_new_password_works_with_existing_login_api(self):
        self.set_password(NEW_PASSWORD)
        response = Client().post(
            reverse("login_api_view"),
            {"username": "buffet_co", "password": NEW_PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "Company")

    def test_validation_failure_keeps_password(self):
        response = self.set_password("123")
        self.assertResetForm(response)
        self.assertContains(response, "too short")
        self.company.refresh_from_db()
        self.assertTrue(self.company.check_password(OLD_PASSWORD))

    def test_confirmation_mismatch(self):
        response = self.set_password(NEW_PASSWORD, NEW_PASSWORD + "x")
        self.assertResetForm(response)
        self.assertContains(response, "didn")
        self.company.refresh_from_db()
        self.assertTrue(self.company.check_password(OLD_PASSWORD))

    def test_leading_or_trailing_space_rejected(self):
        response = self.set_password(" " + NEW_PASSWORD)
        self.assertContains(response, "cannot start or end with a space")
        self.company.refresh_from_db()
        self.assertTrue(self.company.check_password(OLD_PASSWORD))

    def test_link_cannot_be_reused(self):
        self.set_password(NEW_PASSWORD)
        self.assertInvalidLink(self.set_password("Yet-Another-Passw0rd!"))
        self.assertInvalidLink(self.open_link(self.uid, self.token))
        self.company.refresh_from_db()
        self.assertTrue(self.company.check_password(NEW_PASSWORD))

    def test_reset_revokes_refresh_tokens(self):
        refresh = RefreshToken.for_user(self.company)
        self.set_password(NEW_PASSWORD)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists())

    def test_user_is_not_logged_in_after_reset(self):
        self.set_password(NEW_PASSWORD)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_reset_page_privacy_headers(self):
        response = self.client.get(self.reset_url)
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertIn("no-store", response["Cache-Control"])


@override_settings(PROJECT_NAME="dine_flash")
class CsrfBrowserFlowTests(RecoveryTestBase):
    """Full flow with CSRF enforced and the Origin a browser sends from these pages.

    Regression: with Referrer-Policy "no-referrer" browsers send "Origin: null" on POST,
    which Django CSRF rejects (403). With "same-origin" they send the real origin.
    """

    ORIGIN = "https://testserver"

    def setUp(self):
        super().setUp()
        self.company = make_company_admin("csrf_co", "owner@csrf.example", 5001)
        self.browser = Client(enforce_csrf_checks=True)

    def browser_post(self, url, data, origin=ORIGIN):
        token = self.browser.cookies["csrftoken"].value
        return self.browser.post(url, {**data, "csrfmiddlewaretoken": token}, HTTP_ORIGIN=origin, secure=True)

    def test_pages_ask_browsers_for_same_origin_referrer(self):
        for url in (self.forgot_url, self.reset_url):
            response = self.browser.get(url, secure=True)
            self.assertEqual(response["Referrer-Policy"], "same-origin")
            self.assertContains(response, '<meta name="referrer" content="same-origin">')
            self.assertNotContains(response, "no-referrer")

    def test_full_recovery_flow_passes_csrf_with_matching_origin(self):
        # 1. Forgot Password username submission
        self.browser.get(self.forgot_url, secure=True)
        response = self.browser_post(self.forgot_url, {"username": "csrf_co"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.forgot_url + "?sent=1")
        self.assertEqual(len(mail.outbox), 1)
        uid, token = self.last_link()

        # 2. Reset-token verification (the POST the page's JS makes from the URL fragment)
        self.browser.get(self.reset_url, secure=True)
        response = self.browser_post(self.reset_url, {"action": "verify", "uid": uid, "token": token})
        self.assertEqual(response.status_code, 302)
        self.assertResetForm(self.browser.get(self.reset_url, secure=True))

        # 3. New-password submission
        response = self.browser_post(
            self.reset_url,
            {"action": "set", "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.browser.get(self.reset_url, secure=True), "Your password has been reset")
        self.company.refresh_from_db()
        self.assertTrue(self.company.check_password(NEW_PASSWORD))

    def test_csrf_still_enforced(self):
        self.browser.get(self.forgot_url, secure=True)
        null_origin = self.browser_post(self.forgot_url, {"username": "csrf_co"}, origin="null")
        self.assertEqual(null_origin.status_code, 403)
        foreign = self.browser_post(self.forgot_url, {"username": "csrf_co"}, origin="https://evil.example")
        self.assertEqual(foreign.status_code, 403)
        no_token = self.browser.post(self.forgot_url, {"username": "csrf_co"}, HTTP_ORIGIN=self.ORIGIN, secure=True)
        self.assertEqual(no_token.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)


class FlavourGatingTests(RecoveryTestBase):
    ENABLED = ("dine_flash", "dine_flash_buffet", "hospital_flash")
    DISABLED = ("food_flash", "airline_flash", "service_flash")

    def setUp(self):
        super().setUp()
        make_company_admin("gate_co", "gate@x.example", 4001)

    def test_enabled_flavours(self):
        for flavour in self.ENABLED:
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                login = self.client.get(reverse("login_view"))
                self.assertContains(login, "Forgot Password?")
                self.assertContains(login, f'href="{self.forgot_url}"')
                self.assertEqual(self.client.get(self.forgot_url).status_code, 200)
                self.assertEqual(self.client.get(self.reset_url).status_code, 200)

    def test_disabled_flavours(self):
        for flavour in self.DISABLED:
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                login = self.client.get(reverse("login_view"))
                self.assertEqual(login.status_code, 200)
                self.assertNotContains(login, "Forgot Password")
                self.assertNotContains(login, self.forgot_url)
                self.assertEqual(self.client.get(self.forgot_url).status_code, 404)
                self.assertEqual(self.request_reset("gate_co").status_code, 404)
                self.assertEqual(self.client.get(self.reset_url).status_code, 404)
                self.assertEqual(
                    self.client.post(self.reset_url, {"action": "verify", "uid": "x", "token": "y"}).status_code,
                    404,
                )
        self.assertEqual(len(mail.outbox), 0)

    def test_login_form_unchanged(self):
        with override_settings(PROJECT_NAME="dine_flash"):
            login = self.client.get(reverse("login_view")).content.decode()
        form_html = login.split('<form method="POST" id="loginForm">', 1)[1].split("</form>", 1)[0]
        self.assertNotIn("Forgot", form_html)
        self.assertIn('id="username"', form_html)
        self.assertIn('id="password"', form_html)
