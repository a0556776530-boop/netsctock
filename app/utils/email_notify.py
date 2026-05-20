import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_assignment_email(contact, asset, assigned_to_name, site_name=None):
    """Send an asset-assignment notification to a contact. Returns True on success."""
    smtp_host     = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port     = int(os.environ.get('SMTP_PORT', '587'))
    smtp_email    = os.environ.get('SMTP_EMAIL', '')
    smtp_password = os.environ.get('SMTP_PASSWORD', '')

    if not smtp_email or not smtp_password:
        print('[Email] SMTP credentials not configured — skipping.')
        return False
    if not contact.email:
        print(f'[Email] Contact {contact.name} has no email address.')
        return False

    model      = asset.model or asset.serial_number
    serial     = asset.serial_number
    site       = site_name or 'N/A'

    subject = f'Asset Assignment Update - {model}'

    text_body = f"""\
Hello {contact.name},

This is an automated update from NetStock.

The following asset has been assigned to you:

  {model} (S/N: {serial})
  Current Site: {site}

Please confirm receipt at your earliest convenience.

— NetStock Inventory System
"""

    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f4f6fb;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,.08);">

        <!-- Header -->
        <tr>
          <td style="background:#1a5fa8;padding:28px 36px;">
            <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700;
                       letter-spacing:.02em;">NetStock</h1>
            <p style="margin:4px 0 0;color:#c8dcf5;font-size:13px;">
              Asset Assignment Update
            </p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px 36px;">
            <p style="margin:0 0 16px;font-size:15px;color:#333;">
              Hello <strong>{contact.name}</strong>,
            </p>
            <p style="margin:0 0 24px;font-size:15px;color:#555;line-height:1.6;">
              This is an automated update from <strong>NetStock</strong>.
              The following asset has been assigned to you:
            </p>

            <!-- Asset card -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f0f5ff;border-radius:6px;
                          border:1px solid #d0e1f9;margin-bottom:24px;">
              <tr>
                <td style="padding:18px 22px;">
                  <p style="margin:0 0 4px;font-size:18px;font-weight:700;color:#1a5fa8;">
                    {model}
                  </p>
                  <p style="margin:0 0 14px;font-size:13px;color:#666;">
                    S/N: <span style="font-family:monospace;">{serial}</span>
                  </p>
                  <table cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding:3px 10px 3px 0;font-size:13px;
                                 color:#888;font-weight:600;">Current Site</td>
                      <td style="padding:3px 0;font-size:13px;color:#333;">
                        {site}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>

            <p style="margin:0;font-size:13px;color:#888;">
              Please confirm receipt at your earliest convenience.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8f9fc;padding:16px 36px;border-top:1px solid #eee;">
            <p style="margin:0;font-size:12px;color:#aaa;">
              This is an automated message from NetStock Inventory System.
              Please do not reply to this email.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = smtp_email
    msg['To']      = contact.email
    msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html',  'utf-8'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        print(f'[Email] Sent assignment notification to {contact.email}')
        return True
    except Exception as exc:
        print(f'[Email] Failed to send to {contact.email}: {exc}')
        return False
