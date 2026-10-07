"""Self-service Forgot Password / Reset Password.

Available only for Dine Flash, Dine Flash Buffet (Food On Demand) and Hospital Flash.

The user enters a username only; the recovery email is resolved internally:
- Super Admin (``is_superuser``): ``User.email``
- Company Admin (``is_staff`` + linked ``AdminOutlet``): ``AdminOutlet.customer_email``
  (current value; never copied into ``User.email``)

The emailed link carries uid/token in the URL fragment, which browsers never send to the
server, so tokens stay out of request logs and Referer headers. The page posts them once,
they are kept in the session, and the address bar is cleaned (same idea as Django's
PasswordResetConfirmView after its first request).
"""

import hashlib
import logging
import threading

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import Http404
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)

PASSWORD_RECOVERY_PROJECTS = frozenset({
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
})

ROLE_SUPER_ADMIN = "super_admin"
ROLE_COMPANY_ADMIN = "company_admin"

# (max requests, window seconds)
FORGOT_PASSWORD_IP_LIMIT = (20, 15 * 60)
FORGOT_PASSWORD_USERNAME_LIMIT = (3, 60 * 60)

RESET_SESSION_KEY = "_password_recovery_reset"
RESET_DONE_SESSION_KEY = "_password_recovery_done"

GENERIC_SENT_MESSAGE = (
    "If an account with that username is eligible for password recovery, "
    "a password reset link has been sent to the registered email address."
)


def is_password_recovery_enabled():
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() in PASSWORD_RECOVERY_PROJECTS


def get_recovery_role(user):
    """Mirror login_api_view role detection: superuser first, then Company Admin."""
    if user is None or not user.is_active:
        return None
    if user.is_superuser:
        return ROLE_SUPER_ADMIN
    if user.is_staff and getattr(user, "admin_outlet", None) is not None:
        return ROLE_COMPANY_ADMIN
    return None


def get_recovery_email(user, role):
    """Return the validated recovery email for the role, or None. No fallbacks."""
    if role == ROLE_SUPER_ADMIN:
        raw = user.email
    elif role == ROLE_COMPANY_ADMIN:
        raw = user.admin_outlet.customer_email
    else:
        return None
    email = (raw or "").strip()
    try:
        validate_email(email)
    except ValidationError:
        return None
    return email


class CompanyAdminPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """Django's generator plus the current AdminOutlet.customer_email.

    Keeps password hash / last_login / timestamp (so a used or superseded link dies)
    and additionally invalidates links when the company recovery email changes.
    """

    key_salt = "orders.password_recovery.CompanyAdminPasswordResetTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        admin_outlet = getattr(user, "admin_outlet", None)
        outlet_part = ""
        if admin_outlet is not None:
            outlet_part = f"{admin_outlet.pk}:{(admin_outlet.customer_email or '').strip()}"
        return f"{super()._make_hash_value(user, timestamp)}|{outlet_part}"


company_admin_token_generator = CompanyAdminPasswordResetTokenGenerator()


def token_generator_for(role):
    if role == ROLE_SUPER_ADMIN:
        return default_token_generator
    if role == ROLE_COMPANY_ADMIN:
        return company_admin_token_generator
    return None


def _client_ip(request):
    return request.META.get("REMOTE_ADDR") or "unknown"


def _rate_limited(key, limit):
    """Fixed-window counter in the default cache. True once the limit is exceeded."""
    max_requests, window = limit
    if cache.add(key, 1, window):
        return False
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    return count > max_requests


def _username_key(username):
    return "pwrecovery:user:" + hashlib.sha256(username.lower().encode("utf-8")).hexdigest()


def _run_in_background(func):
    # Keeps response timing independent of whether an email is sent (no enumeration by timing).
    threading.Thread(target=func, daemon=True).start()


def _build_reset_url(request, uidb64, token):
    path = reverse("reset_password")
    base = (getattr(settings, "PASSWORD_RESET_BASE_URL", "") or "").strip().rstrip("/")
    page_url = f"{base}{path}" if base else request.build_absolute_uri(path)
    return f"{page_url}#uid={uidb64}&token={token}"


def _send_reset_email(request, user, role, email):
    generator = token_generator_for(role)
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = generator.make_token(user)
    context = {
        "display_name": getattr(settings, "PROJECT_DISPLAY_NAME", "") or "",
        "username": user.get_username(),
        "reset_url": _build_reset_url(request, uidb64, token),
        "expiry_minutes": max(1, settings.PASSWORD_RESET_TIMEOUT // 60),
    }
    subject = "".join(
        render_to_string("orders/password_recovery/email_subject.txt", context).splitlines()
    )
    body = render_to_string("orders/password_recovery/email_body.txt", context)

    def deliver():
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        except Exception as exc:
            # Type only: SMTP exceptions/tracebacks can contain the recipient address.
            logger.error("Password recovery email delivery failed: %s", type(exc).__name__)

    _run_in_background(deliver)


def request_password_reset(request, username):
    """Send a reset email when the account is eligible. Always silent towards the caller."""
    user = get_user_model().objects.filter(username=username).first()
    role = get_recovery_role(user)
    if role is None:
        return
    email = get_recovery_email(user, role)
    if email is None:
        # Deliberately not logged: it would reveal that the account exists.
        return
    _send_reset_email(request, user, role, email)


def _user_from_uidb64(uidb64):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return get_user_model().objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, ValidationError, get_user_model().DoesNotExist):
        return None


def resolve_reset_user(uidb64, token):
    """Return the user when uid/token form a currently valid link for an eligible account."""
    if not uidb64 or not token:
        return None
    user = _user_from_uidb64(uidb64)
    generator = token_generator_for(get_recovery_role(user))
    if generator is None or not generator.check_token(user, token):
        return None
    return user


def _revoke_refresh_tokens(user):
    try:
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
    except Exception as exc:
        logger.error("Refresh-token revocation after password reset failed: %s", type(exc).__name__)


class ForgotPasswordForm(forms.Form):
    username = forms.CharField(max_length=150, strip=True)


class RecoverySetPasswordForm(SetPasswordForm):
    """SetPasswordForm + reject edge whitespace (the login page trims passwords)."""

    def clean_new_password1(self):
        password = self.cleaned_data.get("new_password1") or ""
        if password != password.strip():
            raise ValidationError("Password cannot start or end with a space.")
        return password


def _same_origin_referrer(response):
    # Not "no-referrer": browsers then send "Origin: null" on POST, which Django CSRF rejects.
    # The token lives in the URL fragment, which is never part of a Referer anyway.
    response["Referrer-Policy"] = "same-origin"
    return response


@never_cache
def forgot_password_view(request):
    if not is_password_recovery_enabled():
        raise Http404()

    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            if _rate_limited("pwrecovery:ip:" + _client_ip(request), FORGOT_PASSWORD_IP_LIMIT):
                response = render(
                    request,
                    "orders/password_recovery/forgot_password.html",
                    {"form": form, "rate_limited": True},
                    status=429,
                )
                return _same_origin_referrer(response)
            username = form.cleaned_data["username"]
            if not _rate_limited(_username_key(username), FORGOT_PASSWORD_USERNAME_LIMIT):
                request_password_reset(request, username)
            return redirect(reverse("forgot_password") + "?sent=1")
    else:
        form = ForgotPasswordForm()

    context = {
        "form": form,
        "sent": request.method == "GET" and request.GET.get("sent") == "1",
        "generic_message": GENERIC_SENT_MESSAGE,
    }
    return _same_origin_referrer(render(request, "orders/password_recovery/forgot_password.html", context))


@never_cache
def reset_password_view(request):
    if not is_password_recovery_enabled():
        raise Http404()

    template = "orders/password_recovery/reset_password.html"
    action = request.POST.get("action") if request.method == "POST" else None

    if action == "verify":
        # Link opened: JS moved uid/token from the URL fragment into this POST.
        request.session[RESET_SESSION_KEY] = {
            "uid": request.POST.get("uid", "")[:64],
            "token": request.POST.get("token", "")[:128],
        }
        request.session.pop(RESET_DONE_SESSION_KEY, None)
        return redirect("reset_password")

    if request.method == "GET" and request.session.pop(RESET_DONE_SESSION_KEY, False):
        return _same_origin_referrer(render(request, template, {"state": "done"}))

    pending = request.session.get(RESET_SESSION_KEY)
    if not pending:
        return _same_origin_referrer(render(request, template, {"state": "missing"}))

    user = resolve_reset_user(pending.get("uid"), pending.get("token"))
    if user is None:
        request.session.pop(RESET_SESSION_KEY, None)
        return _same_origin_referrer(render(request, template, {"state": "invalid"}))

    if action == "set":
        form = RecoverySetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            _revoke_refresh_tokens(user)
            request.session.pop(RESET_SESSION_KEY, None)
            request.session[RESET_DONE_SESSION_KEY] = True
            return redirect("reset_password")
    else:
        form = RecoverySetPasswordForm(user)

    return _same_origin_referrer(render(request, template, {"state": "form", "form": form}))
