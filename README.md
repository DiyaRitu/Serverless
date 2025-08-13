# Serverless Offline Email API

This project is a **Serverless Framework Python REST API** that sends emails. It works **fully offline** using a local SMTP debug server and supports **real SMTP** or **AWS SES** if configured. Perfect for demos and local testing without any cloud deployment.

---

## **Features**

- REST API endpoint: `POST /send-email`
- Input: `receiver_email`, `subject`, `body_text`
- Validation of required fields and email format
- Offline mode prints email to terminal
- Supports real SMTP or AWS SES
- Returns appropriate HTTP status codes:
  - **200**: Success
  - **400 / 422**: Input validation errors
  - **500 / 502**: Internal/server errors
- CORS enabled for easy testing

---

## **Getting Started**

### **1. Clone the repository**

```bash
git clone https://github.com/<your-username>/email-api.git
cd email-api
