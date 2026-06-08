import re
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, 
    MessageHandler, CallbackQueryHandler, filters
)
from src.config import ADMIN_IDS, logger
from src.db import (
    get_destinations, get_destination_by_id, get_schedules_by_destination,
    add_bus, add_schedule, get_schedule_details, update_schedule, delete_schedule,
    add_holiday, delete_holiday, get_all_holidays
)

# --- Conversation States ---

# Add Bus states
ADD_CHOOSE_DEST, ADD_ENTER_NAME, ADD_CHOOSE_TYPE, ADD_ENTER_TIME, ADD_ENTER_DURATION, ADD_ENTER_FROM, ADD_CHOOSE_DAYTYPE = range(7)

# Edit Bus states
EDIT_CHOOSE_DEST, EDIT_SELECT_SCHED, EDIT_CHOOSE_FIELD, EDIT_ENTER_TIME, EDIT_ENTER_DURATION, EDIT_ENTER_FROM, EDIT_CHOOSE_DAYTYPE, EDIT_ENTER_BUSNAME, EDIT_CHOOSE_BUSTYPE = range(7, 16)

# Delete Bus states
DEL_CHOOSE_DEST, DEL_SELECT_SCHED, DEL_CONFIRM = range(16, 19)


# --- Authorization Helper ---

def is_admin(user_id: int) -> bool:
    """Checks if the user's Telegram ID is configured as an administrator."""
    # If ADMIN_IDS is empty, allow for local testing convenience but log warning
    if not ADMIN_IDS:
        logger.warning("No ADMIN_IDS configured in environment. All admin commands will be rejected.")
        return False
    return user_id in ADMIN_IDS

async def check_admin_permission(update: Update) -> bool:
    """Verifies user permission and sends unauthorized alert message if necessary."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        logger.warning(f"Unauthorized admin attempt by user {user_id} ({update.effective_user.username})")
        msg = "❌ *Unauthorized Access*\n\nThis command is restricted to administrators."
        if update.message:
            await update.message.reply_text(msg, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.answer("Unauthorized", show_alert=True)
        return False
    return True


# --- Common Cancel Handler ---

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends any active conversation handler."""
    msg = "⏹️ Operation cancelled."
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=msg)
    elif update.message:
        await update.message.reply_text(text=msg)
        
    context.user_data.clear()
    return ConversationHandler.END


# --- List Schedules Command ---

async def list_schedules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all registered schedules grouped by destination."""
    if not await check_admin_permission(update):
        return

    destinations = get_destinations()
    if not destinations:
        await update.message.reply_text("No destinations registered in the database.")
        return

    await update.message.reply_text("📋 *Fetching Timetable Schedules...*", parse_mode="Markdown")
    
    for dest in destinations:
        schedules = get_schedules_by_destination(dest["id"])
        
        text = f"📍 *{dest['name']}* (Stop ID: {dest['id']})\n"
        if not schedules:
            text += "  _No schedules registered_\n"
            await update.message.reply_text(text, parse_mode="Markdown")
            continue
            
        text += "━" * 15 + "\n"
        for s in schedules:
            text += (
                f"• *ID:* `{s['schedule_id']}` | *{s['arrival_time']}* | "
                f"{s['bus_name']} ({s['bus_type']})\n"
                f"  _Duration:_ {s['travel_duration']}m | _Days:_ `{s['day_type']}`\n\n"
            )
            
        # Send separate messages per destination to prevent reaching character limit
        # Split into smaller parts if needed, but for standard seed data it fits well
        await update.message.reply_text(text, parse_mode="Markdown")


# --- Add Schedule Conversation (/addbus) ---

async def addbus_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the /addbus wizard by prompting destination."""
    if not await check_admin_permission(update):
        return ConversationHandler.END

    destinations = get_destinations()
    keyboard = []
    for d in destinations:
        keyboard.append([InlineKeyboardButton(d["name"], callback_data=f"add_dest_{d['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="add_cancel")])
    
    await update.message.reply_text(
        text="➕ *Add Timetable Entry* (Step 1/6)\n\nSelect the destination:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ADD_CHOOSE_DEST

async def addbus_choose_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves selected destination and asks for Bus Name."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_cancel":
        return await cancel(update, context)
        
    dest_id = int(query.data.split("_")[2])
    context.user_data["add_dest_id"] = dest_id
    dest_name = get_destination_by_id(dest_id)
    context.user_data["add_dest_name"] = dest_name
    
    await query.edit_message_text(
        text=f"📍 Destination: *{dest_name}*\n\n💬 *Step 2/6*: Type the name of the Bus (e.g. Meeras):",
        parse_mode="Markdown"
    )
    return ADD_ENTER_NAME

async def addbus_enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves bus name and asks for Bus Type."""
    bus_name = update.message.text.strip()
    if not bus_name:
        await update.message.reply_text("Bus name cannot be empty. Please type the bus name:")
        return ADD_ENTER_NAME
        
    context.user_data["add_bus_name"] = bus_name
    
    keyboard = [
        [
            InlineKeyboardButton("Private", callback_data="add_type_Private"),
            InlineKeyboardButton("KSRTC", callback_data="add_type_KSRTC")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="add_cancel")]
    ]
    
    await update.message.reply_text(
        text=f"🚌 Bus Name: *{bus_name}*\n\n💬 *Step 3/6*: Select the Bus Type:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ADD_CHOOSE_TYPE

async def addbus_choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves bus type and prompts for Arrival Time."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_cancel":
        return await cancel(update, context)
        
    bus_type = query.data.split("_")[2]
    context.user_data["add_bus_type"] = bus_type
    
    await query.edit_message_text(
        text=(
            f"🚌 Bus: *{context.user_data['add_bus_name']}* ({bus_type})\n\n"
            f"💬 *Step 4/6*: Enter the *Arrival Time* at stop (in 24-hour HH:MM format, e.g. 15:30):"
        ),
        parse_mode="Markdown"
    )
    return ADD_ENTER_TIME

async def addbus_enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validates and saves arrival time, then prompts for travel duration."""
    time_text = update.message.text.strip()
    
    # Simple regex for HH:MM 24-hour validation
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", time_text):
        await update.message.reply_text(
            "❌ Invalid time format. Please enter arrival time in 24-hour HH:MM format (e.g. 08:15 or 16:45):"
        )
        return ADD_ENTER_TIME
        
    context.user_data["add_arr_time"] = time_text
    
    await update.message.reply_text(
        text=f"🕒 Arrival Time: *{time_text}*\n\n💬 *Step 5/6*: Enter the *Journey Duration* in minutes (e.g. 45):",
        parse_mode="Markdown"
    )
    return ADD_ENTER_DURATION

async def addbus_enter_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validates and saves journey duration, then prompts for origin point (if Njarakkadu) or schedule day type."""
    duration_text = update.message.text.strip()
    if not duration_text.isdigit() or int(duration_text) <= 0:
        await update.message.reply_text("❌ Please enter a valid positive integer for minutes:")
        return ADD_ENTER_DURATION
        
    context.user_data["add_duration"] = int(duration_text)
    dest_name = context.user_data.get("add_dest_name")
    
    if dest_name == "Njarakkadu":
        await update.message.reply_text(
            text=f"⏳ Duration: *{duration_text} minutes*\n\n💬 *Step 6/7*: Enter the *Origin Point* (starting bus stand, e.g. Muvattupuzha, Thodupuzha):",
            parse_mode="Markdown"
        )
        return ADD_ENTER_FROM
    else:
        # Default starting point to Njarakkadu for other destinations
        context.user_data["add_from_point"] = "Njarakkadu"
        
        keyboard = [
            [
                InlineKeyboardButton("Daily", callback_data="add_day_daily"),
                InlineKeyboardButton("Weekday", callback_data="add_day_weekday")
            ],
            [
                InlineKeyboardButton("Sunday Only", callback_data="add_day_sunday"),
                InlineKeyboardButton("Holiday Only", callback_data="add_day_holiday")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="add_cancel")]
        ]
        
        await update.message.reply_text(
            text=f"⏳ Duration: *{duration_text} minutes*\n\n💬 *Step 6/6*: Select active days for this schedule:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return ADD_CHOOSE_DAYTYPE

async def addbus_enter_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the origin point and prompts for schedule day type."""
    from_pt = update.message.text.strip()
    if not from_pt:
        await update.message.reply_text("Origin point cannot be empty. Please enter the starting bus stand:")
        return ADD_ENTER_FROM
        
    context.user_data["add_from_point"] = from_pt
    
    keyboard = [
        [
            InlineKeyboardButton("Daily", callback_data="add_day_daily"),
            InlineKeyboardButton("Weekday", callback_data="add_day_weekday")
        ],
        [
            InlineKeyboardButton("Sunday Only", callback_data="add_day_sunday"),
            InlineKeyboardButton("Holiday Only", callback_data="add_day_holiday")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="add_cancel")]
    ]
    
    await update.message.reply_text(
        text=f"📍 From: *{from_pt}*\n\n💬 *Step 7/7*: Select active days for this schedule:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ADD_CHOOSE_DAYTYPE

async def addbus_choose_daytype(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves schedule day type, writes schedule to database, and completes conversation."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_cancel":
        return await cancel(update, context)
        
    day_type = query.data.split("_")[2]
    
    dest_id = context.user_data["add_dest_id"]
    dest_name = context.user_data["add_dest_name"]
    bus_name = context.user_data["add_bus_name"]
    bus_type = context.user_data["add_bus_type"]
    arr_time = context.user_data["add_arr_time"]
    duration = context.user_data["add_duration"]
    from_point = context.user_data.get("add_from_point", "Njarakkadu")
    
    try:
        # Write to SQLite
        bus_id = add_bus(bus_name, bus_type)
        add_schedule(dest_id, bus_id, arr_time, duration, day_type, from_point)
        
        success_msg = (
            "✅ *Schedule Added Successfully!*\n\n"
            f"• *Destination:* {dest_name}\n"
            f"• *Bus Name:* {bus_name} ({bus_type})\n"
            f"• *From:* {from_point}\n"
            f"• *Arrival Time:* {arr_time}\n"
            f"• *Duration:* {duration} minutes\n"
            f"• *Active Schedule:* {day_type}\n"
        )
        await query.edit_message_text(text=success_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error adding schedule: {e}")
        await query.edit_message_text(text=f"❌ Error adding schedule to database:\n`{e}`", parse_mode="Markdown")
        
    context.user_data.clear()
    return ConversationHandler.END


# --- Edit Schedule Conversation (/editbus) ---

async def editbus_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts /editbus wizard by listing destinations."""
    if not await check_admin_permission(update):
        return ConversationHandler.END

    destinations = get_destinations()
    keyboard = []
    for d in destinations:
        keyboard.append([InlineKeyboardButton(d["name"], callback_data=f"edit_dest_{d['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")])
    
    await update.message.reply_text(
        text="✏️ *Edit Timetable Entry*\n\nSelect the destination stop:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return EDIT_CHOOSE_DEST

async def editbus_choose_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lists schedules for editing at the selected destination."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancel":
        return await cancel(update, context)
        
    dest_id = int(query.data.split("_")[2])
    dest_name = get_destination_by_id(dest_id)
    
    schedules = get_schedules_by_destination(dest_id)
    if not schedules:
        await query.edit_message_text(f"No schedules registered for destination {dest_name}.")
        context.user_data.clear()
        return ConversationHandler.END
        
    keyboard = []
    for s in schedules:
        label = f"[{s['arrival_time']}] {s['bus_name']}"
        if dest_name == "Njarakkadu":
            label += f" (From: {s['from_point']})"
        label += f" ({s['day_type']})"
        keyboard.append([
            InlineKeyboardButton(
                label, 
                callback_data=f"edit_sched_{s['schedule_id']}"
            )
        ])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")])
    
    await query.edit_message_text(
        text=f"📍 Destination: *{dest_name}*\n\nSelect the schedule to edit:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return EDIT_SELECT_SCHED

async def editbus_select_sched(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays field options for the selected schedule."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancel":
        return await cancel(update, context)
        
    sched_id = int(query.data.split("_")[2])
    context.user_data["edit_sched_id"] = sched_id
    
    details = get_schedule_details(sched_id)
    if not details:
        await query.edit_message_text("Schedule not found.")
        context.user_data.clear()
        return ConversationHandler.END
        
    context.user_data["edit_details"] = details
    
    keyboard = [
        [
            InlineKeyboardButton(f"🚌 Bus Name ({details['bus_name']})", callback_data="edit_field_busname"),
        ],
        [
            InlineKeyboardButton(f"🕒 Arrival Time ({details['arrival_time']})", callback_data="edit_field_time"),
        ],
        [
            InlineKeyboardButton(f"⏳ Duration ({details['travel_duration']} mins)", callback_data="edit_field_duration"),
        ],
        [
            InlineKeyboardButton(f"📅 Day Type ({details['day_type']})", callback_data="edit_field_daytype"),
        ]
    ]
    if details["destination_name"] == "Njarakkadu":
        keyboard.append([
            InlineKeyboardButton(f"📍 From Point ({details['from_point']})", callback_data="edit_field_frompoint")
        ])
        
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")])
    
    text = (
        f"✏️ *Editing Bus:* {details['bus_name']} ({details['bus_type']})\n"
        f"📍 *Destination:* {details['destination_name']}\n\n"
        "Select the field you want to edit:"
    )
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return EDIT_CHOOSE_FIELD

async def editbus_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Directs to sub-handler based on the selected field to update."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancel":
        return await cancel(update, context)
        
    field = query.data.split("_")[2]
    context.user_data["edit_field"] = field
    
    details = context.user_data["edit_details"]
    
    if field == "busname":
        await query.edit_message_text(
            text=f"🚌 Current Bus Name: *{details['bus_name']}*\n\n💬 Type the *new Bus Name*:",
            parse_mode="Markdown"
        )
        return EDIT_ENTER_BUSNAME
    elif field == "time":
        await query.edit_message_text(
            text=f"🕒 Current Arrival Time: *{details['arrival_time']}*\n\n💬 Type the *new Arrival Time* (24-hour HH:MM format):",
            parse_mode="Markdown"
        )
        return EDIT_ENTER_TIME
    elif field == "duration":
        await query.edit_message_text(
            text=f"⏳ Current Journey Duration: *{details['travel_duration']} minutes*\n\n💬 Type the *new Duration* (in minutes):",
            parse_mode="Markdown"
        )
        return EDIT_ENTER_DURATION
    elif field == "daytype":
        keyboard = [
            [
                InlineKeyboardButton("Daily", callback_data="edit_day_daily"),
                InlineKeyboardButton("Weekday", callback_data="edit_day_weekday")
            ],
            [
                InlineKeyboardButton("Sunday Only", callback_data="edit_day_sunday"),
                InlineKeyboardButton("Holiday Only", callback_data="edit_day_holiday")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")]
        ]
        await query.edit_message_text(
            text=f"📅 Current Day Type: *{details['day_type']}*\n\nSelect the *new Day Type*:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return EDIT_CHOOSE_DAYTYPE
    elif field == "frompoint":
        await query.edit_message_text(
            text=f"📍 Current Origin Point: *{details['from_point']}*\n\n💬 Type the *new Origin Point* (e.g. Muvattupuzha):",
            parse_mode="Markdown"
        )
        return EDIT_ENTER_FROM
        
    return ConversationHandler.END

async def editbus_enter_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves new time and commits update to database."""
    time_text = update.message.text.strip()
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", time_text):
        await update.message.reply_text(
            "❌ Invalid time format. Please enter arrival time in 24-hour HH:MM format (e.g. 15:30):"
        )
        return EDIT_ENTER_TIME
        
    sched_id = context.user_data["edit_sched_id"]
    details = context.user_data["edit_details"]
    
    update_schedule(sched_id, time_text, details["travel_duration"], details["day_type"], details["from_point"])
    
    await update.message.reply_text(f"✅ Schedule ID `{sched_id}` updated. Arrival time set to *{time_text}*.", parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def editbus_enter_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves new duration and commits update to database."""
    duration_text = update.message.text.strip()
    if not duration_text.isdigit() or int(duration_text) <= 0:
        await update.message.reply_text("❌ Please enter a valid positive integer for minutes:")
        return EDIT_ENTER_DURATION
        
    sched_id = context.user_data["edit_sched_id"]
    details = context.user_data["edit_details"]
    
    duration = int(duration_text)
    update_schedule(sched_id, details["arrival_time"], duration, details["day_type"], details["from_point"])
    
    await update.message.reply_text(f"✅ Schedule ID `{sched_id}` updated. Duration set to *{duration} minutes*.", parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def editbus_choose_daytype(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves new day type and commits update to database."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancel":
        return await cancel(update, context)
        
    day_type = query.data.split("_")[2]
    sched_id = context.user_data["edit_sched_id"]
    details = context.user_data["edit_details"]
    
    update_schedule(sched_id, details["arrival_time"], details["travel_duration"], day_type, details["from_point"])
    
    await query.edit_message_text(f"✅ Schedule ID `{sched_id}` updated. Day type set to *{day_type}*.", parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def editbus_enter_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves new origin point and commits update to database."""
    from_pt = update.message.text.strip()
    if not from_pt:
        await update.message.reply_text("Origin point cannot be empty. Please enter the starting bus stand:")
        return EDIT_ENTER_FROM
        
    sched_id = context.user_data["edit_sched_id"]
    details = context.user_data["edit_details"]
    
    update_schedule(sched_id, details["arrival_time"], details["travel_duration"], details["day_type"], from_pt)
    
    await update.message.reply_text(f"✅ Schedule ID `{sched_id}` updated. Origin point set to *{from_pt}*.", parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END

async def editbus_enter_busname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the new bus name and asks for Bus Type."""
    bus_name = update.message.text.strip()
    if not bus_name:
        await update.message.reply_text("Bus name cannot be empty. Please type the bus name:")
        return EDIT_ENTER_BUSNAME
        
    context.user_data["edit_bus_name"] = bus_name
    
    keyboard = [
        [
            InlineKeyboardButton("Private", callback_data="edit_type_Private"),
            InlineKeyboardButton("KSRTC", callback_data="edit_type_KSRTC")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")]
    ]
    
    await update.message.reply_text(
        text=f"🚌 New Bus Name: *{bus_name}*\n\n💬 Select the Bus Type:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return EDIT_CHOOSE_BUSTYPE

async def editbus_choose_bustype(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves bus type, updates the bus ID of the schedule, and commits update to database."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edit_cancel":
        return await cancel(update, context)
        
    bus_type = query.data.split("_")[2]
    sched_id = context.user_data["edit_sched_id"]
    details = context.user_data["edit_details"]
    bus_name = context.user_data["edit_bus_name"]
    
    try:
        # Get or create new bus ID
        bus_id = add_bus(bus_name, bus_type)
        
        # Update schedule with the new bus ID
        update_schedule(sched_id, details["arrival_time"], details["travel_duration"], details["day_type"], details["from_point"], bus_id=bus_id)
        
        success_msg = (
            f"✅ Schedule ID `{sched_id}` updated.\n\n"
            f"• *New Bus Name:* {bus_name} ({bus_type})\n"
        )
        await query.edit_message_text(text=success_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error updating bus name for schedule: {e}")
        await query.edit_message_text(text=f"❌ Error updating bus name:\n`{e}`", parse_mode="Markdown")
        
    context.user_data.clear()
    return ConversationHandler.END



# --- Delete Schedule Conversation (/deletebus) ---

async def deletebus_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts /deletebus wizard by listing destinations."""
    if not await check_admin_permission(update):
        return ConversationHandler.END

    destinations = get_destinations()
    keyboard = []
    for d in destinations:
        keyboard.append([InlineKeyboardButton(d["name"], callback_data=f"del_dest_{d['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")])
    
    await update.message.reply_text(
        text="🗑️ *Delete Timetable Entry*\n\nSelect the destination stop:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return DEL_CHOOSE_DEST

async def deletebus_choose_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lists schedules for deletion at the selected destination."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "del_cancel":
        return await cancel(update, context)
        
    dest_id = int(query.data.split("_")[2])
    dest_name = get_destination_by_id(dest_id)
    
    schedules = get_schedules_by_destination(dest_id)
    if not schedules:
        await query.edit_message_text(f"No schedules registered for destination {dest_name}.")
        context.user_data.clear()
        return ConversationHandler.END
        
    keyboard = []
    for s in schedules:
        label = f"[{s['arrival_time']}] {s['bus_name']}"
        if dest_name == "Njarakkadu":
            label += f" (From: {s['from_point']})"
        label += f" (ID: {s['schedule_id']})"
        keyboard.append([
            InlineKeyboardButton(
                f"🗑️ {label}", 
                callback_data=f"del_select_{s['schedule_id']}"
            )
        ])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")])
    
    await query.edit_message_text(
        text=f"📍 Destination: *{dest_name}*\n\nSelect the schedule to delete:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return DEL_SELECT_SCHED

async def deletebus_select_sched(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for confirmation before deleting schedule."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "del_cancel":
        return await cancel(update, context)
        
    sched_id = int(query.data.split("_")[2])
    context.user_data["delete_sched_id"] = sched_id
    
    details = get_schedule_details(sched_id)
    if not details:
        await query.edit_message_text("Schedule not found.")
        context.user_data.clear()
        return ConversationHandler.END
        
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Delete", callback_data="del_confirm_yes"),
            InlineKeyboardButton("❌ No, Cancel", callback_data="del_cancel")
        ]
    ]
    
    text = (
        "⚠️ *Confirm Schedule Deletion* ⚠️\n\n"
        f"Are you sure you want to delete this schedule?\n"
        f"• *ID:* `{sched_id}`\n"
        f"• *Bus Name:* {details['bus_name']} ({details['bus_type']})\n"
        f"• *Destination:* {details['destination_name']}\n"
        f"• *Time:* {details['arrival_time']}\n"
        f"• *Active Schedule:* {details['day_type']}\n\n"
        "This action cannot be undone."
    )
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return DEL_CONFIRM

async def deletebus_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Performs schedule deletion and confirms to the user."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "del_cancel":
        return await cancel(update, context)
        
    sched_id = context.user_data["delete_sched_id"]
    
    try:
        success = delete_schedule(sched_id)
        if success:
            await query.edit_message_text(f"✅ Schedule ID `{sched_id}` deleted successfully.")
        else:
            await query.edit_message_text(f"❌ Error: Schedule ID `{sched_id}` could not be found.")
    except Exception as e:
        logger.error(f"Error deleting schedule: {e}")
        await query.edit_message_text(f"❌ Error deleting schedule:\n`{e}`")
        
    context.user_data.clear()
    return ConversationHandler.END


# --- Holiday Commands ---

async def add_holiday_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a new holiday to the database. Usage: /addholiday YYYY-MM-DD"""
    if not await check_admin_permission(update):
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("❌ Usage: `/addholiday YYYY-MM-DD` (e.g. `/addholiday 2026-08-15`)", parse_mode="Markdown")
        return
        
    date_str = context.args[0].strip()
    
    # Validate YYYY-MM-DD format
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        await update.message.reply_text("❌ Invalid date format. Must be YYYY-MM-DD.")
        return
        
    try:
        # Check if valid date
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        add_holiday(date_str)
        await update.message.reply_text(f"✅ Holiday *{date_str}* added successfully. Schedules of type `holiday` will run on this date.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid calendar date. Please check the month and day.")
    except Exception as e:
        logger.error(f"Error adding holiday: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def delete_holiday_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes a holiday from the database. Usage: /deleteholiday YYYY-MM-DD"""
    if not await check_admin_permission(update):
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("❌ Usage: `/deleteholiday YYYY-MM-DD`", parse_mode="Markdown")
        return
        
    date_str = context.args[0].strip()
    
    try:
        success = delete_holiday(date_str)
        if success:
            await update.message.reply_text(f"✅ Holiday *{date_str}* removed successfully.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Holiday *{date_str}* not found in database.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error deleting holiday: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def list_holidays_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all registered holidays."""
    if not await check_admin_permission(update):
        return

    holidays = get_all_holidays()
    if not holidays:
        await update.message.reply_text("📅 No holidays registered.")
        return
        
    text = "📅 *Registered Holidays (Timetable Type: holiday)*\n\n"
    for h in holidays:
        text += f"• {h}\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")
