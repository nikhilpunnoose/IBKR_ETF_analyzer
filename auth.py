"""Supabase authentication and IBKR credential management."""

from __future__ import annotations

import httpx
import streamlit as st
from cryptography.fernet import Fernet
from supabase import Client, create_client


# --- Availability check ---


def auth_available() -> bool:
    """Return True if Supabase secrets are configured."""
    try:
        _ = st.secrets["supabase"]["url"]
        _ = st.secrets["supabase"]["anon_key"]
        return True
    except (KeyError, FileNotFoundError):
        return False


# --- Supabase client ---


@st.cache_resource
def get_supabase() -> Client:
    """Return a cached Supabase client."""
    sb = create_client(
        st.secrets["supabase"]["url"].strip(),
        st.secrets["supabase"]["anon_key"].strip(),
    )
    # Force HTTP/1.1 on the auth client to avoid StreamReset errors on Streamlit Cloud
    sb.auth._http_client = httpx.Client(http2=False)
    return sb


# --- OAuth flow ---


def handle_oauth_callback() -> bool:
    """Check for OAuth callback code in query params and exchange for session.

    Returns True if a login just completed (caller should st.rerun()).
    """
    code = st.query_params.get("code")
    if not code:
        return False

    try:
        sb = get_supabase()
        resp = sb.auth.exchange_code_for_session({"auth_code": code})
        st.session_state["supabase_session"] = resp.session
        st.session_state["supabase_user"] = resp.user
    except Exception as e:
        st.error(f"Login failed: {e}")
        return False
    finally:
        st.query_params.clear()

    return True


def get_login_url() -> str:
    """Get the Google OAuth login URL using PKCE flow."""
    sb = get_supabase()
    resp = sb.auth.sign_in_with_oauth(
        {
            "provider": "google",
            "options": {"redirect_to": _get_redirect_url()},
        }
    )
    return resp.url


def _get_redirect_url() -> str:
    """Build the redirect URL from the current Streamlit app URL."""
    # In Streamlit Cloud, st.context.headers gives the host
    # Locally, default to localhost:8501
    try:
        headers = st.context.headers
        host = headers.get("Host", "localhost:8501")
        proto = headers.get("X-Forwarded-Proto", "http")
        return f"{proto}://{host}/"
    except Exception:
        return "http://localhost:8501/"


# --- Session helpers ---


def restore_session() -> None:
    """Try to restore an existing Supabase session on page reload."""
    if "supabase_user" in st.session_state:
        return
    try:
        sb = get_supabase()
        resp = sb.auth.get_session()
        if resp and resp.user:
            st.session_state["supabase_session"] = resp
            st.session_state["supabase_user"] = resp.user
    except Exception:
        pass


def is_authenticated() -> bool:
    return "supabase_user" in st.session_state


def get_user():
    return st.session_state.get("supabase_user")


def get_user_id() -> str | None:
    user = get_user()
    return str(user.id) if user else None


def logout() -> None:
    """Sign out and clear all session state."""
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass
    for key in [
        "supabase_session",
        "supabase_user",
        "has_ibkr_credentials",
        "data_key",
        "portfolio",
        "config",
    ]:
        st.session_state.pop(key, None)


# --- Encryption ---


def _get_fernet() -> Fernet:
    return Fernet(st.secrets["encryption"]["fernet_key"].encode())


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


# --- IBKR credential CRUD ---


def save_ibkr_credentials(user_id: str, token: str, query_id: str) -> None:
    """Encrypt token and upsert credentials to Supabase."""
    sb = get_supabase()
    encrypted_token = encrypt_value(token)
    sb.table("user_ibkr_credentials").upsert(
        {
            "user_id": user_id,
            "ibkr_flex_token_encrypted": encrypted_token,
            "ibkr_query_id": query_id,
            "updated_at": "now()",
        }
    ).execute()
    # Refresh cached flag
    st.session_state["has_ibkr_credentials"] = True


def load_ibkr_credentials(user_id: str) -> tuple[str, str] | None:
    """Load and decrypt credentials. Returns (token, query_id) or None."""
    sb = get_supabase()
    resp = (
        sb.table("user_ibkr_credentials")
        .select("ibkr_flex_token_encrypted, ibkr_query_id")
        .eq("user_id", user_id)
        .execute()
    )
    if not resp.data:
        return None
    row = resp.data[0]
    token = decrypt_value(row["ibkr_flex_token_encrypted"])
    return token, row["ibkr_query_id"]


def delete_ibkr_credentials(user_id: str) -> None:
    """Delete saved credentials."""
    sb = get_supabase()
    sb.table("user_ibkr_credentials").delete().eq("user_id", user_id).execute()
    st.session_state["has_ibkr_credentials"] = False


def has_ibkr_credentials(user_id: str) -> bool:
    """Check if user has saved credentials. Cached in session state."""
    cached = st.session_state.get("has_ibkr_credentials")
    if cached is not None:
        return cached

    sb = get_supabase()
    resp = (
        sb.table("user_ibkr_credentials")
        .select("user_id")
        .eq("user_id", user_id)
        .execute()
    )
    result = bool(resp.data)
    st.session_state["has_ibkr_credentials"] = result
    return result
