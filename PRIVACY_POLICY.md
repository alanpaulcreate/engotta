# Privacy Policy for Engotta Telegram Bot

**Last Updated: June 3, 2026**

This Privacy Policy explains how the **Engotta Telegram Bot** ("the Bot") handles your information. 

By using the Bot, you agree to the practices described in this policy.

---

## 1. Information We Collect

### A. Non-Personal & Operational Data
Because the Bot is designed to be simple and privacy-focused, we do not require you to register, share your location, or provide personal details. We only process operational data required to deliver bus timetable results:
* **Telegram User Interactions:** Standard metadata sent by Telegram (such as user ID, username, and language code) is processed to handle commands and button clicks.
* **Callback Queries:** When you click buttons (e.g., selecting a destination), the selection is processed to fetch the correct schedule.

### B. Admin Data
For administrators managing the database:
* **Administrator User IDs:** Configured administrative Telegram User IDs are stored in the server configuration (`.env` file) to restrict access to scheduling commands (like adding, editing, or deleting bus routes).

---

## 2. How We Use the Information
We use the processed data solely to:
* Answer your queries (e.g., display the next available bus for your selected destination).
* Authenticate administrators using authorized Telegram IDs.
* Maintain, debug, and improve bot performance.

---

## 3. Data Storage and Security
* **No Database Logging of Users:** The Bot's database (SQLite) stores only static bus timetable schedules, stops, and holiday dates. We **do not** store logs of who checked which bus or keep a history of your chats in our database.
* **No Location Tracking:** We do not track your GPS location. You manually choose your destination using interactive buttons.

---

## 4. Third-Party Services
* **Telegram API:** The Bot operates on the Telegram platform. Your usage of the Bot is also subject to the [Telegram Privacy Policy](https://telegram.org/privacy).
* **Veyil Link:** The Bot contains an external link to [Veyil](https://veyil.app). If you click this link, you will be redirected to their website, which is subject to its own privacy policy. We do not transfer any user data to Veyil.

---

## 5. Data Sharing & Disclosure
We **do not** sell, trade, or share your data with any third parties. 

---

## 6. Your Rights
Since we do not store personal data or keep track of your user history, there is no personal data for us to delete, modify, or export. 

---

## 7. Contact Us
If you host your own instance of this bot or have questions regarding its configuration, please contact the repository administrator.
