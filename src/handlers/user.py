from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.db import (
    get_destinations, get_destination_by_id, get_next_buses, 
    get_schedule_details, is_date_holiday, get_distinct_from_points
)
from src.utils.time_helper import (
    get_local_now, get_current_time_24h, format_24h_to_12h, 
    calculate_wait_time_minutes, format_wait_time, calculate_expected_arrival
)
from src.config import logger, BANNER_PATH

def get_day_type(now) -> str:
    """Helper to determine schedule day type based on local time and database holidays."""
    date_str = now.strftime("%Y-%m-%d")
    if is_date_holiday(date_str):
        return "holiday"
    if now.weekday() == 6: # 6 is Sunday
        return "sunday"
    return "weekday"

def get_menu_keyboard() -> InlineKeyboardMarkup:
    """Helper to construct the main start menu inline keyboard dynamically."""
    destinations = get_destinations()
    keyboard = []
    
    # 1. Destinations as primary buttons
    for dest in destinations:
        keyboard.append([
            InlineKeyboardButton(f"📍 {dest['name']}", callback_data=f"dest_{dest['id']}")
        ])
        
    # 2. Veyil app and Available Now feature buttons
    keyboard.append([
        InlineKeyboardButton("☀ Veyil", url="https://veyil.app"),
        InlineKeyboardButton("🚌 Available Now", callback_data="available_now")
    ])
    
    return InlineKeyboardMarkup(keyboard)

async def update_menu_message(query, context, text, reply_markup) -> None:
    """Updates the message content, deleting the photo message if transitioning from one to prevent API errors."""
    if query.message and query.message.photo:
        try:
            await query.delete_message()
        except Exception as e:
            logger.warning(f"Failed to delete photo message: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /start command."""
    import os
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")
    
    welcome_text = (
        "🚌 *Welcome to Engotta!*\n"
        "Your instant guide to the next available bus.\n\n"
        "Which bus can I catch right now?"
    )
    
    is_callback = update.callback_query is not None
    if is_callback:
        query = update.callback_query
        await query.answer()
        try:
            await query.delete_message()
        except Exception as e:
            logger.warning(f"Could not delete message in start_command: {e}")
            
    # Send message helper
    async def send_welcome():
        if BANNER_PATH:
            try:
                if BANNER_PATH.startswith("http://") or BANNER_PATH.startswith("https://"):
                    # URL banner
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=BANNER_PATH,
                        caption=welcome_text,
                        reply_markup=get_menu_keyboard(),
                        parse_mode="Markdown"
                    )
                    return
                elif os.path.exists(BANNER_PATH):
                    # Local file banner
                    with open(BANNER_PATH, 'rb') as photo_file:
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=photo_file,
                            caption=welcome_text,
                            reply_markup=get_menu_keyboard(),
                            parse_mode="Markdown"
                        )
                    return
            except Exception as e:
                logger.error(f"Failed to send banner photo: {e}. Falling back to text.")

        # Fallback to text
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_text,
            reply_markup=get_menu_keyboard(),
            parse_mode="Markdown"
        )
        
    await send_welcome()

async def destination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles selection of a specific destination stop."""
    query = update.callback_query
    await query.answer()
    
    # Parse destination ID and from_point if present
    # Format of query.data can be:
    # "dest_<id>"
    # "dest_<id>_from_<from_point>"
    data_parts = query.data.split("_")
    destination_id = int(data_parts[1])
    
    from_point = None
    if len(data_parts) >= 4 and data_parts[2] == "from":
        from_point = "_".join(data_parts[3:])
        
    dest_name = get_destination_by_id(destination_id)
    if not dest_name:
        await query.edit_message_text("Destination not found.", reply_markup=get_menu_keyboard())
        return
        
    # If destination is Njarakkadu and starting point is not selected yet, show submenu
    if dest_name == "Njarakkadu" and not from_point:
        from_points = get_distinct_from_points(destination_id)
        if not from_points:
            text = (
                f"📍 *{dest_name}*\n\n"
                "❌ No scheduled buses found for today."
            )
            keyboard = [[InlineKeyboardButton("🔙 Back to Stop Menu", callback_data="menu_back")]]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
            
        # Build sub list keyboard
        keyboard = []
        for fp in from_points:
            keyboard.append([
                InlineKeyboardButton(f"🚌 From {fp}", callback_data=f"dest_{destination_id}_from_{fp}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Back to Stop Menu", callback_data="menu_back")])
        
        text = (
            f"📍 *{dest_name}*\n\n"
            "Select the starting bus stand for buses towards Njarakkad:"
        )
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    now = get_local_now()
    current_time = now.strftime("%H:%M")
    day_type = get_day_type(now)
    
    # Fetch next buses (up to 4: 1 next bus + 3 upcoming)
    next_schedules = get_next_buses(destination_id, current_time, day_type, limit=4, from_point=from_point)
    
    display_title = dest_name
    if from_point:
        display_title += f" (From: {from_point})"

    if not next_schedules:
        text = (
            f"📍 *{display_title}*\n\n"
            "❌ No scheduled buses found for today."
        )
        # Back button
        if dest_name == "Njarakkadu":
            back_callback = f"dest_{destination_id}"
            back_text = "🔙 Back to Origin Menu"
        else:
            back_callback = "menu_back"
            back_text = "🔙 Back to Stop Menu"
            
        keyboard = [[InlineKeyboardButton(back_text, callback_data=back_callback)]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    next_bus = next_schedules[0]
    upcoming_buses = next_schedules[1:]
    
    # Calculate waiting time for the next bus
    wait_min = calculate_wait_time_minutes(current_time, next_bus["arrival_time"])
    wait_str = format_wait_time(wait_min)
    arrival_12h = format_24h_to_12h(next_bus["arrival_time"])
    
    if dest_name == "Njarakkadu":
        next_bus_str = f"{next_bus['bus_name']} ({next_bus['bus_type']})\n• *From:* {next_bus['from_point']}"
    else:
        next_bus_str = f"{next_bus['bus_name']} ({next_bus['bus_type']})"

    text = (
        f"📍 *{display_title}*\n\n"
        f"🚌 *Next Bus*\n"
        f"{next_bus_str}\n\n"
        f"🕒 *Arrival*\n"
        f"{arrival_12h}\n\n"
        f"⏳ *Waiting Time*\n"
        f"{wait_str}\n"
    )
    
    if upcoming_buses:
        text += "\n*Upcoming Buses*\n\n"
        for bus in upcoming_buses:
            bus_arr_12h = format_24h_to_12h(bus["arrival_time"])
            if dest_name == "Njarakkadu":
                text += f"{bus_arr_12h} - {bus['bus_name']} ({bus['bus_type']}) [From: {bus['from_point']}]\n"
            else:
                text += f"{bus_arr_12h} - {bus['bus_name']} ({bus['bus_type']})\n"
            
    # Keyboard with buttons to view details for each bus listed
    keyboard = []
    
    # Button for the next bus details
    keyboard.append([
        InlineKeyboardButton(
            f"ℹ️ Info: {next_bus['bus_name']} ({arrival_12h})", 
            callback_data=f"route_{next_bus['schedule_id']}"
        )
    ])
    
    # Buttons for upcoming buses details
    for bus in upcoming_buses:
        bus_arr_12h = format_24h_to_12h(bus["arrival_time"])
        keyboard.append([
            InlineKeyboardButton(
                f"ℹ️ Info: {bus['bus_name']} ({bus_arr_12h})", 
                callback_data=f"route_{bus['schedule_id']}"
            )
        ])
        
    # Back button
    if dest_name == "Njarakkadu":
        keyboard.append([InlineKeyboardButton("🔙 Back to Origin Menu", callback_data=f"dest_{destination_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🔙 Back to Stop Menu", callback_data="menu_back")])
    
    await update_menu_message(query, context, text, InlineKeyboardMarkup(keyboard))

async def available_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Available Now' feature showing next bus for every destination."""
    query = update.callback_query
    await query.answer()
    
    now = get_local_now()
    current_time = now.strftime("%H:%M")
    day_type = get_day_type(now)
    
    destinations = get_destinations()
    text = "🚌 *Available Now*\n\n"
    keyboard = []
    
    for dest in destinations:
        # Get next bus for this destination
        next_schedules = get_next_buses(dest["id"], current_time, day_type, limit=1)
        
        text += f"📍 *{dest['name']}*\n"
        if next_schedules:
            next_bus = next_schedules[0]
            arr_12h = format_24h_to_12h(next_bus["arrival_time"])
            if dest['name'] == "Njarakkadu":
                text += f"{next_bus['bus_name']} [From: {next_bus['from_point']}] - {arr_12h}\n\n"
            else:
                text += f"{next_bus['bus_name']} - {arr_12h}\n\n"
            
            # Button for details
            keyboard.append([
                InlineKeyboardButton(
                    f"ℹ️ {dest['name']}: {next_bus['bus_name']}", 
                    callback_data=f"route_{next_bus['schedule_id']}"
                )
            ])
        else:
            text += "No schedules today\n\n"
            
    keyboard.append([InlineKeyboardButton("🔙 Back to Stop Menu", callback_data="menu_back")])
    
    await update_menu_message(query, context, text, InlineKeyboardMarkup(keyboard))

async def route_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles displaying detailed bus route and timetable info."""
    query = update.callback_query
    await query.answer()
    
    # Parse schedule ID
    data_parts = query.data.split("_")
    schedule_id = int(data_parts[1])
    
    details = get_schedule_details(schedule_id)
    if not details:
        await update_menu_message(query, context, "Route details not found.", get_menu_keyboard())
        return
        
    arr_time = details["arrival_time"]
    duration = details["travel_duration"]
    exp_time = calculate_expected_arrival(arr_time, duration)
    
    arr_12h = format_24h_to_12h(arr_time)
    exp_12h = format_24h_to_12h(exp_time)
    
    text = (
        f"🚌 *Bus Details*\n\n"
        f"• *Bus Name:* {details['bus_name']}\n"
        f"• *Bus Type:* {details['bus_type']}\n"
        f"• *From:* {details['from_point']}\n"
        f"• *Destination:* {details['destination_name']}\n"
        f"• *Arrival at Stop:* {arr_12h}\n"
        f"• *Journey Duration:* {duration} minutes\n"
        f"• *Expected Arrival:* {exp_12h}\n"
    )
    
    # Back button to destination list or main menu
    if details['destination_name'] == "Njarakkadu":
        back_callback = f"dest_{details['destination_id']}_from_{details['from_point']}"
        back_label = f"🔙 Back to {details['destination_name']} ({details['from_point']})"
    else:
        back_callback = f"dest_{details['destination_id']}"
        back_label = f"🔙 Back to {details['destination_name']}"
        
    keyboard = [
        [
            InlineKeyboardButton(back_label, callback_data=back_callback)
        ],
        [InlineKeyboardButton("🔙 Back to Stop Menu", callback_data="menu_back")]
    ]
    
    await update_menu_message(query, context, text, InlineKeyboardMarkup(keyboard))
