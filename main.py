import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from flask import Flask, request
import threading

# Initialize Flask app
app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json_str, application.bot)
    application.process_update(update)
    return 'ok'

def run_server():
    app.run(host='0.0.0.0', port=80)

# Load doctor profiles from a JSON file
def load_profiles():
    try:
        with open('doctors.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return []

def save_profiles(profiles):
    with open('doctors.json', 'w') as file:
        json.dump(profiles, file, indent=4)

# Load ward information from a JSON file
def load_ward_info():
    try:
        with open('wards.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Load admission data from a JSON file
def load_admissions():
    try:
        with open('admissions.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Global variable to track the current state of each user
user_states = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_states[user_id] = {'step': 'roll_number'}
    await update.message.reply_text("Please enter your roll number:")

async def ward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        ward_number = context.args[0].strip()
        if len(ward_number) == 2 and ward_number.isdigit():
            results = search_doctors_by_ward(ward_number)
            ward_info = load_ward_info().get(ward_number, None)
            if results:
                response = "Doctors currently in ward " + ward_number + ":\n\n"
                for doctor in results:
                    response += f"Name: Dr. {doctor['name']}\n"
                    response += f"Roll Number: {doctor['rollNumber']}\n"
                    response += f"Mobile Number: {doctor['mobileNumber']}\n\n"

                response += "----------\n"
                if ward_info:
                    ward_name = ward_info.get('name', 'No ward name available')
                    unit = ward_info.get('unit', 'No unit information available')
                    unit_head = ward_info.get('unitHead', 'No unit head information available')

                    response += f"Ward Name: {ward_name}\n"
                    response += f"Unit: {unit}\n"
                    response += f"Unit Head: {unit_head}\n"
                else:
                    response += "No additional information available for this ward."

                await update.message.reply_text(response)
            else:
                await update.message.reply_text(f"There is no one in ward {ward_number} currently.")
        else:
            await update.message.reply_text("Please enter a valid 2-digit ward number.")
    else:
        await update.message.reply_text("Please provide a ward number as an argument, e.g., 22")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    message_text = update.message.text.strip().lower()

    if user_id in user_states:
        state = user_states[user_id]['step']

        if state == 'roll_number':
            roll_number = message_text
            profiles = load_profiles()
            doctor = next((doc for doc in profiles if doc['rollNumber'] == roll_number), None)
            if doctor:
                user_states[user_id] = {'step': 'current_ward', 'doctor': doctor}
                await update.message.reply_text(f"Hello Dr. {doctor['name']}, please enter your current ward number:")
            else:
                await update.message.reply_text("Roll number not found. Please enter your roll number again:")

        elif state == 'current_ward':
            if len(message_text) == 2 and message_text.isdigit():
                doctor = user_states[user_id]['doctor']
                profiles = load_profiles()
                # Update the current ward in the profiles
                for doc in profiles:
                    if doc['rollNumber'] == doctor['rollNumber']:
                        doc['currentWard'] = message_text
                        break
                save_profiles(profiles)
                previous_ward = doctor.get('currentWard', 'Unknown')
                user_states.pop(user_id, None)
                await update.message.reply_text(
                    f"Welcome back Dr. {doctor['name']}!\n"
                    f"Your previous ward was: {previous_ward}\n"
                    f"Your current ward is: {message_text}"
                )
            else:
                await update.message.reply_text("Please enter a valid 2-digit ward number.")

    elif message_text == 'admission':
        await admission(update, context)
    elif len(message_text) == 2 and message_text.isdigit():
        ward_number = message_text
        results = search_doctors_by_ward(ward_number)
        ward_info = load_ward_info().get(ward_number, None)
        if results:
            response = "Doctors currently in ward " + ward_number + ":\n\n"
            for doctor in results:
                response += f"Name: Dr. {doctor['name']}\n"
                response += f"Roll Number: {doctor['rollNumber']}\n"
                response += f"Mobile Number: {doctor['mobileNumber']}\n\n"

            response += "---------------------\n"
            if ward_info:
                ward_name = ward_info.get('name', 'No ward name available')
                unit = ward_info.get('unit', 'No unit information available')
                unit_head = ward_info.get('unitHead', 'No unit head information available')

                response += f"Ward Name: {ward_name}\n"
                response += f"Unit: {unit}\n"
                response += f"Unit Head: {unit_head}\n"
            else:
                response += "No additional information available for this ward."

            await update.message.reply_text(response)
        else:
            await update.message.reply_text(f"There is no one in ward {ward_number} currently.")
    else:
        search_query = message_text
        if search_query:
            profiles = load_profiles()
            matching_doctors = [doc for doc in profiles if search_query.lower() in doc['name'].lower()]

            if matching_doctors:
                keyboard = [[InlineKeyboardButton(doc['name'], callback_data=f"show_{doc['rollNumber']}")] for doc in matching_doctors]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text('Select a doctor:', reply_markup=reply_markup)
            else:
                await update.message.reply_text("No doctors found with that name.")

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    profiles = load_profiles()

    if data.startswith("show_"):
        roll_number = data.split("_")[1]
        doctor = next((doc for doc in profiles if doc['rollNumber'] == roll_number), None)
        if doctor:
            await query.message.reply_text(
                f"Name: Dr. {doctor['name']}\n"
                f"Roll Number: {doctor['rollNumber']}\n"
                f"Current Ward: {doctor.get('currentWard', 'Unknown')}\n"
                f"Mobile Number: {doctor['mobileNumber']}"
            )
        else:
            await query.message.reply_text("Doctor not found.")

def search_doctors_by_ward(ward_number):
    profiles = load_profiles()
    return [doc for doc in profiles if doc.get('currentWard', '').strip() == ward_number]

async def admission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admissions = load_admissions()
    today = datetime.now().strftime("%d/%m/%y")

    if admissions:
        response = f"ADMISSION INFO\nDate: {today}\n------------------\n"
        found = False
        for department, records in admissions.items():
            department_info = [f"Ward: {record['ward']}" for record in records if record['date'] == today]
            if department_info:
                response += f"{department.capitalize()}: {', '.join(department_info)}\n"
                found = True

        if not found:
            response = "No admissions for today."

        await update.message.reply_text(response)
    else:
        await update.message.reply_text("No admission information available.")

def main():
    global application
    # Initialize the Telegram bot
    application = ApplicationBuilder().token("7474836822:AAGQx5Ci4qRAAuD8WMHXz1Xo--NsvJbiVWY").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ward", ward))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_query))

    # Start Flask server in a separate thread
    threading.Thread(target=run_server).start()

    # Set the webhook for the bot
    application.bot.set_webhook(url='https://f786ea9f-2368-4c08-9101-1941526c58b5-00-r2vnpp8t6l6a.pike.replit.dev:3000/')

    # Start the bot polling (optional, in case webhook fails)
    application.run_polling()

if __name__ == '__main__':
    main()
