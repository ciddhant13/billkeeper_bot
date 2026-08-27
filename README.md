# Billkeeper Bot 🤖🧾

An AI-powered Telegram bot that automates comprehensive bill and invoice tracking by extracting rich data from your documents and seamlessly syncing everything to Google Workspace.

## The Problem
Keeping track of receipts, invoices, and warranties is traditionally a tedious, manual process. You get a physical receipt, stuff it in a drawer, and eventually have to manually type the details into a spreadsheet. 

Crucial metadata—like warranty expiration dates, tax breakdowns, and specific vendor info—is often lost or forgotten entirely. Later, when an appliance like your washing machine breaks down, finding out if it's still under warranty (which dictates whether you pay out of pocket for service repair costs) turns into a stressful scavenger hunt through old files and faded receipts.

## The Solution
**Billkeeper Bot** eliminates manual data entry and lost warranties by turning your Telegram app into a smart financial and document assistant. 

Instead of typing out expenses or filing papers, you simply send a photo or PDF of your bill to the bot. Using Google's Gemini AI, the bot instantly reads the document, extracts comprehensive data (including amounts, taxes, vendor details, and warranty periods), archives the original file in Google Drive, and logs the extracted details into a running Google Doc ledger.

Most importantly, it functions as an interactive conversational agent. You can simply ask the bot questions about your past purchases, and it will give you the answers instantly.

## ✨ Key Features
- **Comprehensive AI Extraction**: Powered by Google Gemini, the bot goes beyond simple expense tracking. It accurately reads physical photos or digital PDFs to extract vendors, dates, taxes, specific line items, and critical warranty information.
- **Conversational AI Assistant**: This is not just a logger; it's a chatbot! If you forget how long the warranty on your washing machine lasts, you don't need to dig through your Google Docs—just ask the bot directly in Telegram, and it will retrieve the answer from your history.
- **Automated Cloud Archiving**: Automatically uploads every receipt image or PDF directly to a designated Google Drive folder so you never lose a proof of purchase.
- **Live Ledger Syncing**: Instantly appends the extracted bill details to a centralized Google Doc, creating an automated, running ledger of your expenses and invoices.
- **Always-On Availability**: Includes a lightweight Flask server (`keep_alive.py`) designed to keep the bot running continuously on cloud platforms like Replit or Render.

## 🛠️ Tech Stack
- **Language**: Python 3
- **Bot Framework**: `python-telegram-bot`
- **AI & Vision**: Google Generative AI (Gemini), `pdf2image`, `Pillow` (PIL)
- **Cloud Integrations**: Google Drive API, Google Docs API
- **Web Server**: Flask (for background keep-alive)

## 🚀 Setup & Installation

### Prerequisites
1. Python 3.8+
2. A Telegram Bot Token (from [@BotFather](https://t.me/botfather))
3. A Google Cloud Console project with the following enabled:
   - Google Drive API
   - Google Docs API
4. A Google service account with a `service_account.json` key file.
5. A Google Gemini API Key.

### Local Installation
1. **Clone the repository:**
   ```bash
   git clone https://github.com/ciddhant13/billkeeper_bot.git
   cd billkeeper_bot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in the root directory and add the following:
   ```ini
   BOT_TOKEN=your_telegram_bot_token
   GEMINI_API_KEY=your_gemini_api_key
   GOOGLE_DOC_ID=your_target_google_doc_id
   DRIVE_FOLDER_ID=your_target_google_drive_folder_id
   ```

4. **Add Google Credentials:**
   Place your `service_account.json` file in the root directory. *(Note: Ensure this file and `.env` are never committed to version control. They are ignored by default in the provided `.gitignore`).*

5. **Run the bot:**
   ```bash
   python main.py
   ```

## 💡 Usage
1. Open Telegram and start a chat with your bot.
2. Send a photo or a PDF of any bill, invoice, or receipt.
3. Wait a few seconds while the bot analyzes the document, extracts warranties and taxes, uploads it to Google Drive, and updates your Google Doc.
4. Ask the bot follow-up questions about your expenses! (e.g., *"When does the warranty on my washing machine expire?"*)
