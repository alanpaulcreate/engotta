import os
import json
import datetime
from flask import Flask, request, Response, send_file
from twilio.twiml.messaging_response import MessagingResponse

from src.db import (
    get_destinations, get_destination_by_id, get_next_buses,
    get_schedule_details, get_distinct_from_points, get_schedules_for_day,
    get_schedules_by_bus_name_search
)
from src.utils.time_helper import (
    get_local_now, format_24h_to_12h, calculate_wait_time_minutes, 
    format_wait_time, calculate_expected_arrival, time_to_minutes, 
    parse_user_time
)
from src.handlers.user import get_day_type
from src.whatsapp_db import (
    init_whatsapp_db, get_whatsapp_session, save_whatsapp_session, 
    delete_whatsapp_session
)
from src.config import logger

app = Flask(__name__)

# Initialize the WhatsApp sessions table when this module is imported or start_whatsapp_server is called
try:
    init_whatsapp_db()
except Exception as e:
    logger.error(f"Failed to initialize WhatsApp sessions database: {e}")

# Session State Constants
STATE_MAIN_MENU = "MAIN_MENU"
STATE_SELECT_NJARAKKADU_FROM = "SELECT_NJARAKKADU_FROM"
STATE_VIEWING_BUSES = "VIEWING_BUSES"
STATE_REACH_SELECT_DEST = "REACH_SELECT_DEST"
STATE_REACH_SELECT_NJARAKKADU_FROM = "REACH_SELECT_NJARAKKADU_FROM"
STATE_REACH_ENTER_TIME = "REACH_ENTER_TIME"
STATE_SEARCH_BUS_NAME = "SEARCH_BUS_NAME"

def get_main_menu_text() -> str:
    """Constructs the welcome and main menu text dynamically based on configured destinations."""
    destinations = get_destinations()
    text = (
        "🚌 *Welcome to Engotta!*\n"
        "Your instant guide to the next available bus.\n\n"
        "Which bus can I catch right now?\n\n"
        "Reply with a number to choose an option:\n"
    )
    for idx, dest in enumerate(destinations, 1):
        text += f"{idx}️⃣ {dest['name']}\n"
    
    # Option indices
    reach_idx = len(destinations) + 1
    avail_idx = len(destinations) + 2
    veyil_idx = len(destinations) + 3
    search_idx = len(destinations) + 4
    
    text += f"{reach_idx}️⃣ ⏱ Reach by Time\n"
    text += f"{avail_idx}️⃣ 🚌 Available Now\n"
    text += f"{veyil_idx}️⃣ ☀ Veyil\n"
    text += f"{search_idx}️⃣ 🔍 Search Bus by Name\n\n"
    text += "_You can send \"menu\" or \"start\" at any time to return here._"
    return text

def format_destination_buses(dest_id: int, dest_name: str, from_point: str = None) -> tuple:
    """Formats the next/upcoming buses for a specific destination."""
    now = get_local_now()
    current_time = now.strftime("%H:%M")
    day_type = get_day_type(now)
    
    # Fetch next buses (up to 4)
    next_schedules = get_next_buses(dest_id, current_time, day_type, limit=4, from_point=from_point)
    
    display_title = dest_name
    if from_point:
        display_title += f" (From: {from_point})"
        
    if not next_schedules:
        text = (
            f"📍 *{display_title}*\n\n"
            "❌ No scheduled buses found for today.\n\n"
            "Reply *0* or *menu* to return to the main menu."
        )
        return text, []
        
    next_bus = next_schedules[0]
    upcoming_buses = next_schedules[1:]
    
    wait_min = calculate_wait_time_minutes(current_time, next_bus["arrival_time"])
    wait_str = format_wait_time(wait_min)
    arrival_12h = format_24h_to_12h(next_bus["arrival_time"])
    
    if dest_name == "Njarakkadu":
        next_bus_str = f"*{next_bus['bus_name']}* ({next_bus['bus_type']})\n• *From:* {next_bus['from_point']}"
    else:
        next_bus_str = f"*{next_bus['bus_name']}* ({next_bus['bus_type']})"
        
    text = (
        f"📍 *{display_title}*\n\n"
        f"🚌 *Next Bus*\n"
        f"1️⃣ {next_bus_str}\n"
        f"🕒 *Arrival:* {arrival_12h}\n"
        f"⏳ *Waiting Time:* {wait_str}\n"
    )
    
    schedules_stored = [next_bus["schedule_id"]]
    
    if upcoming_buses:
        text += "\n*Upcoming Buses:*\n"
        for idx, bus in enumerate(upcoming_buses, 2):
            bus_arr_12h = format_24h_to_12h(bus["arrival_time"])
            schedules_stored.append(bus["schedule_id"])
            emoji = f"{idx}️⃣"
            if dest_name == "Njarakkadu":
                text += f"{emoji} {bus_arr_12h} - {bus['bus_name']} ({bus['bus_type']}) [From: {bus['from_point']}]\n"
            else:
                text += f"{emoji} {bus_arr_12h} - {bus['bus_name']} ({bus['bus_type']})\n"
                
    text += (
        "\n_Reply with a number (1-4) to view full bus details (journey duration, expected arrival, etc.)._\n"
        "_Reply *0* or *menu* to return to the main menu._"
    )
    return text, schedules_stored

def get_available_now_text() -> str:
    """Builds the text for the 'Available Now' dashboard."""
    now = get_local_now()
    current_time = now.strftime("%H:%M")
    day_type = get_day_type(now)
    
    destinations = get_destinations()
    text = "🚌 *Available Now*\n\n"
    
    for dest in destinations:
        next_schedules = get_next_buses(dest["id"], current_time, day_type, limit=1)
        text += f"📍 *{dest['name']}*\n"
        if next_schedules:
            next_bus = next_schedules[0]
            arr_12h = format_24h_to_12h(next_bus["arrival_time"])
            if dest['name'] == "Njarakkadu":
                text += f"{next_bus['bus_name']} [From: {next_bus['from_point']}] - {arr_12h}\n\n"
            else:
                text += f"{next_bus['bus_name']} - {arr_12h}\n\n"
        else:
            text += "No schedules today\n\n"
            
    text += "Reply *0* or *menu* to return to the main menu."
    return text

def format_bus_details(schedule_id: int) -> str:
    """Retrieves and formats full schedule details for a given schedule ID."""
    details = get_schedule_details(schedule_id)
    if not details:
        return "❌ Bus details not found."
        
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
        f"• *Expected Arrival:* {exp_12h}\n\n"
        f"_Reply with another number to view details, or *0* to return to the main menu._"
    )
    return text

@app.route("/", methods=["GET"])
@app.route("/ping", methods=["GET"])
def ping():
    """Health check endpoint for keeping the bot awake."""
    return Response("OK", status=200)

@app.route("/download-db", methods=["GET"])
def download_db():
    """Temporary endpoint to download the live SQLite database."""
    import os
    from pathlib import Path
    # Resolve path relative to the project root (where bot is started from)
    db_path = Path(os.getcwd()) / os.getenv("DATABASE_PATH", "data/database.db")
    if db_path.exists():
        return send_file(str(db_path), as_attachment=True, download_name="database.db")
    return f"Database not found at: {db_path}", 404

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Handles incoming Twilio WhatsApp requests."""
    phone_number = request.values.get("From", "")
    body = request.values.get("Body", "").strip()
    
    if not phone_number or not body:
        return Response("", status=200)
        
    # Standard normalization for main actions
    norm_body = body.lower()
    
    # 1. Reset / Go to menu if keyword detected
    if norm_body in ["menu", "start", "reset", "help", "hi", "hello"]:
        delete_whatsapp_session(phone_number)
        resp_text = get_main_menu_text()
        save_whatsapp_session(phone_number, STATE_MAIN_MENU, {})
        twiml = MessagingResponse()
        twiml.message(resp_text)
        return Response(str(twiml), mimetype="application/xml")
        
    # Get user session
    session = get_whatsapp_session(phone_number)
    if not session:
        # Default fallback to main menu
        resp_text = get_main_menu_text()
        save_whatsapp_session(phone_number, STATE_MAIN_MENU, {})
        twiml = MessagingResponse()
        twiml.message(resp_text)
        return Response(str(twiml), mimetype="application/xml")
        
    state = session["state"]
    context = session["context_data"]
    
    destinations = get_destinations()
    dest_names_lower = {d["name"].lower(): d for d in destinations}
    
    reply_text = ""
    next_state = state
    next_context = context.copy()
    
    # --- State Machine ---
    if state == STATE_MAIN_MENU:
        # Parse inputs: 1 to len(destinations), or text match
        dest_match = None
        choice_idx = -1
        
        if body.isdigit():
            choice_idx = int(body)
        else:
            # Try text match
            for name, dest in dest_names_lower.items():
                if name in norm_body:
                    dest_match = dest
                    break
                    
        reach_idx = len(destinations) + 1
        avail_idx = len(destinations) + 2
        veyil_idx = len(destinations) + 3
        search_idx = len(destinations) + 4
        
        # Check choice
        if dest_match or (1 <= choice_idx <= len(destinations)):
            selected_dest = dest_match or destinations[choice_idx - 1]
            dest_id = selected_dest["id"]
            dest_name = selected_dest["name"]
            
            if dest_name == "Njarakkadu":
                # Multiple starting points, show submenu
                next_state = STATE_SELECT_NJARAKKADU_FROM
                next_context = {"dest_id": dest_id, "dest_name": dest_name}
                
                reply_text = (
                    f"📍 *{dest_name}*\n\n"
                    "Select the starting bus stand:\n"
                    "1️⃣ From Thodupuzha\n"
                    "2️⃣ From Muvattupuzha\n"
                    "3️⃣ From Kothamangalam\n"
                    "4️⃣ From Kaliyar\n\n"
                    "_Reply with a number (1-4), or *0* to return to the main menu._"
                )
            else:
                # Direct lookup
                reply_text, schedules = format_destination_buses(dest_id, dest_name)
                if schedules:
                    next_state = STATE_VIEWING_BUSES
                    next_context = {"schedules": schedules, "dest_id": dest_id, "dest_name": dest_name}
                else:
                    next_state = STATE_MAIN_MENU
                    next_context = {}
                    
        elif choice_idx == reach_idx or "reach" in norm_body:
            # Reach by Time
            next_state = STATE_REACH_SELECT_DEST
            reply_text = "⏱ *Reach Destination by Time*\n\nSelect your destination:\n"
            for idx, dest in enumerate(destinations, 1):
                reply_text += f"{idx}️⃣ {dest['name']}\n"
            reply_text += "\n_Reply with a number (1-5), or *0* to return to the main menu._"
            
        elif choice_idx == avail_idx or "avail" in norm_body:
            reply_text = get_available_now_text()
            
        elif choice_idx == veyil_idx or "veyil" in norm_body:
            reply_text = "☀ Veyil app is available at: https://veyil.app\n\nReply *0* or *menu* to return to the main menu."

        elif choice_idx == search_idx or "search" in norm_body or "bus name" in norm_body:
            # Search Bus by Name
            next_state = STATE_SEARCH_BUS_NAME
            reply_text = (
                "🔍 *Search Bus by Name*\n\n"
                "Type the bus name (or part of it) and I'll show you its upcoming trips for today.\n\n"
                "_Reply *0* or *menu* to return to the main menu._"
            )

        else:
            reply_text = "⚠️ Invalid option. Please select a valid number from the menu (or send *menu* to see it again)."
            
    elif state == STATE_SELECT_NJARAKKADU_FROM:
        # Starting stands for Njarakkadu: 1. Thodupuzha, 2. Muvattupuzha, 3. Kothamangalam, 4. Kaliyar
        stands = ["Thodupuzha", "Muvattupuzha", "Kothamangalam", "Kaliyar"]
        
        if body == "0":
            next_state = STATE_MAIN_MENU
            next_context = {}
            reply_text = get_main_menu_text()
        elif body.isdigit() and 1 <= int(body) <= len(stands):
            from_point = stands[int(body) - 1]
            dest_id = context.get("dest_id")
            dest_name = context.get("dest_name", "Njarakkadu")
            
            reply_text, schedules = format_destination_buses(dest_id, dest_name, from_point=from_point)
            if schedules:
                next_state = STATE_VIEWING_BUSES
                next_context = {"schedules": schedules, "dest_id": dest_id, "dest_name": dest_name, "from_point": from_point}
            else:
                next_state = STATE_MAIN_MENU
                next_context = {}
        else:
            reply_text = "⚠️ Invalid starting stand. Reply 1-4, or *0* to cancel and return to main menu."
            
    elif state == STATE_VIEWING_BUSES:
        schedules = context.get("schedules", [])
        
        if body == "0":
            next_state = STATE_MAIN_MENU
            next_context = {}
            reply_text = get_main_menu_text()
        elif body.isdigit() and 1 <= int(body) <= len(schedules):
            schedule_id = schedules[int(body) - 1]
            reply_text = format_bus_details(schedule_id)
            # Stay in VIEWING_BUSES so they can view details for other buses
        else:
            reply_text = f"⚠️ Invalid option. Reply with a number (1-{len(schedules)}) to view details, or *0* to go back."
            
    elif state == STATE_REACH_SELECT_DEST:
        if body == "0":
            next_state = STATE_MAIN_MENU
            next_context = {}
            reply_text = get_main_menu_text()
        elif body.isdigit() and 1 <= int(body) <= len(destinations):
            selected_dest = destinations[int(body) - 1]
            dest_id = selected_dest["id"]
            dest_name = selected_dest["name"]
            
            next_context = {"reach_dest_id": dest_id, "reach_dest_name": dest_name}
            
            if dest_name == "Njarakkadu":
                next_state = STATE_REACH_SELECT_NJARAKKADU_FROM
                reply_text = (
                    f"📍 Destination: *{dest_name}*\n\n"
                    "Select the starting stand:\n"
                    "1️⃣ From Thodupuzha\n"
                    "2️⃣ From Muvattupuzha\n"
                    "3️⃣ From Kothamangalam\n"
                    "4️⃣ From Kaliyar\n\n"
                    "_Reply with a number (1-4), or *0* to return to main menu._"
                )
            else:
                next_state = STATE_REACH_ENTER_TIME
                reply_text = (
                    f"📍 Destination: *{dest_name}*\n\n"
                    "💬 Enter the time by which you need to reach (e.g. *10:30 AM* or *15:00*):\n\n"
                    "_Reply *0* to cancel and return to main menu._"
                )
        else:
            reply_text = "⚠️ Invalid destination selection. Reply 1-5, or *0* to cancel."
            
    elif state == STATE_REACH_SELECT_NJARAKKADU_FROM:
        stands = ["Thodupuzha", "Muvattupuzha", "Kothamangalam", "Kaliyar"]
        
        if body == "0":
            next_state = STATE_MAIN_MENU
            next_context = {}
            reply_text = get_main_menu_text()
        elif body.isdigit() and 1 <= int(body) <= len(stands):
            from_point = stands[int(body) - 1]
            dest_id = context.get("reach_dest_id")
            dest_name = context.get("reach_dest_name", "Njarakkadu")
            
            next_state = STATE_REACH_ENTER_TIME
            next_context = {
                "reach_dest_id": dest_id,
                "reach_dest_name": dest_name,
                "reach_from_point": from_point
            }
            reply_text = (
                f"📍 Destination: *{dest_name}* (From: *{from_point}*)\n\n"
                "💬 Enter the time by which you need to reach (e.g. *10:30 AM* or *15:00*):\n\n"
                "_Reply *0* to cancel and return to main menu._"
            )
        else:
            reply_text = "⚠️ Invalid selection. Reply 1-4, or *0* to cancel."
            
    elif state == STATE_REACH_ENTER_TIME:
        if body == "0":
            next_state = STATE_MAIN_MENU
            next_context = {}
            reply_text = get_main_menu_text()
        else:
            target_time_24h = parse_user_time(body)
            if not target_time_24h:
                reply_text = (
                    "❌ *Invalid time format.*\n\n"
                    "Please enter the time in formats like *10:30 AM*, *14:15*, or *3:00 PM*:\n"
                    "(Or reply *0* to cancel)"
                )
            else:
                dest_id = context["reach_dest_id"]
                dest_name = context["reach_dest_name"]
                from_point = context.get("reach_from_point")
                
                # Run reach search logic (copied and adjusted from user.py)
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
                
                # Same day search
                if target_time_24h >= current_time:
                    today_schedules = get_schedules_for_day(dest_id, today_day_type, from_point)
                    for s in today_schedules:
                        b_time = s["arrival_time"]
                        if b_time >= current_time:
                            b_mins = time_to_minutes(b_time)
                            exp_arr_mins = b_mins + s["travel_duration"]
                            if exp_arr_mins <= target_mins:
                                exp_arr_time = calculate_expected_arrival(b_time, s["travel_duration"])
                                wait_m = b_mins - current_mins
                                reach_diff = target_mins - exp_arr_mins
                                matching_buses.append({
                                    **s,
                                    "expected_arrival": exp_arr_time,
                                    "wait_minutes": wait_m,
                                    "reach_diff": reach_diff,
                                    "is_tomorrow": False
                                })
                else:
                    # Spans midnight
                    # 1. Today's schedules departing after now
                    today_schedules = get_schedules_for_day(dest_id, today_day_type, from_point)
                    for s in today_schedules:
                        b_time = s["arrival_time"]
                        if b_time >= current_time:
                            b_mins = time_to_minutes(b_time)
                            exp_arr_mins = b_mins + s["travel_duration"]
                            if exp_arr_mins <= target_mins:
                                exp_arr_time = calculate_expected_arrival(b_time, s["travel_duration"])
                                wait_m = b_mins - current_mins
                                reach_diff = target_mins - exp_arr_mins
                                matching_buses.append({
                                    **s,
                                    "expected_arrival": exp_arr_time,
                                    "wait_minutes": wait_m,
                                    "reach_diff": reach_diff,
                                    "is_tomorrow": False
                                })
                    # 2. Tomorrow's schedules departing and arriving before target
                    tomorrow_schedules = get_schedules_for_day(dest_id, tomorrow_day_type, from_point)
                    for s in tomorrow_schedules:
                        b_time = s["arrival_time"]
                        b_mins = time_to_minutes(b_time) + 24 * 60
                        exp_arr_mins = b_mins + s["travel_duration"]
                        if exp_arr_mins <= target_mins:
                            exp_arr_time = calculate_expected_arrival(b_time, s["travel_duration"])
                            wait_m = b_mins - current_mins
                            reach_diff = target_mins - exp_arr_mins
                            matching_buses.append({
                                **s,
                                "expected_arrival": exp_arr_time,
                                "wait_minutes": wait_m,
                                "reach_diff": reach_diff,
                                "is_tomorrow": True
                            })
                            
                # Sort: nearest to target arrival first
                matching_buses.sort(key=lambda x: (x["reach_diff"], -x["wait_minutes"]))
                
                target_time_12h = format_24h_to_12h(target_time_24h)
                day_str = "today" if target_time_24h >= current_time else "tomorrow"
                display_dest = dest_name
                if from_point:
                    display_dest += f" (From: {from_point})"
                    
                if not matching_buses:
                    reply_text = (
                        f"⏱ *Reach {display_dest} by {target_time_12h} {day_str}*\n\n"
                        "❌ No scheduled buses found that can be boarded after now and reach by this time.\n\n"
                        "Reply:\n"
                        "1️⃣ Search again\n"
                        "0️⃣ Return to main menu"
                    )
                    # We stay in REACH_ENTER_TIME, but store choices 0 or 1.
                    # Or we can handle choices in next iteration. Let's make an ad-hoc check:
                    # Actually, if they reply "1" next, we will handle it because we'll be in REACH_ENTER_TIME state.
                    # Wait, if they reply "1", body is "1", it's not "0", and `parse_user_time("1")` will fail, prompting again! Which is fine.
                    # But to be cleaner, we can transition to a helper state or just reset to main menu on 0, and reset reach on anything else.
                    # Let's say if matching_buses is empty, we stay in REACH_ENTER_TIME but if they reply "0" we return. If they reply anything else, we try to parse it as a time again.
                else:
                    reply_text = f"⏱ *Buses reaching {display_dest} by {target_time_12h} {day_str}:*\n\n"
                    schedules_stored = []
                    
                    for idx, bus in enumerate(matching_buses[:8], 1):
                        boarding_12h = format_24h_to_12h(bus["arrival_time"])
                        reach_12h = format_24h_to_12h(bus["expected_arrival"])
                        wait_m_str = format_wait_time(bus["wait_minutes"])
                        day_suffix = " (Tomorrow)" if bus["is_tomorrow"] else ""
                        schedules_stored.append(bus["schedule_id"])
                        
                        emoji = f"{idx}️⃣"
                        if dest_name == "Njarakkadu":
                            bus_detail = f"*{bus['bus_name']}* ({bus['bus_type']}) [From: {bus['from_point']}]"
                        else:
                            bus_detail = f"*{bus['bus_name']}* ({bus['bus_type']})"
                            
                        reply_text += (
                            f"{emoji} {bus_detail}\n"
                            f"• *Board:* {boarding_12h}{day_suffix} (in {wait_m_str})\n"
                            f"• *Reach:* {reach_12h}\n"
                            f"• *Journey:* {bus['travel_duration']} mins\n\n"
                        )
                        
                    reply_text += (
                        f"Reply with a number (1-{len(schedules_stored)}) to view details.\n"
                        "Reply *0* to return to main menu."
                    )
                    next_state = STATE_VIEWING_BUSES
                    next_context = {
                        "schedules": schedules_stored,
                        "dest_id": dest_id,
                        "dest_name": dest_name,
                        "from_point": from_point
                    }
                    
    elif state == STATE_SEARCH_BUS_NAME:
        if body == "0":
            next_state = STATE_MAIN_MENU
            next_context = {}
            reply_text = get_main_menu_text()
        else:
            # Search by bus name (partial, case-insensitive)
            now = get_local_now()
            current_time = now.strftime("%H:%M")
            day_type = get_day_type(now)

            results = get_schedules_by_bus_name_search(body, day_type, current_time)

            if not results:
                reply_text = (
                    f"🔍 No upcoming buses matching *\"{body}\"* found for today.\n\n"
                    "Try a different name, or reply *0* or *menu* to return to the main menu."
                )
                # Stay in SEARCH_BUS_NAME so the user can try another query
            else:
                reply_text = f"🔍 *Results for \"{body}\":*\n\n"
                schedules_stored = []

                for idx, s in enumerate(results[:8], 1):
                    arr_12h = format_24h_to_12h(s["arrival_time"])
                    wait_m = calculate_wait_time_minutes(current_time, s["arrival_time"])
                    wait_str = format_wait_time(wait_m)
                    schedules_stored.append(s["schedule_id"])
                    emoji = f"{idx}️⃣"

                    if s.get("from_point") and s["from_point"] != "Njarakkadu":
                        from_str = f" [From: {s['from_point']}]"
                    else:
                        from_str = ""

                    reply_text += (
                        f"{emoji} *{s['bus_name']}* ({s['bus_type']}){from_str}\n"
                        f"• *To:* {s['destination_name']}\n"
                        f"• *Arrives:* {arr_12h} (in {wait_str})\n\n"
                    )

                reply_text += (
                    f"Reply with a number (1-{len(schedules_stored)}) to view full details.\n"
                    "Reply *0* or *menu* to return to the main menu."
                )
                next_state = STATE_VIEWING_BUSES
                next_context = {
                    "schedules": schedules_stored,
                    "dest_id": results[0].get("destination_id"),
                    "dest_name": results[0]["destination_name"],
                }

    # Save the updated session state

    save_whatsapp_session(phone_number, next_state, next_context)
    
    twiml = MessagingResponse()
    twiml.message(reply_text)
    return Response(str(twiml), mimetype="application/xml")

def start_whatsapp_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    """Starts the Flask server to handle webhooks."""
    app.run(host=host, port=port, use_reloader=False)

if __name__ == "__main__":
    start_whatsapp_server(port=5000)
