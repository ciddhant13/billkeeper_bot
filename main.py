# Import necessary libraries
from keep_alive import keep_alive  # Assuming this is a custom module to keep the bot running

keep_alive()  # Start the keep-alive mechanism

import os
import telegram
# Updated import: Added ParseMode directly from telegram
from telegram import Update, InputFile, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from googleapiclient.discovery import build
from google.oauth2 import service_account
import google.generativeai as genai
from googleapiclient.http import MediaFileUpload
# PIL is not explicitly used in the provided logic after the fix,
# but might be needed if further image manipulation were required.
# from PIL import Image
from datetime import datetime
import pytz
import logging
import traceback  # Import traceback for detailed error logging
import re  # Import regex for more robust parsing
from collections import deque  # Use deque for efficient history limiting

# === SETUP SECTION === #

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables & Constants ---
try:
    # Load credentials and configuration from environment variables
    SERVICE_ACCOUNT_FILE = '/etc/secrets/service_account.json'  # Path to your service account key file
    # Ensure GOOGLE_DOC_ID is set in your environment
    DOC_ID = os.environ["GOOGLE_DOC_ID"]
    # Ensure BOT_TOKEN is set in your environment
    TELEGRAM_API_TOKEN = os.environ["BOT_TOKEN"]
    # Ensure GEMINI_API_KEY is set in your environment
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    # Ensure DRIVE_FOLDER_ID is set in your environment
    DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
except KeyError as e:
    logger.error(
        f"❌ Missing environment variable: {e}. Please set all required variables."
    )
    exit()  # Exit if essential configuration is missing

# --- Google API Setup ---
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',  # Scope for Google Drive file operations
    'https://www.googleapis.com/auth/documents'  # Scope for Google Docs operations
]
try:
    # Authenticate using the service account file
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    # Build Google Drive and Docs service objects
    drive_service = build('drive', 'v3', credentials=credentials)
    docs_service = build('docs', 'v1', credentials=credentials)
    logger.info("✅ Google API services initialized.")
except Exception as e:
    logger.error(f"❌ Failed to initialize Google API services: {e}")
    exit()

# --- Gemini API Setup ---
try:
    # Configure the Generative AI client
    genai.configure(api_key=GEMINI_API_KEY)
    # Initialize the Gemini model
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    logger.info("✅ Gemini API configured.")
except Exception as e:
    logger.error(f"❌ Failed to configure Gemini API: {e}")
    exit()

# --- Telegram Bot Setup ---
try:
    # Initialize the Telegram bot
    bot = telegram.Bot(token=TELEGRAM_API_TOKEN)
    logger.info("✅ Telegram Bot initialized.")
except Exception as e:
    logger.error(f"❌ Failed to initialize Telegram Bot: {e}")
    exit()

# === HELPER FUNCTIONS === #


def escape_markdown_v2(text: str) -> str:
    """Escapes characters for Telegram MarkdownV2 formatting."""
    # Characters to escape as per Telegram API documentation
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    # Replace each special character with its escaped version
    return ''.join(['\\' + c if c in escape_chars else c for c in text])


def upload_to_drive(file_path: str, filename: str) -> str:
    """Uploads a file to a specific Google Drive folder and returns the file ID."""
    logger.info(f"🚀 Uploading '{filename}' to Google Drive...")
    # Define metadata for the file (name and parent folder)
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    # Create a media uploader object
    media = MediaFileUpload(file_path, resumable=True)
    try:
        # Execute the file creation request
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'  # Request only the file ID in the response
        ).execute()
        file_id = uploaded_file['id']
        logger.info(f"✅ File uploaded successfully. Drive File ID: {file_id}")
        return file_id
    except Exception as e:
        logger.error(f"❌ Google Drive upload failed for '{filename}': {e}")
        raise  # Re-raise the exception to be caught by the handler


def extract_bill_details_from_gemini(file_path: str) -> str:
    """Extracts bill details from a file (PDF or image) using Gemini."""
    logger.info(
        f"🧠 Analyzing file '{os.path.basename(file_path)}' with Gemini...")
    # Define the prompt for the Gemini model
    prompt = (
        "You are a helpful assistant. Extract all relevant information from the attached bill. "
        "Include: date, time, total amount (with breakdown if possible), merchant or establishment name, "
        "items or services purchased/rented/subscribed, location (if available), and anything else useful. "
        "Format the result as a readable paragraph for future reference. After the paragraph, use clean bullet points "  # Ensure prompt requests paragraph first
        "to highlight these key pieces of information for easy readability. Use a double newline to separate the paragraph and the bullet points."  # Added instruction for separator
        "Do NOT add or hallucinate information. "
        "If the document does not look like a bill, clearly state that.")

    # Read the file content in binary mode
    with open(file_path, 'rb') as f:
        file_data = f.read()

    # Determine the MIME type based on the file extension
    file_extension = file_path.lower().split('.')[-1]
    if file_extension == "pdf":
        mime_type = "application/pdf"
    elif file_extension in ('png', 'jpg', 'jpeg'):
        mime_type = f"image/{'jpeg' if file_extension == 'jpg' else file_extension}"
    else:
        logger.warning(
            f"⚠️ Unsupported file type for Gemini analysis: {file_extension}")
        raise ValueError(f"Unsupported file type: .{file_extension}")

    # Prepare the file input for the Gemini API
    file_input = {"mime_type": mime_type, "data": file_data}

    try:
        # Generate content using the Gemini model
        response = gemini_model.generate_content([prompt, file_input])
        # Handle potential lack of text in response
        extracted_text = ""
        if response.parts:
            extracted_text = "".join(part.text for part in response.parts
                                     if hasattr(part, 'text')).strip()
        else:
            # Fallback if response.parts is empty but response.text exists (older API versions?)
            extracted_text = response.text.strip()

        if not extracted_text and response.prompt_feedback.block_reason:
            logger.warning(
                f"Gemini content blocked: {response.prompt_feedback.block_reason}"
            )
            # Optionally, return a specific message indicating blockage
            # return f"(Content blocked by safety settings: {response.prompt_feedback.block_reason})"
            raise Exception(
                f"Content generation blocked: {response.prompt_feedback.block_reason}"
            )  # Or raise error

        logger.info("✅ Bill details extracted successfully by Gemini.")
        return extracted_text
    except Exception as e:
        # Log detailed error information if Gemini fails
        logger.error(
            f"❌ Gemini analysis failed for '{os.path.basename(file_path)}': {e}"
        )
        logger.error(traceback.format_exc())  # Log the full traceback
        # Try to access potentially more detailed error information if available
        try:
            # Check if the response has safety ratings or prompt feedback
            if hasattr(response, 'prompt_feedback'
                       ) and response.prompt_feedback.block_reason:
                logger.error(
                    f"Gemini Block Reason: {response.prompt_feedback.block_reason}"
                )
            if hasattr(response, 'candidates'
                       ) and response.candidates and response.candidates[
                           0].finish_reason != 'STOP':
                logger.error(
                    f"Gemini Finish Reason: {response.candidates[0].finish_reason}"
                )
        except Exception:
            pass  # Ignore errors during detailed error logging
        raise  # Re-raise the exception


def update_google_doc(text_to_insert: str):
    """Inserts text at the beginning of the specified Google Doc."""
    logger.info(f"📝 Updating Google Doc (ID: {DOC_ID})...")
    # Define the request to insert text at the beginning (index 1)
    requests = [{
        'insertText': {
            'location': {
                'index': 1
            },
            'text': text_to_insert + "\n\n"  # Add extra newlines for spacing
        }
    }]
    try:
        # Execute the batch update request
        docs_service.documents().batchUpdate(documentId=DOC_ID,
                                             body={
                                                 'requests': requests
                                             }).execute()
        logger.info("✅ Google Doc updated successfully.")
    except Exception as e:
        logger.error(f"❌ Google Doc update failed: {e}")
        raise  # Re-raise the exception


# === CORE PROCESSING FUNCTION === #


def process_file(update: Update, context: CallbackContext, local_path: str,
                 original_filename: str):
    """Handles the core logic: Gemini extraction, Drive upload, Doc update, and reply."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    logger.info(
        f"🔄 Processing file '{original_filename}' from user {user_id} in chat {chat_id}."
    )

    processing_message = None  # To store the "Processing..." message object
    try:
        # 1. Send "Processing..." message
        processing_message = context.bot.send_message(
            chat_id, "⏳ Processing your bill, please wait...")

        # 2. Extract details using Gemini (gets the full text)
        extracted_text = extract_bill_details_from_gemini(local_path)

        # 3. Check if it's a bill (using the full text)
        if "does not look like a bill" in extracted_text.lower():
            logger.warning(
                f"⚠️ File '{original_filename}' does not look like a bill.")
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=
                "⚠️ The uploaded file doesn't seem to be a bill. Skipping processing."
            )
            # Clear conversation history if a non-bill is uploaded,
            # as the context might become irrelevant.
            if 'history' in context.user_data:
                del context.user_data['history']
                logger.info(
                    f"🧹 Cleared conversation history for user {user_id} due to non-bill upload."
                )
            return  # Stop processing if it's not a bill

        # 4. Upload to Google Drive
        drive_file_id = upload_to_drive(local_path, original_filename)
        drive_link = f"https://drive.google.com/file/d/{drive_file_id}/view"

        # 5. Format Timestamp
        timezone = pytz.timezone('Asia/Kolkata')
        timestamp = update.message.date.astimezone(timezone).strftime(
            '%Y-%m-%d %H:%M:%S %Z')

        # 6. Prepare FULL text for Google Doc
        final_text_for_doc = (
            f"\n📄 Bill Processed on: {timestamp}\n"
            f"👤 Processed for User ID: {user_id}\n"
            f"🏷️ Original Filename: {original_filename}\n\n"
            f"{extracted_text}\n\n"  # Use the full extracted text here
            f"🔗 Google Drive Link: {drive_link}\n"
            f"----------------------------------------------------------------------\n"
        )

        # 7. Update Google Doc with FULL text
        update_google_doc(final_text_for_doc)

        # 8. Send confirmation to user (edit the "Processing..." message)
        #    Only include success message and Drive link.
        escaped_intro = escape_markdown_v2(
            "✅ Bill uploaded and processed successfully!")
        escaped_drive_link = escape_markdown_v2(
            drive_link)  # Escape the link URL itself

        reply_text = (
            f"{escaped_intro}\n\n"  # Only the success message
            # Format the link using MarkdownV2 syntax
            f"🔗 [Click to view bill in Drive]({escaped_drive_link})")

        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_message.message_id,
            text=reply_text,
            # Updated usage: Use ParseMode directly
            parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(
            f"✅ Successfully processed '{original_filename}' for user {user_id}. Sent success confirmation to chat."
        )

    except ValueError as e:  # Catch specific unsupported file type error
        logger.warning(
            f"⚠️ Value Error during processing for user {user_id}: {e}")
        if processing_message:
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=f"⚠️ Skipping file: {e}")
        else:  # If sending initial message failed
            update.message.reply_text(f"⚠️ Skipping file: {e}")

    except Exception as e:
        # Catch all other exceptions during processing
        logger.error(f"❌ Error processing file for user {user_id}: {e}",
                     exc_info=True)  # Log traceback
        error_message = f"❌ Sorry, an error occurred while processing your file: {e}. Please try again later or contact support if the issue persists."
        if processing_message:
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_message.message_id,
                text=error_message)
        else:
            update.message.reply_text(error_message)

    finally:
        # 9. Clean up the downloaded file
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
                logger.info(f"🧹 Cleaned up temporary file: {local_path}")
        except Exception as e:
            logger.error(
                f"⚠️ Failed to clean up temporary file '{local_path}': {e}")


# === TELEGRAM HANDLERS === #


def start(update: Update, context: CallbackContext):
    """Handler for the /start command."""
    user_name = update.effective_user.first_name
    user_id = update.effective_user.id
    logger.info(
        f"🏁 /start command received from user {user_id} ({user_name}).")
    # Clear any previous history when the user starts/restarts the conversation
    if 'history' in context.user_data:
        del context.user_data['history']
        logger.info(
            f"🧹 Cleared conversation history for user {user_id} on /start.")

    update.message.reply_text(
        f"👋 Hello {user_name}! Send me a bill (PDF, PNG, JPG, JPEG) as a document or photo, "
        "and I'll extract the details, save it to Google Drive, and log it in our Google Doc.\n\n"
        "You can also ask me questions about your past bills!")


def handle_document(update: Update, context: CallbackContext):
    """Handles incoming documents (PDFs, or images sent as files)."""
    if not update.message.document:
        logger.warning("handle_document called without a document.")
        return

    doc = update.message.document
    file_id = doc.file_id
    file_name = doc.file_name  # Get the original filename
    logger.info(f"📄 Document received: '{file_name}' (ID: {file_id})")

    # Define the local path to save the downloaded file
    local_path = f"./{file_name}"  # Save in current directory

    try:
        # Download the file
        tg_file = context.bot.get_file(file_id)
        tg_file.download(local_path)
        logger.info(f"✅ Document '{file_name}' downloaded to '{local_path}'.")

        # Process the downloaded file
        process_file(update, context, local_path, file_name)

    except Exception as e:
        logger.error(f"❌ Error handling document '{file_name}': {e}",
                     exc_info=True)
        update.message.reply_text(
            f"❌ Sorry, failed to download or process the document: {e}")
        # Ensure cleanup even if download fails partially or process_file isn't called
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                logger.info(
                    f"🧹 Cleaned up partially downloaded/failed file: {local_path}"
                )
            except Exception as cleanup_e:
                logger.error(
                    f"⚠️ Failed to clean up file '{local_path}' after error: {cleanup_e}"
                )


def handle_photo(update: Update, context: CallbackContext):
    """Handles incoming photos (images sent as compressed photos)."""
    if not update.message.photo:
        logger.warning("handle_photo called without a photo.")
        return

    # Get the highest resolution photo available
    photo = update.message.photo[-1]
    file_id = photo.file_id
    logger.info(f"🖼️ Photo received (ID: {file_id})")

    # Create a filename (Telegram photos don't have inherent filenames)
    # We'll use the file_id and assume .jpg as Telegram often converts
    file_name = f"photo_{file_id}.jpg"
    local_path = f"./{file_name}"  # Save in current directory

    try:
        # Download the photo
        tg_file = context.bot.get_file(file_id)
        tg_file.download(local_path)
        logger.info(f"✅ Photo (ID: {file_id}) downloaded to '{local_path}'.")

        # Process the downloaded photo
        process_file(update, context, local_path,
                     file_name)  # Use the generated filename

    except Exception as e:
        logger.error(f"❌ Error handling photo (ID: {file_id}): {e}",
                     exc_info=True)
        update.message.reply_text(
            f"❌ Sorry, failed to download or process the photo: {e}")
        # Ensure cleanup even if download fails partially or process_file isn't called
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                logger.info(
                    f"🧹 Cleaned up partially downloaded/failed file: {local_path}"
                )
            except Exception as cleanup_e:
                logger.error(
                    f"⚠️ Failed to clean up file '{local_path}' after error: {cleanup_e}"
                )


def handle_question(update: Update, context: CallbackContext):
    """Handles text messages, incorporating conversation history."""
    user_query = update.message.text
    user_id = update.effective_user.id
    # Use chat_id for chat-specific history if the bot is used in groups
    # For simplicity, we'll use user_data which is user-specific across chats
    logger.info(f"❓ Question received from user {user_id}: '{user_query}'")

    # --- History Management ---
    # Initialize history if it doesn't exist, using deque for max length
    # Store tuples of (question, answer)
    if 'history' not in context.user_data:
        context.user_data['history'] = deque(maxlen=5)  # Keep last 5 Q&A pairs

    history = context.user_data['history']
    # Format history for the prompt
    history_str = "\n".join([f"User: {q}\nAssistant: {a}" for q, a in history])
    # --- End History Management ---

    try:
        # 1. Fetch the entire content of the Google Doc
        logger.info("📚 Fetching Google Doc content for context...")
        doc = docs_service.documents().get(documentId=DOC_ID,
                                           fields='body/content').execute()
        all_text = ""
        content = doc.get('body', {}).get('content', [])
        for element in content:
            paragraph = element.get('paragraph', {})
            elements = paragraph.get('elements', [])
            for elem in elements:
                text_run = elem.get('textRun', {})
                all_text += text_run.get('content', '')
        logger.info(f"📄 Retrieved {len(all_text)} characters from Google Doc.")

        if not all_text.strip():
            logger.warning("⚠️ Google Doc is empty. Cannot answer questions.")
            update.message.reply_text(
                "⚠️ The bill history document seems empty. I can't answer questions yet."
            )
            return

        # 2. Prepare the prompt for Gemini, including history
        prompt = (
            "You are an assistant specialized in answering questions based *only* on the provided bill history document AND the recent conversation history below. "
            "Use the conversation history to understand context from previous turns if relevant to the current question. "
            "Do not use any external knowledge or make assumptions. "
            "Analyze the bill history and the conversation history to answer the user's current question concisely and factually. "
            "If the answer cannot be found *directly* within the provided texts (bill history + conversation history), explicitly state that the information is not available.\n\n"
            f"--- Bill History Start ---\n{all_text.strip()}\n--- Bill History End ---\n\n"
            f"--- Recent Conversation History (Oldest First) ---\n{history_str if history_str else 'No previous conversation.'}\n--- Conversation History End ---\n\n"
            f"Current User Question: {user_query}")

        # 3. Ask Gemini
        logger.info(
            "🧠 Asking Gemini to answer the question based on document and conversation context..."
        )
        response = gemini_model.generate_content(prompt)

        # Handle potential lack of text in response more robustly
        answer = ""
        if hasattr(response, 'parts') and response.parts:
            answer = "".join(part.text for part in response.parts
                             if hasattr(part, 'text')).strip()
        elif hasattr(
                response, 'text'
        ):  # Fallback for older API or different response structure
            answer = response.text.strip()

        # Check for blocked content *after* trying to extract text
        if not answer and hasattr(
                response,
                'prompt_feedback') and response.prompt_feedback.block_reason:
            logger.warning(
                f"Gemini content blocked for user {user_id}: {response.prompt_feedback.block_reason}"
            )
            answer = f"⚠️ Sorry, my response was blocked due to safety settings ({response.prompt_feedback.block_reason}). Please rephrase your question."
        elif not answer:
            logger.warning(
                f"Gemini returned an empty answer for user {user_id}.")
            answer = "🤔 Sorry, I couldn't generate a response for that question."
        else:
            logger.info("✅ Gemini provided an answer.")
            # --- Update History ---
            # Add the current question and its answer to the history
            history.append((user_query, answer))
            context.user_data[
                'history'] = history  # Store it back (though deque modifies in-place)
            logger.info(
                f"📝 Added Q&A to history for user {user_id}. History size: {len(history)}"
            )
            # --- End Update History ---

    except Exception as e:
        logger.error(f"❌ Error handling question from user {user_id}: {e}",
                     exc_info=True)
        answer = "❌ Sorry, I encountered an error while trying to answer your question. Please try again."

    # 4. Reply to the user
    update.message.reply_text(answer)


# === MAIN EXECUTION === #


def main():
    """Starts the Telegram bot."""
    logger.info("🚀 Starting bot application...")
    # Create the Updater and pass it the bot's token.
    updater = Updater(TELEGRAM_API_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # --- Register Handlers ---
    # Command handlers
    dp.add_handler(CommandHandler("start", start))

    # Message handlers
    # Handle documents (PDF, PNG, JPG sent as files)
    dp.add_handler(
        MessageHandler(
            Filters.document.mime_type("application/pdf")
            | Filters.document.mime_type("image/jpeg")
            | Filters.document.mime_type("image/png"), handle_document))
    # Handle photos (PNG, JPG sent as photos)
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))

    # Handle regular text messages (questions) - must be after file handlers
    dp.add_handler(
        MessageHandler(Filters.text & ~Filters.command, handle_question))

    # --- Start the Bot ---
    # Start the Bot's polling mechanism
    updater.start_polling()
    logger.info("✅ Bot is now polling for updates from Telegram...")

    # Keep the bot running until interrupted (e.g., Ctrl+C)
    updater.idle()
    logger.info("🛑 Bot polling stopped.")


if __name__ == '__main__':
    main()
