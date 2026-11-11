"""Email texts for employee onboarding. Plain text plus a simple HTML version."""
from __future__ import annotations

from datetime import datetime
from html import escape

from ..mailer import Email


def _html(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> str:
    body = "".join(f"<p style='margin:0 0 14px'>{p}</p>" for p in paragraphs)
    if button:
        label, url = button
        body += (f"<p style='margin:22px 0'><a href='{escape(url)}' style='background:#0f9d6b;color:#fff;"
                 f"padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600'>{escape(label)}</a></p>"
                 f"<p style='margin:0 0 14px;color:#5b6b78;font-size:13px'>Or open this link: {escape(url)}</p>")
    return (f"<div style='font-family:Inter,Arial,sans-serif;max-width:560px;margin:auto;color:#1b2a38'>"
            f"<div style='background:#10233f;color:#fff;padding:16px 22px;border-radius:12px 12px 0 0;"
            f"font-weight:700'>ClearPay4U <span style='font-weight:400;opacity:.7'>· zero-penalty payroll</span></div>"
            f"<div style='border:1px solid #e3e9e7;border-top:0;padding:22px;border-radius:0 0 12px 12px'>"
            f"<h2 style='margin:0 0 14px;font-size:20px'>{escape(title)}</h2>{body}</div></div>")


def _date(dt: datetime) -> str:
    return f"{dt:%d %b %Y}"


def invite(to: str, employee_name: str, client_name: str, link: str, expires: datetime) -> Email:
    first = employee_name.split()[0] if employee_name else "there"
    subject = f"{client_name} invites you to ClearPay4U payroll"
    text = (f"Hello {first},\n\n{client_name} runs payroll on ClearPay4U. Create your login to fill in your joining "
            f"details (contact, PAN, UAN and bank account), see your payslips and declare your tax savings.\n\n"
            f"Create your account: {link}\n\nThe link works once and expires on {_date(expires)}. "
            f"If you weren't expecting this, you can ignore this email.\n\n— ClearPay4U for {client_name}")
    html = _html(f"Welcome to {client_name}'s payroll", [
        f"Hello {escape(first)},",
        f"{escape(client_name)} runs payroll on ClearPay4U. Create your login to fill in your joining details "
        "(contact, PAN, UAN and bank account), see your payslips and declare your tax savings.",
        f"The link works once and expires on <strong>{_date(expires)}</strong>.",
    ], ("Create your account", link))
    return Email(to, subject, text, html)


def submitted(to: str, employee_name: str, code: str, client_name: str, link: str) -> Email:
    subject = f"{employee_name} submitted joining details"
    text = (f"{employee_name} ({code}) at {client_name} has submitted their joining details.\n\n"
            f"Check and verify them on the Employee onboarding page: {link}")
    html = _html("Joining details to check", [
        f"<strong>{escape(employee_name)}</strong> ({escape(code)}) at {escape(client_name)} has submitted their "
        "joining details. Check them, then verify or send them back with a note.",
    ], ("Open Employee onboarding", link))
    return Email(to, subject, text, html)


def returned(to: str, employee_name: str, client_name: str, note: str, link: str) -> Email:
    first = employee_name.split()[0] if employee_name else "there"
    subject = "Please update your joining details"
    text = (f"Hello {first},\n\n{client_name} asked you to change your joining details:\n\n  {note}\n\n"
            f"Log in to update and resubmit them: {link}")
    html = _html("Please update your joining details", [
        f"Hello {escape(first)},",
        f"{escape(client_name)} asked you to change your joining details:",
        f"<em style='display:block;border-left:3px solid #e8a317;padding-left:10px'>{escape(note)}</em>",
    ], ("Update my details", link))
    return Email(to, subject, text, html)


def verified(to: str, employee_name: str, client_name: str, link: str) -> Email:
    first = employee_name.split()[0] if employee_name else "there"
    subject = "Your joining details are verified"
    text = (f"Hello {first},\n\n{client_name} has verified your joining details. Your salary and PF, ESI and TDS "
            f"filings will use them.\n\nSee your payslips and tax declarations: {link}")
    html = _html("You're all set", [
        f"Hello {escape(first)},",
        f"{escape(client_name)} has verified your joining details. Your salary and PF, ESI and TDS filings will use them.",
    ], ("Open ClearPay4U", link))
    return Email(to, subject, text, html)
