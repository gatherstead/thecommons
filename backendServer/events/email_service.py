import logging
import os

import brevo_python
from brevo_python.rest import ApiException

logger = logging.getLogger(__name__)


def _get_brevo_client():
    configuration = brevo_python.Configuration()
    configuration.api_key["api-key"] = os.environ["BREVO_API_KEY"]
    return brevo_python.TransactionalEmailsApi(brevo_python.ApiClient(configuration))


def _get_sender():
    return brevo_python.SendSmtpEmailSender(
        name="The Commons",
        email=os.environ.get("DIGEST_FROM_EMAIL", "digest@thecommons.town"),
    )


def send_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    """Send one transactional email via Brevo.

    Low-level primitive used by every digest path. Returns True on success and
    False (after logging) on failure, so callers can tally results without
    each having to catch ApiException.
    """
    email = brevo_python.SendSmtpEmail(
        to=[brevo_python.SendSmtpEmailTo(email=to)],
        sender=_get_sender(),
        subject=subject,
        html_content=html,
    )
    if text:
        email.text_content = text

    try:
        _get_brevo_client().send_transac_email(email)
        return True
    except ApiException as e:
        logger.error("Brevo send failed for %s: %s", to, e)
        return False
    except Exception as e:  # noqa: BLE001 — config/network errors shouldn't crash a batch
        logger.error("Unexpected error sending to %s: %s", to, e)
        return False
