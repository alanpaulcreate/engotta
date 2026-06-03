import sys
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ConversationHandler, MessageHandler, filters
)
from src.config import BOT_TOKEN, logger
from src.db import init_db
from src.handlers.user import (
    start_command, destination_callback, available_now_callback, 
    route_details_callback
)
from src.handlers.admin import (
    # Common actions
    cancel,
    # Listschedules
    list_schedules_command,
    # Addbus conversation
    addbus_start, addbus_choose_dest, addbus_enter_name, 
    addbus_choose_type, addbus_enter_time, addbus_enter_duration, 
    addbus_choose_daytype,
    ADD_CHOOSE_DEST, ADD_ENTER_NAME, ADD_CHOOSE_TYPE, 
    ADD_ENTER_TIME, ADD_ENTER_DURATION, ADD_CHOOSE_DAYTYPE,
    # Editbus conversation
    editbus_start, editbus_choose_dest, editbus_select_sched,
    editbus_choose_field, editbus_enter_time, editbus_enter_duration,
    editbus_choose_daytype,
    EDIT_CHOOSE_DEST, EDIT_SELECT_SCHED, EDIT_CHOOSE_FIELD,
    EDIT_ENTER_TIME, EDIT_ENTER_DURATION, EDIT_CHOOSE_DAYTYPE,
    # Deletebus conversation
    deletebus_start, deletebus_choose_dest, deletebus_select_sched,
    deletebus_confirm,
    DEL_CHOOSE_DEST, DEL_SELECT_SCHED, DEL_CONFIRM,
    # Holiday commands
    add_holiday_command, delete_holiday_command, list_holidays_command
)

def main() -> None:
    """Main function to initialize database and run the Telegram bot."""
    if not BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is missing! Set it in your environment or .env file.")
        sys.exit(1)
        
    # 1. Initialize SQLite Database (creates tables & seeds default timetable)
    try:
        init_db()
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}")
        sys.exit(1)
        
    # 2. Build Telegram Application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # 3. Register Conversation Handlers for Admins
    
    # /addbus Conversation
    addbus_conv = ConversationHandler(
        entry_points=[CommandHandler("addbus", addbus_start)],
        states={
            ADD_CHOOSE_DEST: [CallbackQueryHandler(addbus_choose_dest, pattern="^add_dest_\\d+$|^add_cancel$")],
            ADD_ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addbus_enter_name)],
            ADD_CHOOSE_TYPE: [CallbackQueryHandler(addbus_choose_type, pattern="^add_type_.*$|^add_cancel$")],
            ADD_ENTER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addbus_enter_time)],
            ADD_ENTER_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, addbus_enter_duration)],
            ADD_CHOOSE_DAYTYPE: [CallbackQueryHandler(addbus_choose_daytype, pattern="^add_day_.*$|^add_cancel$")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^add_cancel$")
        ],
        per_message=False
    )
    
    # /editbus Conversation
    editbus_conv = ConversationHandler(
        entry_points=[CommandHandler("editbus", editbus_start)],
        states={
            EDIT_CHOOSE_DEST: [CallbackQueryHandler(editbus_choose_dest, pattern="^edit_dest_\\d+$|^edit_cancel$")],
            EDIT_SELECT_SCHED: [CallbackQueryHandler(editbus_select_sched, pattern="^edit_sched_\\d+$|^edit_cancel$")],
            EDIT_CHOOSE_FIELD: [CallbackQueryHandler(editbus_choose_field, pattern="^edit_field_.*$|^edit_cancel$")],
            EDIT_ENTER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, editbus_enter_time)],
            EDIT_ENTER_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, editbus_enter_duration)],
            EDIT_CHOOSE_DAYTYPE: [CallbackQueryHandler(editbus_choose_daytype, pattern="^edit_day_.*$|^edit_cancel$")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^edit_cancel$")
        ],
        per_message=False
    )
    
    # /deletebus Conversation
    deletebus_conv = ConversationHandler(
        entry_points=[CommandHandler("deletebus", deletebus_start)],
        states={
            DEL_CHOOSE_DEST: [CallbackQueryHandler(deletebus_choose_dest, pattern="^del_dest_\\d+$|^del_cancel$")],
            DEL_SELECT_SCHED: [CallbackQueryHandler(deletebus_select_sched, pattern="^del_select_\\d+$|^del_cancel$")],
            DEL_CONFIRM: [CallbackQueryHandler(deletebus_confirm, pattern="^del_confirm_yes$|^del_cancel$")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^del_cancel$")
        ],
        per_message=False
    )
    
    application.add_handler(addbus_conv)
    application.add_handler(editbus_conv)
    application.add_handler(deletebus_conv)
    
    # 4. Register Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("listschedules", list_schedules_command))
    application.add_handler(CommandHandler("addholiday", add_holiday_command))
    application.add_handler(CommandHandler("deleteholiday", delete_holiday_command))
    application.add_handler(CommandHandler("listholidays", list_holidays_command))
    
    # 5. Register Callback Query Handlers (User-facing actions)
    application.add_handler(CallbackQueryHandler(destination_callback, pattern="^dest_\\d+$"))
    application.add_handler(CallbackQueryHandler(available_now_callback, pattern="^available_now$"))
    application.add_handler(CallbackQueryHandler(route_details_callback, pattern="^route_\\d+$"))
    application.add_handler(CallbackQueryHandler(start_command, pattern="^menu_back$"))
    
    # 6. Start the Bot
    logger.info("Starting Telegram bot polling loop...")
    application.run_polling()

if __name__ == "__main__":
    main()
