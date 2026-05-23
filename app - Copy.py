import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import openpyxl

import automation
from automation import DB_PATH, state, load_db, save_db, run_automation_worker, open_linkedin_for_login, sync_acceptance_task

app = Flask(__name__, static_folder="public")
CORS(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Standard response helper
def err_response(message, code=400):
    return jsonify({"error": message}), code

# Serves frontend files
@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")

# API - Get Current Automation State
@app.route("/api/state", methods=["GET"])
def get_automation_state():
    return jsonify(state.get_state())

# API - Get Contacts list
@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    return jsonify(load_db())

# API - Add a single contact
@app.route("/api/contacts/add", methods=["POST"])
def add_contact():
    if state.is_running:
        return err_response("Cannot add contacts while automation is running.")
        
    req_data = request.json or {}
    url = req_data.get("profile_url", "").strip()
    name = req_data.get("name", "").strip()
    
    if not url:
        return err_response("Profile URL is required.")
        
    if "linkedin.com/" not in url:
        if url.isalnum():
            url = f"https://www.linkedin.com/in/{url}"
        else:
            return err_response("Invalid LinkedIn URL. Must contain 'linkedin.com/in/'.")
            
    norm_url = url.split('?')[0].rstrip('/')
    
    db_data = load_db()
    existing_urls = {c.get("profile_url", "").strip().split('?')[0].rstrip('/') for c in db_data}
    
    if norm_url in existing_urls:
        return err_response("This profile URL already exists in the database.")
        
    if not name:
        # Guess name from username
        username = url.split("/in/")[-1].split("/")[0].replace("-", " ")
        name = username.title()
        
    first_name = ""
    last_name = ""
    parts = name.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    
    new_contact = {
        "name": name,
        "first_name": first_name,
        "last_name": last_name,
        "profile_url": url,
        "company": req_data.get("company", "").strip(),
        "title": req_data.get("title", "").strip(),
        "status": "Not Started",
        "date_sent": None,
        "date_accepted": None,
        "logs": None
    }
    
    db_data.append(new_contact)
    save_db(db_data)
    
    state.add_log(f"Added single profile URL: {name} ({url})", "success")
    return jsonify({"status": "success", "message": f"Successfully added {name} to list."})


# API - Clear all contacts
@app.route("/api/contacts/clear", methods=["POST"])
def clear_contacts():
    if state.is_running:
        return err_response("Cannot clear contacts while automation is running.")
    save_db([])
    state.add_log("Database cleared by user.", "warning")
    return jsonify({"status": "success", "message": "Contacts list cleared."})

# API - Delete a single contact
@app.route("/api/contacts/delete", methods=["POST"])
def delete_contact():
    if state.is_running:
        return err_response("Cannot delete contacts while automation is running.")
        
    req_data = request.json or {}
    url = req_data.get("profile_url", "").strip()
    
    if not url:
        return err_response("Profile URL is required to delete a contact.")
        
    db_data = load_db()
    index_to_remove = -1
    for i, contact in enumerate(db_data):
        if contact.get("profile_url", "").strip() == url:
            index_to_remove = i
            break
            
    if index_to_remove == -1:
        return err_response("Contact not found in database.")
        
    removed = db_data.pop(index_to_remove)
    save_db(db_data)
    
    state.add_log(f"Deleted contact: {removed.get('name')} ({url})", "warning")
    return jsonify({"status": "success", "message": f"Successfully deleted {removed.get('name')}."})

# API - Reset specific or all statuses (failed/pending -> Not Started)
@app.route("/api/contacts/reset", methods=["POST"])
def reset_contacts():
    if state.is_running:
        return err_response("Cannot reset contacts while automation is running.")
        
    req_data = request.json or {}
    scope = req_data.get("scope", "all") # "all", "failed", "pending"
    
    db_data = load_db()
    reset_count = 0
    for contact in db_data:
        status = contact.get("status", "Not Started")
        if scope == "all":
            contact["status"] = "Not Started"
            contact["date_sent"] = None
            contact["date_accepted"] = None
            contact["logs"] = None
            reset_count += 1
        elif scope == "failed" and status == "Failed":
            contact["status"] = "Not Started"
            contact["logs"] = None
            reset_count += 1
        elif scope == "pending" and status == "Pending":
            contact["status"] = "Not Started"
            contact["date_sent"] = None
            reset_count += 1
            
    save_db(db_data)
    state.add_log(f"Reset {reset_count} contact(s) back to 'Not Started' ({scope} scope).", "info")
    return jsonify({"status": "success", "message": f"Successfully reset {reset_count} contacts."})

# API - Launch browser for manual login
@app.route("/api/launch-login", methods=["POST"])
def launch_login():
    if state.is_running:
        return err_response("Automation is currently running. Please wait or stop it first.")
    
    open_linkedin_for_login()
    return jsonify({"status": "success", "message": "Browser launched. Please check taskbar."})

# API - Start connection automation
@app.route("/api/start", methods=["POST"])
def start_automation():
    if state.is_running:
        return err_response("Automation is already running.")
        
    config = request.json or {}
    note_template = config.get("note_template", "")
    send_with_note = config.get("send_with_note", False)
    delay_min = int(config.get("delay_min", 30))
    delay_max = int(config.get("delay_max", 70))
    daily_limit = int(config.get("daily_limit", 50))
    
    start_index = config.get("start_index")
    end_index = config.get("end_index")
    
    # Safely convert to integers if provided
    try:
        start_index = int(start_index) if start_index is not None and str(start_index).strip() != "" else None
    except ValueError:
        start_index = None
        
    try:
        end_index = int(end_index) if end_index is not None and str(end_index).strip() != "" else None
    except ValueError:
        end_index = None
        
    # Enforce safe delay constraints
    if delay_min < 10:
        delay_min = 10
    if delay_max < delay_min:
        delay_max = delay_min + 10
        
    run_automation_worker(
        note_template=note_template,
        send_with_note=send_with_note,
        delay_min=delay_min,
        delay_max=delay_max,
        daily_limit=daily_limit,
        start_index=start_index,
        end_index=end_index
    )
    return jsonify({"status": "success", "message": "Automation worker started."})

# API - Stop/Pause automation
@app.route("/api/stop", methods=["POST"])
def stop_automation():
    state.stop_requested = True
    state.add_log("Pause request received. Stopping at next safe point...", "warning")
    return jsonify({"status": "success", "message": "Stop signal sent."})

# API - Sync Acceptance
@app.route("/api/sync-acceptance", methods=["POST"])
def sync_acceptance():
    if state.is_running:
        return err_response("Automation is currently running.")
        
    sync_acceptance_task()
    return jsonify({"status": "success", "message": "Acceptance sync worker started."})

# API - Upload Excel Sheet
@app.route("/api/upload", methods=["POST"])
def upload_file():
    if state.is_running:
        return err_response("Cannot upload files while automation is running.")
        
    if 'file' not in request.files:
        return err_response("No file part in the request.")
        
    file = request.files['file']
    if file.filename == '':
        return err_response("No selected file.")
        
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        return err_response("Invalid file type. Please upload an Excel sheet (.xlsx or .xls).")
        
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    state.add_log(f"Excel file uploaded: {filename}. Parsing contents...", "info")
    
    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        sheet = wb.active
        
        # Read header row to detect columns
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return err_response("The uploaded Excel sheet is empty.")
            
        header = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
        
        # Helper to find column index based on keywords
        def find_column(keywords):
            for idx, h in enumerate(header):
                if any(k in h for k in keywords):
                    return idx
            return -1
            
        # Try to find LinkedIn URL column (required)
        url_idx = find_column(["linkedin", "url", "profile", "link", "href"])
        if url_idx == -1:
            # Fallback: scan all cells in first 3 rows to see if any contain linkedin.com/in
            found_idx = -1
            for row in rows[:5]:
                for idx, val in enumerate(row):
                    if val and "linkedin.com/in" in str(val):
                        found_idx = idx
                        break
                if found_idx != -1:
                    break
            url_idx = found_idx
            
        if url_idx == -1:
            return err_response("Could not find a LinkedIn URL column in your sheet. Please ensure it contains a column with 'LinkedIn' or profile URLs.")
            
        # Find optional fields
        first_name_idx = find_column(["first name", "firstname", "first"])
        last_name_idx = find_column(["last name", "lastname", "last"])
        full_name_idx = find_column(["name", "full name", "fullname", "contact"])
        company_idx = find_column(["company", "organization", "firm", "employer"])
        title_idx = find_column(["title", "role", "designation", "position"])
        
        contacts_added = 0
        existing_db = load_db()
        existing_urls = {c.get("profile_url", "").strip().split('?')[0].rstrip('/') for c in existing_db}
        
        new_contacts = []
        
        for row_idx, row in enumerate(rows[1:], start=2):
            if row_idx > len(rows):
                break
                
            # Fetch URL
            url_val = row[url_idx] if url_idx < len(row) else None
            if not url_val:
                continue
                
            url = str(url_val).strip()
            if "linkedin.com/" not in url:
                # If they just gave a username, let's construct the URL
                if url.isalnum():
                    url = f"https://www.linkedin.com/in/{url}"
                else:
                    continue # Skip invalid URL
                    
            # Normalize URL for duplicate checks
            norm_url = url.split('?')[0].rstrip('/')
            if norm_url in existing_urls:
                continue # Skip duplicates
                
            # Extract names
            first_name = ""
            last_name = ""
            full_name = ""
            
            if first_name_idx != -1 and first_name_idx < len(row) and row[first_name_idx]:
                first_name = str(row[first_name_idx]).strip()
            if last_name_idx != -1 and last_name_idx < len(row) and row[last_name_idx]:
                last_name = str(row[last_name_idx]).strip()
            if full_name_idx != -1 and full_name_idx < len(row) and row[full_name_idx]:
                full_name = str(row[full_name_idx]).strip()
                
            if not full_name:
                if first_name or last_name:
                    full_name = f"{first_name} {last_name}".strip()
                else:
                    # Guess name from profile URL username part
                    username = url.split("/in/")[-1].split("/")[0].replace("-", " ")
                    full_name = username.title()
                    
            if not first_name and full_name:
                parts = full_name.split()
                first_name = parts[0] if parts else ""
                last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                
            # Extract company and title
            company = ""
            title = ""
            if company_idx != -1 and company_idx < len(row) and row[company_idx]:
                company = str(row[company_idx]).strip()
            if title_idx != -1 and title_idx < len(row) and row[title_idx]:
                title = str(row[title_idx]).strip()
                
            new_contact = {
                "name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "profile_url": url,
                "company": company,
                "title": title,
                "status": "Not Started",
                "date_sent": None,
                "date_accepted": None,
                "logs": None
            }
            new_contacts.append(new_contact)
            existing_urls.add(norm_url)
            contacts_added += 1
            
        # Merge and save
        merged_db = existing_db + new_contacts
        save_db(merged_db)
        
        state.add_log(f"Successfully processed Excel. Added {contacts_added} new profiles to the list.", "success")
        
        # Clean up temporary uploaded file
        try:
            os.remove(filepath)
        except:
            pass
            
        return jsonify({
            "status": "success",
            "message": f"Successfully loaded {contacts_added} profiles from Excel.",
            "added_count": contacts_added
        })
        
    except Exception as e:
        state.add_log(f"Error parsing uploaded Excel file: {str(e)}", "error")
        return err_response(f"Failed to process Excel file: {str(e)}")

if __name__ == "__main__":
    # Create empty database.json if not present
    if not os.path.exists(DB_PATH):
        save_db([])
    else:
        # Migrate "Accepted" to "Connected"
        try:
            db_data = load_db()
            migrated = False
            for contact in db_data:
                if contact.get("status") == "Accepted":
                    contact["status"] = "Connected"
                    migrated = True
            if migrated:
                save_db(db_data)
                print("[INFO] Migrated database statuses from 'Accepted' to 'Connected'.")
        except Exception as e:
            print(f"[ERROR] Database migration failed: {str(e)}")
        
    print("--------------------------------------------------")
    print("   LinkedIn Connection Automator Backend Active   ")
    print("--------------------------------------------------")
    app.run(host="0.0.0.0", port=5000, debug=False)
