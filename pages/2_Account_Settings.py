"""Account Settings page — manage saved IBKR credentials."""

import streamlit as st

from auth import (
    delete_ibkr_credentials,
    get_user,
    get_user_id,
    has_ibkr_credentials,
    is_authenticated,
    load_ibkr_credentials,
    save_ibkr_credentials,
)

st.title("Account Settings")

if not is_authenticated():
    st.warning("Sign in with Google to access account settings.")
    st.stop()

user = get_user()
st.markdown(f"Signed in as **{user.email}**")
user_id = get_user_id()

st.divider()
st.header("IBKR Flex Query Credentials")
st.caption(
    "Save your IBKR Flex Query token and query ID to load positions "
    "directly from IBKR without uploading a file each time."
)

with st.expander("Where do I find these?"):
    st.markdown("""
1. Log in to [IBKR Client Portal](https://www.interactivebrokers.com/sso/Login)
2. Go to **Performance & Reports > Flex Queries**
3. **Flex Query Token**: Click **Flex Web Service Configuration > Configure**. Copy the token shown (or generate a new one).
4. **Query ID**: On the same Flex Queries page, the numeric ID is shown next to each saved query. See the [Setup Guide](/Flex_Query_Setup_Guide) if you haven't created a query yet.
""")

has_creds = has_ibkr_credentials(user_id)
editing = st.session_state.get("editing_credentials", False)

if has_creds and not editing:
    # Show existing credentials (masked)
    creds = load_ibkr_credentials(user_id)
    if creds:
        token, query_id = creds
        masked_token = token[:4] + "*" * (len(token) - 4)
        st.text_input("Flex Token", value=masked_token, disabled=True)
        st.text_input("Query ID", value=query_id, disabled=True)

        col1, col2 = st.columns(2)
        if col1.button("Update Credentials"):
            st.session_state["editing_credentials"] = True
            st.rerun()
        if col2.button("Delete Credentials", type="secondary"):
            delete_ibkr_credentials(user_id)
            st.session_state.pop("editing_credentials", None)
            st.success("Credentials deleted.")
            st.rerun()
else:
    # Show form to save/update
    with st.form("ibkr_credentials_form"):
        token_input = st.text_input(
            "IBKR Flex Query Token",
            type="password",
            help="Found under Performance & Reports > Flex Queries > Flex Web Service Configuration",
        )
        query_id_input = st.text_input(
            "Flex Query ID",
            help="The numeric ID of your saved Flex Query",
        )
        submitted = st.form_submit_button("Save Credentials")

        if submitted:
            if not token_input or not query_id_input:
                st.error("Both fields are required.")
            else:
                save_ibkr_credentials(user_id, token_input, query_id_input)
                st.session_state.pop("editing_credentials", None)
                st.success("Credentials saved and encrypted.")
                st.rerun()

    if editing:
        if st.button("Cancel"):
            st.session_state.pop("editing_credentials", None)
            st.rerun()

st.divider()
st.info(
    "Your Flex Query token is encrypted before storage and can be deleted anytime. "
    "See the [Flex Query Setup Guide](/Flex_Query_Setup_Guide) for help finding these values.",
    icon="\U0001f512",
)
