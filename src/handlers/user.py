import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.db import (
    get_destinations, get_destination_by_id, get_next_buses, 
    get_schedule_details, is_date_holiday, get_distinct_from_points,
    get_schedules_for_day, get_schedules_by_bus_name_search
)
from src.utils.time_helper import (
    get_local_now, get_current_time_24h, format_24h_to_12h, 
    calculate_wait_time_minutes, format_wait_time, calculate_expected_arrival,
    time_to_minutes, parse_user_time
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
    """Helper to construct the main start menu inline keyboard dynamically in 2 columns using native Telegram button styles."""
    destinations = get_destinations()
    keyboard = []
    
    # Destinations: 2 columns, red (danger)
    dest_buttons = [
        InlineKeyboardButton(dest['name'], callback_data=f"dest_{dest['id']}", api_kwargs={"style": "danger"})
        for dest in destinations
    ]
    for i in range(0, len(dest_buttons), 2):
        keyboard.append(dest_buttons[i:i+2])
        
    # Feature buttons: green (success)
    keyboard.append([
        InlineKeyboardButton("Reach by Time", callback_data="reach_by_time", api_kwargs={"style": "success"}),
        InlineKeyboardButton("Available Now", callback_data="available_now", api_kwargs={"style": "success"})
    ])
    keyboard.append([
        InlineKeyboardButton("🔍 Search Bus by Name", callback_data="search_bus", api_kwargs={"style": "success"}),
        InlineKeyboardButton("Veyil App", url="https://veyil.app")
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
        await update_menu_message(query, context, "Destination not found.", get_menu_keyboard())
        return
        
    # If destination is Njarakkadu and starting point is not selected yet, show submenu
    if dest_name == "Njarakkadu" and not from_point:
        from_points = get_distinct_from_points(destination_id)
        if not from_points:
            text = (
                f"📍 *{dest_name}*\n\n"
                "❌ No scheduled buses found for today."
            )
            keyboard = [[InlineKeyboardButton("Back to Menu", callback_data="menu_back", api_kwargs={"style": "primary"})]]
            await update_menu_message(query, context, text, InlineKeyboardMarkup(keyboard))
            return
            
        # Build sub list keyboard (2 columns with red buttons)
        from_buttons = [
            InlineKeyboardButton(f"From {fp}", callback_data=f"dest_{destination_id}_from_{fp}", api_kwargs={"style": "danger"})
            for fp in from_points
        ]
        keyboard = []
        for i in range(0, len(from_buttons), 2):
            keyboard.append(from_buttons[i:i+2])
        keyboard.append([InlineKeyboardButton("Back to Stop Menu", callback_data="menu_back", api_kwargs={"style": "primary"})])
        
        text = (
            f"📍 *{dest_name}*\n\n"
            "Select the starting bus stand for buses towards Njarakkad:"
        )
        await update_menu_message(query, context, text, InlineKeyboardMarkup(keyboard))
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
            
        keyboard = [[InlineKeyboardButton("Back to Menu", callback_data=back_callback, api_kwargs={"style": "primary"})]]
        await update_menu_message(query, context, text, InlineKeyboardMarkup(keyboard))
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
            f"Info: {next_bus['bus_name']} ({arrival_12h})",
            callback_data=f"route_{next_bus['schedule_id']}",
            api_kwargs={"style": "success"}
        )
    ])
    
    # Buttons for upcoming buses details
    for bus in upcoming_buses:
        bus_arr_12h = format_24h_to_12h(bus["arrival_time"])
        keyboard.append([
            InlineKeyboardButton(
                f"Info: {bus['bus_name']} ({bus_arr_12h})",
                callback_data=f"route_{bus['schedule_id']}",
                api_kwargs={"style": "success"}
            )
        ])
        
    # Back button
    if dest_name == "Njarakkadu":
        keyboard.append([InlineKeyboardButton("Back to Origin Menu", callback_data=f"dest_{destination_id}", api_kwargs={"style": "primary"})])
    else:
        keyboard.append([InlineKeyboardButton("Back to Stop Menu", callback_data="menu_back", api_kwargs={"style": "primary"})])
    
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
                    f"Info: {dest['name']}: {next_bus['bus_name']}",
                    callback_data=f"route_{next_bus['schedule_id']}",
                    api_kwargs={"style": "success"}
                )
            ])
        else:
            text += "No schedules today\n\n"
            
    keyboard.append([InlineKeyboardButton("Back to Menu", callback_data="menu_back", api_kwargs={"style": "primary"})])
    
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
            InlineKeyboardButton(f"Back to {back_label.replace('🔙 Back to ', '')}", callback_data=back_callback, api_kwargs={"style": "primary"})
        ],
        [InlineKeyboardButton("Back to Menu", callback_data="menu_back", api_kwargs={"style": "primary"})]
    ]
    
    await update_menu_message(query, context, text, InlineKeyboardMarkup(keyboard))

# --- Reach Destination by Time Conversation States ---
REACH_CHOOSE_DEST, REACH_CHOOSE_FROM, REACH_ENTER_TIME = range(3)

async def reach_by_time_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the 'Reach by Time' search conversation by prompting destination."""
    is_callback = update.callback_query is not None
    if is_callback:
        query = update.callback_query
        await query.answer()
        # Delete or edit. If it has a photo, start_command deletes it. We can delete it here to avoid photo conflicts.
        if query.message and query.message.photo:
            try:
                await query.delete_message()
            except Exception as e:
                logger.warning(f"Could not delete message in reach_by_time_start: {e}")
            message_sender = context.bot.send_message
            target_chat_id = query.message.chat_id
        else:
            message_sender = query.edit_message_text
            target_chat_id = None
    else:
        message_sender = update.message.reply_text
        target_chat_id = None

    context.user_data.clear()
    destinations = get_destinations()
    keyboard = []
    dest_buttons = [
        InlineKeyboardButton(d['name'], callback_data=f"reach_dest_{d['id']}", api_kwargs={"style": "danger"})
        for d in destinations
    ]
    for i in range(0, len(dest_buttons), 2):
        keyboard.append(dest_buttons[i:i+2])
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="reach_cancel", api_kwargs={"style": "primary"})])
    
    text = "⏱ *Reach Destination by Time*\n\nSelect your destination stop:"
    
    if target_chat_id:
        await message_sender(
            chat_id=target_chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await message_sender(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    return REACH_CHOOSE_DEST

async def reach_choose_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves chosen destination. If Njarakkadu, prompts for starting point. Otherwise, prompts for target reach time."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "reach_cancel":
        return await reach_cancel(update, context)
        
    dest_id = int(query.data.split("_")[2])
    dest_name = get_destination_by_id(dest_id)
    if not dest_name:
        await start_command(update, context)
        return ConversationHandler.END
        
    context.user_data["reach_dest_id"] = dest_id
    context.user_data["reach_dest_name"] = dest_name
    
    if dest_name == "Njarakkadu":
        from_points = get_distinct_from_points(dest_id)
        if not from_points:
            text = (
                f"📍 *{dest_name}*\n\n"
                "❌ No starting points found for this stop."
            )
            keyboard = [[InlineKeyboardButton("Cancel", callback_data="reach_cancel", api_kwargs={"style": "primary"})]]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
            context.user_data.clear()
            return ConversationHandler.END
            
        from_buttons = [
            InlineKeyboardButton(f"From {fp}", callback_data=f"reach_from_{dest_id}_{fp}", api_kwargs={"style": "danger"})
            for fp in from_points
        ]
        keyboard = []
        for i in range(0, len(from_buttons), 2):
            keyboard.append(from_buttons[i:i+2])
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="reach_cancel", api_kwargs={"style": "primary"})])
        
        text = (
            f"📍 *{dest_name}*\n\n"
            "Select the starting bus stand for buses towards Njarakkad:"
        )
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
        return REACH_CHOOSE_FROM
    else:
        text = (
            f"📍 Destination: *{dest_name}*\n\n"
            "💬 Enter the time by which you need to reach (e.g. *10:30 AM* or *15:00*):"
        )
        keyboard = [[InlineKeyboardButton("Cancel", callback_data="reach_cancel", api_kwargs={"style": "primary"})]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return REACH_ENTER_TIME

async def reach_choose_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves chosen origin point for Njarakkadu and prompts for target reach time."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "reach_cancel":
        return await reach_cancel(update, context)
        
    parts = query.data.split("_")
    # Format: reach_from_<dest_id>_<origin_point>
    dest_id = int(parts[2])
    from_point = "_".join(parts[3:])
    
    context.user_data["reach_dest_id"] = dest_id
    context.user_data["reach_from_point"] = from_point
    dest_name = context.user_data.get("reach_dest_name") or "Njarakkadu"
    
    text = (
        f"📍 Destination: *{dest_name}* (From: *{from_point}*)\n\n"
        "💬 Enter the time by which you need to reach (e.g. *10:30 AM* or *15:00*):"
    )
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="reach_cancel", api_kwargs={"style": "primary"})]]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return REACH_ENTER_TIME

async def reach_enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validates target time, queries schedules, filters and sorts by reachability, and returns the result."""
    text = update.message.text.strip()
    
    target_time_24h = parse_user_time(text)
    if not target_time_24h:
        keyboard = [[InlineKeyboardButton("Cancel", callback_data="reach_cancel", api_kwargs={"style": "primary"})]]
        await update.message.reply_text(
            "❌ *Invalid time format.*\n\nPlease enter the time in formats like *10:30 AM*, *14:15*, or *3:00 PM*:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return REACH_ENTER_TIME

    dest_id = context.user_data["reach_dest_id"]
    dest_name = context.user_data["reach_dest_name"]
    from_point = context.user_data.get("reach_from_point")

    now = get_local_now()
    current_time = now.strftime("%H:%M")
    current_mins = time_to_minutes(current_time)
    
    target_mins = time_to_minutes(target_time_24h)
    if target_time_24h < current_time:
        target_mins += 24 * 60

    today_day_type = get_day_type(now)
    tomorrow = now + datetime.timedelta(days=1)
    tomorrow_day_type = get_day_type(tomorrow)

    matching_buses = []

    # Check if target time spans midnight
    if target_time_24h >= current_time:
        # Same-day search
        today_schedules = get_schedules_for_day(dest_id, today_day_type, from_point)
        for s in today_schedules:
            boarding_time = s["arrival_time"]
            if boarding_time >= current_time:
                boarding_mins = time_to_minutes(boarding_time)
                expected_arrival_mins = boarding_mins + s["travel_duration"]
                if expected_arrival_mins <= target_mins:
                    expected_arrival_time = calculate_expected_arrival(boarding_time, s["travel_duration"])
                    wait_minutes = boarding_mins - current_mins
                    reach_diff = target_mins - expected_arrival_mins
                    
                    matching_buses.append({
                        **s,
                        "expected_arrival": expected_arrival_time,
                        "wait_minutes": wait_minutes,
                        "reach_diff": reach_diff,
                        "is_tomorrow": False
                    })
    else:
        # Spans midnight (target is tomorrow morning/afternoon)
        # 1. Today's schedules departing after now
        today_schedules = get_schedules_for_day(dest_id, today_day_type, from_point)
        for s in today_schedules:
            boarding_time = s["arrival_time"]
            if boarding_time >= current_time:
                boarding_mins = time_to_minutes(boarding_time)
                expected_arrival_mins = boarding_mins + s["travel_duration"]
                if expected_arrival_mins <= target_mins:
                    expected_arrival_time = calculate_expected_arrival(boarding_time, s["travel_duration"])
                    wait_minutes = boarding_mins - current_mins
                    reach_diff = target_mins - expected_arrival_mins
                    
                    matching_buses.append({
                        **s,
                        "expected_arrival": expected_arrival_time,
                        "wait_minutes": wait_minutes,
                        "reach_diff": reach_diff,
                        "is_tomorrow": False
                    })
                
        # 2. Tomorrow's schedules departing and arriving before target_time
        tomorrow_schedules = get_schedules_for_day(dest_id, tomorrow_day_type, from_point)
        for s in tomorrow_schedules:
            boarding_time = s["arrival_time"]
            boarding_mins = time_to_minutes(boarding_time) + 24 * 60
            expected_arrival_mins = boarding_mins + s["travel_duration"]
            if expected_arrival_mins <= target_mins:
                expected_arrival_time = calculate_expected_arrival(boarding_time, s["travel_duration"])
                wait_minutes = boarding_mins - current_mins
                reach_diff = target_mins - expected_arrival_mins
                
                matching_buses.append({
                    **s,
                    "expected_arrival": expected_arrival_time,
                    "wait_minutes": wait_minutes,
                    "reach_diff": reach_diff,
                    "is_tomorrow": True
                })

    # Sort matching buses by reach difference ascending (nearest to target arrival time first)
    # Secondary key: wait minutes descending (later boarding time is preferred if arrival is identical)
    matching_buses.sort(key=lambda x: (x["reach_diff"], -x["wait_minutes"]))

    target_time_12h = format_24h_to_12h(target_time_24h)
    day_str = "today" if target_time_24h >= current_time else "tomorrow"
    display_dest = dest_name
    if from_point:
        display_dest += f" (From: {from_point})"

    keyboard = []

    if not matching_buses:
        text_out = (
            f"⏱ *Reach {display_dest} by {target_time_12h} {day_str}*\n\n"
            f"❌ No scheduled buses found that can be boarded after now and reach by this time."
        )
    else:
        text_out = f"⏱ *Buses reaching {display_dest} by {target_time_12h} {day_str}:*\n\n"
        # List top 8 buses to avoid message limit issues
        for bus in matching_buses[:8]:
            boarding_12h = format_24h_to_12h(bus["arrival_time"])
            reach_12h = format_24h_to_12h(bus["expected_arrival"])
            wait_str = format_wait_time(bus["wait_minutes"])
            day_suffix = " (Tomorrow)" if bus["is_tomorrow"] else ""
            
            if dest_name == "Njarakkadu":
                bus_detail = f"🚌 *{bus['bus_name']}* ({bus['bus_type']}) [From: {bus['from_point']}]"
            else:
                bus_detail = f"🚌 *{bus['bus_name']}* ({bus['bus_type']})"
                
            text_out += (
                f"{bus_detail}\n"
                f"• *Board:* {boarding_12h}{day_suffix} (in {wait_str})\n"
                f"• *Reach:* {reach_12h}\n"
                f"• *Journey:* {bus['travel_duration']} mins\n\n"
            )
            
            keyboard.append([
                InlineKeyboardButton(
                    f"ℹ️ Info: {bus['bus_name']} ({boarding_12h})", 
                    callback_data=f"route_{bus['schedule_id']}"
                )
            ])

    keyboard.append([
        InlineKeyboardButton("Search Again", callback_data="reach_by_time", api_kwargs={"style": "success"}),
        InlineKeyboardButton("Back to Menu", callback_data="menu_back", api_kwargs={"style": "primary"})
    ])

    await update.message.reply_text(
        text=text_out,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    context.user_data.clear()
    return ConversationHandler.END

async def reach_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels search and returns to the main menu."""
    query = update.callback_query
    if query:
        await query.answer()
        await start_command(update, context)
    else:
        await update.message.reply_text("⏹️ Search cancelled. Type /start to open the menu.")
    context.user_data.clear()
    return ConversationHandler.END


# --- Search Bus by Name Conversation ---
SEARCH_BUS_ENTER_NAME = 10

async def search_bus_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Triggered by 'Search Bus by Name' button. Prompts user to type a bus name."""
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="search_bus_cancel", api_kwargs={"style": "primary"})]]
    await query.edit_message_text(
        text="🔍 *Search Bus by Name*\n\nType the bus name (or part of it):\n\n_I'll show all upcoming trips for today._",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SEARCH_BUS_ENTER_NAME

async def search_bus_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the user's bus name input and shows matching schedules."""
    bus_name = update.message.text.strip()
    now = get_local_now()
    current_time = now.strftime("%H:%M")
    day_type = get_day_type(now)

    results = get_schedules_by_bus_name_search(bus_name, day_type, current_time)

    keyboard = [[InlineKeyboardButton("🔍 Search Again", callback_data="search_bus", api_kwargs={"style": "success"}),
                 InlineKeyboardButton("Back to Menu", callback_data="menu_back", api_kwargs={"style": "primary"})]]

    if not results:
        await update.message.reply_text(
            f"🔍 No upcoming buses matching *\"{bus_name}\"* found for today.\n\n"
            "Try a different name or check back later.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return SEARCH_BUS_ENTER_NAME

    text = f"🔍 *Results for \"{bus_name}\":*\n\n"
    for idx, s in enumerate(results[:8], 1):
        arr_12h = format_24h_to_12h(s["arrival_time"])
        wait_m = calculate_wait_time_minutes(current_time, s["arrival_time"])
        wait_str = format_wait_time(wait_m)
        from_str = f" [From: {s['from_point']}]" if s.get("from_point") and s["from_point"] != "Njarakkadu" else ""
        text += (
            f"{idx}. *{s['bus_name']}* ({s['bus_type']}){from_str}\n"
            f"   ➜ {s['destination_name']} | {arr_12h} (in {wait_str})\n\n"
        )

    await update.message.reply_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SEARCH_BUS_ENTER_NAME

async def search_bus_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the search and returns to main menu."""
    query = update.callback_query
    if query:
        await query.answer()
        await start_command(update, context)
    else:
        await update.message.reply_text("Search cancelled.")
    return ConversationHandler.END
