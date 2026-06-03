import datetime
import pytz
from typing import Tuple
from src.config import TIMEZONE, logger

def get_local_now() -> datetime.datetime:
    """Returns the current localized datetime according to the configured timezone."""
    try:
        tz = pytz.timezone(TIMEZONE)
    except Exception as e:
        logger.error(f"Invalid timezone configuration: {TIMEZONE}. Falling back to Asia/Kolkata. Error: {e}")
        tz = pytz.timezone("Asia/Kolkata")
    return datetime.datetime.now(tz)

def get_current_time_24h() -> str:
    """Returns the current local time in HH:MM format (24-hour)."""
    now = get_local_now()
    return now.strftime("%H:%M")

def time_to_minutes(time_str: str) -> int:
    """Converts HH:MM 24h string to minutes since midnight."""
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {time_str}. Must be HH:MM.")
    hours = int(parts[0])
    minutes = int(parts[1])
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError(f"Time out of range: {time_str}")
    return hours * 60 + minutes

def minutes_to_time_str_24h(minutes: int) -> str:
    """Converts minutes since midnight to HH:MM 24h string."""
    minutes = minutes % (24 * 60) # Ensure it wraps around 24 hours
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

def format_24h_to_12h(time_str: str) -> str:
    """Converts HH:MM (24-hour) string to 12-hour AM/PM string (e.g. 15:05 -> 3:05 PM)."""
    try:
        t = datetime.datetime.strptime(time_str, "%H:%M")
        # %I is 12-hour hour, %M is minute, %p is AM/PM.
        # lstrip('0') is used to remove leading zero from hour, but standard strftime may format differently on Windows vs Linux.
        # We can handle it safely in code.
        formatted = t.strftime("%I:%M %p")
        if formatted.startswith("0"):
            formatted = formatted[1:]
        return formatted
    except Exception as e:
        logger.error(f"Error formatting time {time_str}: {e}")
        return time_str

def calculate_wait_time_minutes(current_time_str: str, arrival_time_str: str) -> int:
    """Calculates wait time in minutes between current time and arrival time, handling midnight wrap-around."""
    curr_min = time_to_minutes(current_time_str)
    arr_min = time_to_minutes(arrival_time_str)
    diff = arr_min - curr_min
    if diff < 0:
        diff += 24 * 60 # Midnight wrap-around
    return diff

def format_wait_time(minutes: int) -> str:
    """Formats wait time in minutes to a user-friendly string (e.g. 5 minutes or 1 hour 15 minutes)."""
    if minutes == 0:
        return "Now arriving"
    if minutes == 1:
        return "1 minute"
    if minutes < 60:
        return f"{minutes} minutes"
    
    hours = minutes // 60
    mins = minutes % 60
    
    hours_str = "1 hour" if hours == 1 else f"{hours} hours"
    mins_str = ""
    if mins > 0:
        mins_str = " 1 minute" if mins == 1 else f" {mins} minutes"
        
    return f"{hours_str}{mins_str}"

def calculate_expected_arrival(arrival_time_str: str, duration_minutes: int) -> str:
    """Calculates expected arrival time by adding journey duration to the arrival time."""
    arr_min = time_to_minutes(arrival_time_str)
    exp_min = (arr_min + duration_minutes) % (24 * 60)
    return minutes_to_time_str_24h(exp_min)
