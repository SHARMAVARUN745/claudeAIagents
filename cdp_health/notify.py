import os, smtplib, requests
from email.message import EmailMessage


def send(md, worst, cfg):
    hook = os.environ.get(cfg.get("slack_webhook_env", ""), "")
    if hook:  # Slack/Teams-compatible incoming webhook
        requests.post(hook, json={"text": f"*Cloudera health: {worst}*\n{md[:3500]}"}, timeout=15)
    em = cfg.get("email")
    if em:
        m = EmailMessage()
        m["Subject"], m["From"], m["To"] = f"[Cloudera] Health report - {worst}", em["from"], ", ".join(em["to"])
        m.set_content(md)
        with smtplib.SMTP(em["smtp_host"], em.get("smtp_port", 25)) as s:
            s.send_message(m)
