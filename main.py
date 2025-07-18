import os
import logging
import hmac
import hashlib
import json
from flask import Flask, request
import requests
import google.generativeai as genai

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- Load Secrets from Environment ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
APP_SECRET = os.environ.get("APP_SECRET")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PAGE_ID = os.environ.get("FB_PAGE_ID")

# --- Gemini AI Configuration ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest')

SYSTEM_PROMPT = """You are a helpful and witty chatbot in a private friends' group on Facebook Messenger.
Your name is Gemini.
Your location is Pune, Maharashtra, India.
The current date is Friday, July 18, 2025.
Be friendly, conversational, use emojis, and keep your responses concise.
"""

def ask_gemini(prompt):
    """Sends a prompt to the Gemini API."""
    try:
        full_prompt = SYSTEM_PROMPT + "\n\nFriend's message: " + prompt
        response = model.generate_content(full_prompt)
        logger.info("Successfully received response from Gemini.")
        return response.text
    except Exception as e:
        logger.error(f"Error calling Gemini: {e}")
        return "Sorry, my AI brain is taking a little nap. Try again in a moment."

# --- Facebook Messenger Functions ---
GRAPH_API_URL = "https://graph.facebook.com/v19.0/me/messages"

def verify_webhook_signature(payload, signature):
    """Verifies the request signature."""
    if not signature:
        logger.warning("No signature provided in request.")
        return False
    try:
        hash_object = hmac.new(APP_SECRET.encode('utf-8'), payload, hashlib.sha1)
        expected_signature = 'sha1=' + hash_object.hexdigest()
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        logger.error(f"Error verifying signature: {e}")
        return False

def send_message(recipient_id, message_text):
    """Sends a message to a user."""
    try:
        message_data = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
        params = {"access_token": PAGE_ACCESS_TOKEN}
        response = requests.post(GRAPH_API_URL, params=params, json=message_data)
        response.raise_for_status()
        logger.info(f"Message sent successfully to {recipient_id}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message: {e}")

def process_message(sender_id, message_text):
    """Processes the incoming message and gets a response."""
    greetings = ['hi', 'hello', 'hey', 'yo']
    message_lower = message_text.lower()
    
    if message_lower in greetings or '?' in message_lower or len(message_text.split()) > 1:
        response = ask_gemini(message_text)
        send_message(sender_id, response)
    else:
        logger.info("Message too short, not sending to Gemini.")

# --- Flask Web Server Routes ---
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Handles webhook verification."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully!")
        return challenge, 200
    else:
        logger.warning("Webhook verification failed.")
        return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handles incoming messages."""
    payload = request.get_data()
    signature = request.headers.get('X-Hub-Signature')

    if not verify_webhook_signature(payload, signature):
        logger.warning("Invalid signature. Request rejected.")
        return 'Forbidden', 403
        
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")

                if sender_id == PAGE_ID:
                    return "OK", 200

                if messaging_event.get("message"):
                    message = messaging_event["message"]
                    if not message.get("is_echo") and "text" in message:
                        process_message(sender_id, message["text"])
                        
    return "OK", 200

@app.route('/')
def index():
    """A simple endpoint to confirm the server is running."""
    return "This is a Facebook Messenger bot webhook.", 200

if __name__ == '__main__':
    # This block is for local development and might not be used by Render's Gunicorn.
    logger.info("Starting bot server...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))


