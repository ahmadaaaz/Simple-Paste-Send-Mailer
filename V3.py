import streamlit as st
import pandas as pd
import smtplib
from email.message import EmailMessage
import io
import time
from email.utils import make_msgid
import mimetypes
import markdown
import re

st.set_page_config(layout="wide")
st.title("🚀 Simple Paste & Send Mailer")

# --- STEP 1: PASTE DATA ---
st.warning("Mail column's title must be " '"Email"')
st.subheader("1. Paste Data From Google Sheets")
raw_pasted_data = st.text_area("Copy your rows (including headers) and paste here:", height=250)

df = None
if raw_pasted_data:
    try:
        # Google Sheets copies data separated by tabs (\t). 
        # io.StringIO tricks pandas into reading the raw text string like an actual file.
        df = pd.read_csv(io.StringIO(raw_pasted_data), sep="\t")
        st.success("✅ Data read successfully! Preview below:")
        st.dataframe(df)
    except Exception as e:
        st.error(f"Could not parse data. Make sure you included the column headers. Error: {e}")

if df is not None:
    st.divider()
    
    # --- STEP 2 & 3: DRAFT AND LIVE PREVIEW ---
    # Using columns to put the drafter and preview side-by-side
    col1, col2 = st.columns(2)
    
    
    st.subheader("2. Draft & Live Preview")
    email_subject = st.text_input("Email Subject", value="Inquiry from Bayeng")
    email_body = st.text_area(
        "Email Content", 
        height=300,
        value="Hello {Contact Person},\n\nWe are interested in your capabilities regarding your {Category}."
    )
    uploaded_attachments = st.file_uploader(
                "Attach a General File (PDF, DOCX, etc.)", 
                type=["pdf", "doc", "docx", "png", "jpg", "jpeg", "xlsx"], accept_multiple_files=True
            )

    uploaded_logo = st.file_uploader("Attach Signature Logo", type=["png", "jpg", "jpeg"])
    # --- NEW: Disclaimer Box ---
    email_disclaimer = st.text_area(
        "Disclaimer (Appears below the signature logo)", 
        value="<small><span style='color: gray;'>This email and any attachments are confidential and intended solely for the use of the individual or entity to whom they are addressed.</span></small>",
        height=100
    )
    # ---------------------------
    st.subheader("👀 Live Preview:\n")
    if len(df) > 0:
        # 1. Create a list of row numbers from 1 to the total number of rows
        preview_options = list(range(1, len(df) + 1))
        # 2. Add the dropdown widget displaying just the row numbers
        selected_row_num = st.selectbox("Select row number to preview:", preview_options, index=0)
        # 3. Subtract 1 to convert the user's choice back to a 0-indexed pandas location
        selected_index = selected_row_num - 1  
        # 4. Pull the dictionary for the chosen row
        selected_row = df.iloc[selected_index].to_dict()
        try:
            # This generates the preview dynamically
            preview_body = email_body.format(**selected_row) 
            
            # --- THE FIX: Force Streamlit to show every empty line ---
            preview_body = preview_body.replace("\n", "  \n")
            
            st.info(f"**Subject:** {email_subject}\n\n{preview_body}\n\n*(Your uploaded logo will appear here)*\n\n{email_disclaimer}")
        except KeyError as e:
            st.error(f"⚠️ Missing column in your pasted data: {e}. Check your spelling inside the brackets!")

    st.divider()
    
    # --- STEP 4: SMTP LOGIN & SEND ---
    st.subheader("3. Finalize & Send")
    st.write("Enter your credentials to authorize the dispatch.")
    
    login_col1, login_col2 = st.columns(2)
    smtp_host = login_col1.text_input("SMTP Host", value="mail.bayeng.com.tr")
    smtp_port = login_col2.number_input("SMTP Port", value=465)
    email_user = login_col1.text_input("Your Email (e.g., you@bayeng.com.tr)")
    email_pass = login_col2.text_input("Your Email Password", type="password")
    
    if st.button("🔥 Start Sending Emails One-by-One", use_container_width=True):
        if not email_user or not email_pass:
            st.error("Please fill out your SMTP login credentials first.")
        else:
            try:
                with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                    server.login(email_user, email_pass)
                    
                    status_text = st.empty()
                    progress_bar = st.progress(0)
                    
                    for index, row in df.iterrows():
                        row_dict = row.to_dict()
                        
                        try:
                            personalized_body = email_body.format(**row_dict)
                        except KeyError:
                            break # Skip if there's a formatting error
                        
                        target_email = row_dict.get("Email")
                        if not target_email or pd.isna(target_email):
                            continue
                        
                        msg = EmailMessage() 
                        msg['Subject'] = email_subject
                        msg['From'] = email_user
                        msg['To'] = str(target_email).strip()
                        
                        # --- THE MAGIC FIX FOR BOLD, BULLETS & MULTI-LINES ---
                        # 1. Preserve multiple consecutive empty lines by turning extra newlines into HTML breaks
                        processed_body = re.sub(r'\n{3,}', lambda m: '<br>' * (len(m.group(0))), personalized_body)
                        
                        # 2. Convert markdown (**bold**, * bullets, etc.) into clean HTML
                        formatted_body = markdown.markdown(processed_body, extensions=['nl2br'])
                        # --- NEW: Process the disclaimer ---
                        formatted_disclaimer = markdown.markdown(email_disclaimer, extensions=['nl2br'])
                        # -----------------------------------------------------

                        if uploaded_logo is not None:
                            image_cid = make_msgid() 
                            html_content = f"<html><body>{formatted_body}<br><br><img src='cid:{image_cid[1:-1]}'><br><br>{formatted_disclaimer}</body></html>"
                            msg.set_content(html_content, subtype='html')
                            
                            image_bytes = uploaded_logo.getvalue()
                            file_ext = uploaded_logo.name.split('.')[-1].lower()
                            img_subtype = 'jpeg' if file_ext == 'jpg' else file_ext 
                            msg.add_related(image_bytes, 'image', img_subtype, cid=image_cid)
                        else:
                            html_content = f"<html><body>{formatted_body}<br><br>{formatted_disclaimer}</body></html>"
                            msg.set_content(html_content, subtype='html')

                        # 2. GENERAL ATTACHMENT LOGIC MUST GO SECOND
                        if uploaded_attachments: # Checks if the list has any files inside
                            for single_file in uploaded_attachments: # Loops through them one by one
                                file_data = single_file.getvalue()
                                file_name = single_file.name
                                
                                # Guess if it's an application (pdf/doc) or image based on file extension
                                mime_type, _ = mimetypes.guess_type(file_name)
                                if mime_type is None:
                                    mime_type = 'application/octet-stream' # Safe fallback
                                    
                                maintype, subtype = mime_type.split('/', 1)
                                
                                # Staple the file to the email
                                msg.add_attachment(
                                    file_data, 
                                    maintype=maintype, 
                                    subtype=subtype, 
                                    filename=file_name
                                )
                        # 1. SEND MESSAGE TO RECIPIENT
                        server.send_message(msg)
                        
                        # 3. UPDATE PROGRESS BAR ON SCREEN
                        status_text.text(f"✅ [{index + 1}/{len(df)}] Sent to: {target_email}")
                        progress_bar.progress((index + 1) / len(df))
                        
                        # 4. WAIT 15 SECONDS BEFORE THE NEXT LOOP
                        timer_placeholder = st.empty()
                        for seconds in range(15, 0, -1):
                            timer_placeholder.info(f"⏳ Waiting {seconds} seconds before sending next email...")
                            time.sleep(1) 
                            
                        # Clear the timer message once it reaches 0
                        timer_placeholder.empty()
                        
                st.success("🎉 Complete! All emails in this batch have been processed.")
            except Exception as err:
                st.error(f"SMTP Connection Error: {err}")
                st.success("🎉 Complete! All emails in this batch have been processed.")
            except Exception as err:
                st.error(f"SMTP Connection Error: {err}")
