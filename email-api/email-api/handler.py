"""
handler.py - Serverless Lambda handler for sending email.

Supports three modes controlled by env var EMAIL_MODE:
  - "offline": simulated send OR local SMTP (used for local testing)
  - "smtp"   : real SMTP server (Gmail, SendGrid SMTP, etc.)
  - "ses"    : AWS SES via boto3

Environment variables used (set locally or in provider.environment):
  SENDER_EMAIL  - required (example: "me@example.com")
  EMAIL_MODE    - offline | smtp | ses   (default: offline)
  SMTP_HOST     - hostname for SMTP (for smtp/offline)
  SMTP_PORT     - port for SMTP (default 587)
  SMTP_USER     - SMTP username (if required)
  SMTP_PASS     - SMTP password (if required)
  SMTP_USE_TLS  - "true" to use STARTTLS
  SMTP_USE_SSL  - "true" to use SMTPS (smtp over SSL)
  SES_REGION    - AWS region for SES (default us-east-1)
"""

import json
import os
import re
import base64
import smtplib
import ssl
from email.message import EmailMessage

# boto3 for SES
import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Basic email regex (simple validation)
EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def _json_response(status: int, payload: dict, cors: bool = True):
    """Return API Gateway compatible JSON response with headers."""
    headers = {"Content-Type": "application/json"}
    if cors:
        headers.update({
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "OPTIONS,POST"
        })
    return {"statusCode": status, "headers": headers, "body": json.dumps(payload)}

def _parse_event_body(event):
    """Extract JSON body from the Lambda event (handles base64 if present)."""
    body = event.get("body")
    if body is None:
        return None, "Missing request body"
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception:
            return None, "Body is base64 encoded but could not be decoded"
    try:
        data = json.loads(body)
    except Exception:
        return None, "Request body is not valid JSON"
    return data, None

def _validate_input(data: dict):
    """Validate required fields and email format. Return (code, message) on error."""
    missing = [k for k in ("receiver_email", "subject", "body_text") if not data.get(k, "").strip()]
    if missing:
        return 400, f"Missing required field(s): {', '.join(missing)}"
    receiver = data.get("receiver_email", "").strip()
    if not EMAIL_REGEX.match(receiver):
        return 422, "receiver_email is not a valid email address"
    if len(data.get("subject", "")) > 998:
        return 422, "Subject is too long"
    return None, None

def _send_via_smtp(sender_email, receiver_email, subject, body_text):
    """
    Send using SMTP. Reads SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_USE_TLS, SMTP_USE_SSL.
    If SMTP_HOST is not set, simulate a send (offline mode).
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    try:
        if host:
            # Use real SMTP
            if use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
                    if user and password:
                        server.login(user, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    if use_tls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                    if user and password:
                        server.login(user, password)
                    server.send_message(msg)
        else:
            # Offline simulation: print email to terminal
            print("=== Simulated Email ===")
            print(f"From: {sender_email}")
            print(f"To: {receiver_email}")
            print(f"Subject: {subject}")
            print(f"Body:\n{body_text}")
            print("======================")
        return {"mode": "smtp", "messageId": None}
    except Exception as e:
        raise RuntimeError(f"SMTP error: {str(e)}") from e

def _send_via_ses(sender_email, receiver_email, subject, body_text):
    """Send using AWS SES via boto3."""
    region = os.getenv("SES_REGION") or os.getenv("AWS_REGION") or "us-east-1"
    ses = boto3.client("ses", region_name=region)
    try:
        resp = ses.send_email(
            Source=sender_email,
            Destination={"ToAddresses": [receiver_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
            },
        )
        return {"mode": "ses", "messageId": resp.get("MessageId")}
    except (ClientError, BotoCoreError) as e:
        raise RuntimeError(f"SES error: {str(e)}") from e

def send_email(event, context):
    """
    Main Lambda handler: parse body, validate, then send using chosen mode.
    Returns JSON responses with appropriate HTTP status codes.
    """
    print("DEBUG incoming event:", event)
    data, err = _parse_event_body(event)
    if err:
        return _json_response(400, {"error": err})

    code, v_err = _validate_input(data)
    if v_err:
        return _json_response(code, {"error": v_err})

    sender_email = os.getenv("SENDER_EMAIL", "test@example.com")
    receiver_email = data["receiver_email"].strip()
    subject = str(data["subject"])
    body_text = str(data["body_text"])

    mode = os.getenv("EMAIL_MODE", "offline").lower()

    try:
        if mode in ("offline", "local", "smtp"):
            _send_via_smtp(sender_email, receiver_email, subject, body_text)
            # Always return 200 success for demo
            return _json_response(200, {"message": "Email sent successfully"})

        elif mode == "ses":
            _send_via_ses(sender_email, receiver_email, subject, body_text)
            return _json_response(200, {"message": "Email sent successfully"})

        else:
            return _json_response(500, {"error": f"Unknown EMAIL_MODE '{mode}'. Use offline|smtp|ses"})

    except RuntimeError as e:
        return _json_response(502, {"error": str(e)})
    except Exception as e:
        return _json_response(500, {"error": str(e)})
