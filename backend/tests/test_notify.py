from unittest.mock import MagicMock, patch

from app.core import notify as notify_mod
from app.core.config import Settings
from app.core.notify import EmailNotifier, MultiNotifier, NoopNotifier, SlackNotifier, get_notifier


def _reset_notifier_singleton():
    notify_mod._notifier_instance = None


def test_noop_notifier_never_raises():
    NoopNotifier().notify("subject", "message")  # must not raise, no network calls


def test_get_notifier_defaults_to_noop(monkeypatch):
    _reset_notifier_singleton()
    monkeypatch.setattr(notify_mod, "get_settings", lambda: Settings(notify_backend="none"))
    assert isinstance(get_notifier(), NoopNotifier)


def test_get_notifier_selects_email(monkeypatch):
    _reset_notifier_singleton()
    monkeypatch.setattr(notify_mod, "get_settings", lambda: Settings(notify_backend="email"))
    assert isinstance(get_notifier(), EmailNotifier)


def test_get_notifier_selects_slack(monkeypatch):
    _reset_notifier_singleton()
    monkeypatch.setattr(notify_mod, "get_settings", lambda: Settings(notify_backend="slack"))
    assert isinstance(get_notifier(), SlackNotifier)


def test_get_notifier_selects_both(monkeypatch):
    _reset_notifier_singleton()
    monkeypatch.setattr(notify_mod, "get_settings", lambda: Settings(notify_backend="both"))
    notifier = get_notifier()
    assert isinstance(notifier, MultiNotifier)
    assert len(notifier._notifiers) == 2


def test_get_notifier_caches_instance(monkeypatch):
    _reset_notifier_singleton()
    monkeypatch.setattr(notify_mod, "get_settings", lambda: Settings(notify_backend="none"))
    first = get_notifier()
    second = get_notifier()
    assert first is second


def test_email_notifier_sends_via_smtp():
    notifier = EmailNotifier(
        host="smtp.example.com", port=587, user="u", password="p",
        sender="recon@eroute.local", recipients=["ops@eroute.local"],
    )
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        notifier.notify("Run completed", "Run abc123 (nfs) completed.")

        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("u", "p")
        assert mock_smtp.send_message.call_count == 1
        sent_msg = mock_smtp.send_message.call_args[0][0]
        assert sent_msg["Subject"] == "Run completed"
        assert sent_msg["To"] == "ops@eroute.local"


def test_email_notifier_skips_send_with_no_recipients():
    notifier = EmailNotifier(host="h", port=587, user="", password="", sender="s", recipients=[])
    with patch("smtplib.SMTP") as mock_smtp_cls:
        notifier.notify("subject", "message")
        mock_smtp_cls.assert_not_called()


def test_slack_notifier_posts_to_webhook():
    notifier = SlackNotifier("https://hooks.slack.example/T000/B000/xyz")
    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        notifier.notify("Run failed", "Run abc123 (upi) failed.")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://hooks.slack.example/T000/B000/xyz"
        assert "Run failed" in kwargs["json"]["text"]
        assert "Run abc123 (upi) failed." in kwargs["json"]["text"]
        mock_response.raise_for_status.assert_called_once()


def test_multi_notifier_fans_out_to_all():
    n1, n2 = MagicMock(), MagicMock()
    MultiNotifier([n1, n2]).notify("subject", "message")
    n1.notify.assert_called_once_with("subject", "message")
    n2.notify.assert_called_once_with("subject", "message")
