# Attendance Stats

App Streamlit per leggere il foglio `Roster` da Google Sheets e calcolare:

- presenze totali
- presenze campo allenamento
- presenze palestra

## Avvio locale

```bash
pip install -r requirements.txt
streamlit run app.py
```

Configura il link in `streamlit/secrets.toml` oppure nel path standard `.streamlit/secrets.toml`.
Entrambi sono ignorati da Git:

```toml
sheet_url = "https://docs.google.com/spreadsheets/d/.../edit?gid=..."
```

## Pubblicazione su Streamlit Cloud

In `Settings > Secrets` aggiungi sempre:

```toml
sheet_url = "https://docs.google.com/spreadsheets/d/.../edit?gid=..."
```

Se il Google Sheet e' privato, crea un service account Google, condividi il foglio con la sua email e aggiungi anche questo in `Secrets`:

```toml
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```
