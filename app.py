import os
import shutil
import zipfile
import tempfile
import requests
import threading
import json
import uuid  # <-- Added import
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_file, jsonify, abort
)
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect

# Get the absolute path for the directory where app.py is located
basedir = os.path.abspath(os.path.dirname(__file__))

# Define the directory where data (including the DB) will be stored.
DATA_DIR = os.path.join(basedir, 'data') # This is now an absolute path
DB_NAME = 'database.db'
DB_PATH = os.path.join(DATA_DIR, DB_NAME) # This is also an absolute path
os.makedirs(DATA_DIR, exist_ok=True) # Ensure data directory exists

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-key-for-flash-messages'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}' # This now points to an absolute path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
APP_VERSION = "v?.?.?" # Default if file is missing
try:
    version_file_path = os.path.join(basedir, '.version')
    with open(version_file_path, 'r') as f:
        APP_VERSION = f.read().strip() # .strip() removes any newlines
except FileNotFoundError:
    pass # Will use the default "v?.?.?"
except Exception as e:
    print(f"Warning: Could not read .version file: {e}")


db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*") # Initialize SocketIO

# --- GLOBAL STATE FOR ASYNC PULL ---
# We'll use this dictionary to track the pull status across requests
pull_status = {'status': 'idle', 'message': ''}
# A lock to make sure we don't have race conditions updating the status
pull_lock = threading.Lock()


# --- SQLAlchemy Models (Refactored for Stable Table + JSON) ---

class Instance(db.Model):
    """
    Stores the URLs of other app instances.
    Uses a JSON 'data' column for flexibility.
    """
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # The stable column that holds all attributes
    data = db.Column(db.JSON, default=dict, nullable=False)

    # Property helpers to allow templates to access instance.name / instance.url
    # transparently, while the actual data lives in the JSON blob.
    @property
    def name(self):
        return self.data.get('name', 'Unknown')

    @property
    def url(self):
        return self.data.get('url', '')



class Excalidraw(db.Model):
    """
    Stores Excalidraw drawings.
    Uses a JSON 'data' column for flexibility.
    Schema agnostic: all specific fields like name, directory, elements, etc. go into 'data'.
    """
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    data = db.Column(db.JSON, default=dict, nullable=False)

    @property
    def name(self):
        return self.data.get('name', 'Untitled')
    
    @property
    def directory(self):
        return self.data.get('directory', '/')

    @property
    def description(self):
         return self.data.get('description', '')

# --- Helper Function for Data Restore ---

def restore_data_from_zip(zip_path_or_file, db_handle):
    """
    Restores the data directory from a given zip file.
    This is a DESTRUCTIVE operation.
    It now works by moving *contents* to avoid Docker volume errors.
    """
    # 1. Define paths
    # We'll create a *temporary* backup dir, not rename the live one
    backup_dir = os.path.join(basedir, 'data_temp_backup')
    # Create a unique temporary directory for the new data
    extract_dir = tempfile.mkdtemp(prefix='data_new_')

    # 2. Try to extract the new data *first*
    try:
        with zipfile.ZipFile(zip_path_or_file, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
    except Exception as e:
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        return False, f"Failed to extract new data zip: {e}"

    # 3. --- MODIFIED "ATOMIC SWAP" ---
    # We move *contents* to avoid "Device busy" on volume mounts.
    try:
        # 3a. Close all DB connections
        if db_handle:
            db_handle.session.remove()
            db_handle.engine.dispose()
        
        # 3b. Ensure temp backup dir is clean and ready
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        os.makedirs(backup_dir)

        # 3c. Move *contents* of current data to the temp backup
        # This leaves DATA_DIR (the volume) empty
        current_data_files = os.listdir(DATA_DIR)
        for item in current_data_files:
            shutil.move(os.path.join(DATA_DIR, item), backup_dir)
        
        # 3d. Move *contents* of new extracted data into DATA_DIR
        for item in os.listdir(extract_dir):
            shutil.move(os.path.join(extract_dir, item), DATA_DIR)

        # 3e. Success! We can now safely remove the temp backup.
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
            
        return True, "Data restored successfully! The app is using the new data."

    except Exception as e:
        # 4. FAILED! Attempt to restore the backup.
        try:
            # 4a. Remove any partially-moved new data from DATA_DIR
            for item in os.listdir(DATA_DIR):
                item_path = os.path.join(DATA_DIR, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
            
            # 4b. Restore the old backup from temp dir
            if os.path.exists(backup_dir):
                for item in os.listdir(backup_dir):
                    shutil.move(os.path.join(backup_dir, item), DATA_DIR)
                shutil.rmtree(backup_dir) # Clean up temp backup
                
        except Exception as restore_e:
             return False, f"CRITICAL: Failed to restore data ({e}) AND failed to restore backup ({restore_e}). App may be broken."
        
        return False, f"Failed to swap data contents: {e}. Original data has been preserved."
    
    finally:
        # 5. Final cleanup:
        # Remove the temporary extraction directory
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        
        # 6. Just in case: if restore failed badly, clean up temp backup
        if os.path.exists(backup_dir):
            print(f"Warning: Cleaning up leftover temp backup dir: {backup_dir}")
            shutil.rmtree(backup_dir)


@app.context_processor
def inject_global_data():
    """Makes 'all_instances' and 'app_version' available to all templates."""
    try:
        all_instances = Instance.query.all()
    except Exception:
        # This can happen if the DB isn't created yet
        all_instances = []
    # Add the app_version to the dictionary
    return dict(all_instances=all_instances, app_version=APP_VERSION)


# --- Main App Routes ---

@app.route('/')
def index():
    """Redirect to Excalidraw list."""
    return redirect(url_for('excalidraw_list'))

# --- Data Management Routes ---

@app.route('/export-data')
def export_data():
    """Creates a zip archive of the DATA_DIR and sends it for download."""
    try:
        # Create a zip file in a temporary location
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_name = 'data_export'
            zip_path = os.path.join(tmpdir, zip_name)
            
            # Use shutil.make_archive to zip the *contents* of DATA_DIR
            shutil.make_archive(
                base_name=zip_path,
                format='zip',
                root_dir=DATA_DIR  # The directory to zip
            )
            
            # Send the file
            return send_file(
                f"{zip_path}.zip",
                as_attachment=True,
                download_name='data_export.zip'
            )
    except Exception as e:
        flash(f'Error exporting data: {e}', 'error')
        return redirect(url_for('index'))

@app.route('/import-data', methods=['POST'])
def import_data():
    """Handles the file upload from the 'Import' modal."""
    file = request.files.get('zip_file')
    
    # 1. Validate the file
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    if not file.filename.endswith('.zip'):
        flash('Invalid file type. Please upload a .zip file.', 'error')
        return redirect(url_for('index'))

    # 2. Use the helper to restore data
    # We pass the 'file' object AND the 'db' object
    success, message = restore_data_from_zip(file, db) # <-- THIS LINE IS NOW FIXED
    
    flash(message, 'success' if success else 'error')
    
    # Note: Replacing the DB file while the app is running can be unstable.
    # A full restart is the safest way to ensure the new DB is loaded.
    if success:
        flash("It's recommended to restart the application to ensure changes are loaded.", "info")
        
    return redirect(url_for('index'))


# --- Excalidraw Routes ---

@app.route('/excalidraw-list')
def excalidraw_list():
    """Landing page for Excalidraw drawings."""
    drawings = Excalidraw.query.all()
    # No grouping, just pass the flat list
    return render_template('excalidraw_landing.html', drawings=drawings)

@app.route('/excalidraw/create', methods=['POST'])
def create_excalidraw():
    """Creates a new Excalidraw drawing."""
    name = request.form.get('name', 'Untitled')
    # Use root directory by default for all drawings since we are flat listing
    directory = '/'
        
    try:
        new_drawing = Excalidraw(data={'name': name, 'directory': directory, 'elements': [], 'appState': {}, 'files': {}})
        db.session.add(new_drawing)
        db.session.commit()
        flash('Drawing created!', 'success')
        return redirect(url_for('view_excalidraw', id=new_drawing.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating drawing: {e}', 'error')
        return redirect(url_for('excalidraw_list'))



@app.route('/excalidraw/<id>')
def view_excalidraw(id):
    """View/Edit Excalidraw drawing."""
    drawing = db.get_or_404(Excalidraw, id)
    return render_template('excalidraw.html', drawing=drawing)

@app.route('/excalidraw/<id>/readonly')
def view_excalidraw_readonly(id):
    """Read-only view of Excalidraw drawing."""
    drawing = db.get_or_404(Excalidraw, id)
    return render_template('excalidraw_readonly.html', drawing=drawing)

@app.route('/api/excalidraw/<id>', methods=['GET'])
def get_excalidraw_data(id):
    """API to get drawing data."""
    drawing = db.get_or_404(Excalidraw, id)
    return jsonify(drawing.data)

@app.route('/api/excalidraw/<id>', methods=['POST'])
def save_excalidraw_data(id):
    """API to save drawing data."""
    drawing = db.get_or_404(Excalidraw, id)
    try:
        json_data = request.json
        # Merge new data into existing data, preserving name/directory if not provided (though save usually sends full state)
        # We need to be careful not to overwrite name/directory if the client doesn't send them, 
        # but the client usually sends 'elements', 'appState', 'files'.
        
        current_data = drawing.data.copy()
        
        # Update fields that are sent
        if 'elements' in json_data:
            current_data['elements'] = json_data['elements']
        if 'appState' in json_data:
            current_data['appState'] = json_data['appState']
        if 'files' in json_data:
            current_data['files'] = json_data['files']
            
        # If the client sends name updates etc (optional future proofing)
        if 'name' in json_data:
            current_data['name'] = json_data['name']
            
        drawing.data = current_data
        
        # Explicitly mark the field as modified because it's a JSON type
        # (SQLAlchemy often detects this, but explicit flag is safer for mutations of mutable objects)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(drawing, "data")
        
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# --- Instance & Pull Routes ---

@app.route('/add-instance', methods=['POST'])
def add_instance():
    """Adds a new remote instance to the database."""
    name = request.form.get('name')
    url = request.form.get('url') # Gets 'http://10.0.0.5:5000'
    
    if not name or not url:
        flash('Name and URL are required.', 'error')
        return redirect(url_for('index'))
    
    # Clean up the URL
    url = url.rstrip('/')

    try:
        # MANUAL UNIQUENESS CHECK:
        # Since we are using a JSON column, we don't have a strict SQL unique constraint.
        # We must check logic manually.
        all_instances = Instance.query.all()
        for inst in all_instances:
            if inst.data.get('url') == url:
                 flash(f'Error: An instance with URL "{url}" already exists.', 'error')
                 return redirect(url_for('index'))

        # UPDATED: Save to 'data' JSON field
        new_instance = Instance(data={'name': name, 'url': url})
        db.session.add(new_instance)
        db.session.commit()
        flash('Instance added.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding instance: {e}', 'error')
            
    return redirect(url_for('index'))

@app.route('/delete-instance/<instance_id>', methods=['POST'])
def delete_instance(instance_id):
    """Deletes an instance from the database."""
    instance = db.get_or_404(Instance, instance_id)
    try:
        # We capture the name before deletion for the flash message
        # access via property still works
        inst_name = instance.name 
        db.session.delete(instance)
        db.session.commit()
        flash(f'Instance "{inst_name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting instance: {e}', 'error')
    return redirect(url_for('index'))


def _run_pull_task(app_instance, instance_id):
    """
    This function runs in a separate thread to perform the data pull.
    It updates the global 'pull_status' variable.
    """
    global pull_status
    
    # Threads need their own app context to use 'db' or other Flask extensions
    with app_instance.app_context():
        tmp_zip_path = None
        try:
            instance = db.get_or_404(Instance, instance_id)
            # Property access makes this transparent
            remote_export_url = f"{instance.url}/export-data"
            
            # 1. Update status: Downloading
            with pull_lock:
                pull_status = {'status': 'running', 'message': f'Attempting to pull from {instance.name}...'}
            
            response = requests.get(remote_export_url, timeout=60) 
            response.raise_for_status()

            if 'application/zip' not in response.headers.get('Content-Type', ''):
                raise Exception(f'Error: Remote instance ({instance.name}) did not return a zip file.')
            
            # 2. Update status: Saving
            with pull_lock:
                pull_status = {'status': 'running', 'message': 'Download complete. Saving to temporary file...'}
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
                tmp_zip.write(response.content)
                tmp_zip_path = tmp_zip.name

            # 3. Update status: Restoring
            with pull_lock:
                pull_status = {'status': 'running', 'message': 'Restoring data from file...'}
            
            # --- MODIFIED ---
            # Pass the zip path AND the 'db' object to the restore function.
            # It needs the 'db' object to control the connections.
            success, message = restore_data_from_zip(tmp_zip_path, db)
            # --- END MODIFIED ---

            # 4. Update status: Done
            if success:
                with pull_lock:
                    pull_status = {
                        'status': 'success',
                        'message': f"{message} It's recommended to restart the application to ensure changes are loaded."
                    }
            else:
                raise Exception(message)

        except requests.exceptions.RequestException as e:
            with pull_lock:
                # instace.name property access
                pull_status = {'status': 'error', 'message': f'Failed to connect or download: {e}'}
        except Exception as e:
            with pull_lock:
                pull_status = {'status': 'error', 'message': f'An unexpected error occurred: {e}'}
        finally:
            # 5. Clean up the temporary zip file
            if tmp_zip_path and os.path.exists(tmp_zip_path):
                os.remove(tmp_zip_path)



# --- MODIFIED: This route now *starts* the pull task ---
@app.route('/start-pull/<instance_id>', methods=['POST'])
def start_pull(instance_id):
    """
    Starts the asynchronous pull task and redirects to the status page.
    """
    global pull_status
    with pull_lock:
        # Check if a pull is already running
        if pull_status['status'] == 'running':
            flash('A pull operation is already in progress.', 'warning')
            # Redirect to the status page so they can see it
            return redirect(url_for('pull_status_page')) 
        
        # Set status to 'running' and start the new thread
        # It's OK to start a new pull if status is 'idle', 'success', or 'error'
        pull_status = {'status': 'running', 'message': 'Initializing pull...'}
        
        # We pass the 'app' object itself to the thread
        thread = threading.Thread(target=_run_pull_task, args=(app, instance_id))
        thread.daemon = True # Allows the app to exit even if threads are running
        thread.start()
    
    # Immediately redirect to the status page
    return redirect(url_for('pull_status_page'))


# --- NEW: Status Page and API Routes ---
@app.route('/pull-status')
def pull_status_page():
    """
    Renders the page that will poll for the pull status.
    """
    return render_template('pull_status.html')

@app.route('/api/pull-status')
def api_pull_status():
    """
    Returns the current pull status as JSON for the status page to fetch.
    """
    global pull_status
    with pull_lock:
        # Return a *copy* of the status dictionary
        status_copy = pull_status.copy()
    return jsonify(status_copy)


# --- SocketIO Events ---

# Room ID is just the drawing ID (stringified)
# Participants: { room_id: { sid: user_name } }
participants = {}

@socketio.on('join')
def on_join(data):
    room = str(data['room'])
    name = data['name']
    
    join_room(room)
    
    if room not in participants:
        participants[room] = {}
    participants[room][request.sid] = name
    
    # Broadcast updated participant list
    emit('room_users', list(participants[room].values()), room=room)
    print(f"User {name} joined room {room}")

@socketio.on('disconnect')
def on_disconnect():
    # Find which room this SID was in and remove them
    for room, users in participants.items():
        if request.sid in users:
            name = users.pop(request.sid)
            leave_room(room)
            emit('room_users', list(users.values()), room=room)
            print(f"User {name} left room {room}")
            # If room empty, clean up? (optional, maybe keep it simple for now)
            break

@socketio.on('update_scene')
def on_update_scene(data):
    """
    data = {
        'room': room_id,
        'elements': ...,
        'appState': ...
    }
    """
    room = str(data['room'])
    # Broadcast to everyone else in the room
    emit('update_scene', data, room=room, include_self=False)

@socketio.on('cursor_move')
def on_cursor_move(data):
    """
    data = {
        'room': room_id,
        'username': name,
        'x': x,
        'y': y
    }
    """
    room = str(data['room'])
    emit('cursor_move', data, room=room, include_self=False)


# --- 3. SEEDING LOGIC ---

def seed_nodes():
    """Reads nodes from nodes.json and saves them to the DB if empty."""
    nodes_file = os.path.join(basedir, 'nodes.json')
    
    if not os.path.exists(nodes_file):
        print(f"No nodes.json found at {nodes_file}, skipping seeding.")
        return

    try:
        # Check if the Instance table is empty
        # We use .first() as a lightweight check
        if Instance.query.first() is None:
            with open(nodes_file, 'r') as f:
                predefined_nodes = json.load(f)
            
            print(f"Seeding {len(predefined_nodes)} instances from nodes.json...")
            
            count = 0
            for node_data in predefined_nodes:
                name = node_data.get('name')
                url = node_data.get('url')
                
                if name and url:
                    url = url.rstrip('/')
                    # Create using the JSON column 'data'
                    # We don't strictly check for duplicates here because the table is empty
                    new_instance = Instance(data={'name': name, 'url': url})
                    db.session.add(new_instance)
                    count += 1
            
            if count > 0:
                db.session.commit()
                print("Seeding complete.")
            else:
                print("No valid nodes found in nodes.json.")
        else:
             # Logic for when table is not empty
             print("Instance table not empty. Skipping seeding.")

    except Exception as e:
        print(f"Error seeding nodes: {e}")
        db.session.rollback()


# --- STARTUP BLOCK ---
if __name__ == '__main__':
    with app.app_context():
        # 1. Create all tables (safe, won't overwrite existing tables)
        db.create_all()

        # 2. Seed nodes from JSON
        seed_nodes()

    # Host='0.0.0.0' makes it accessible on your network
    # app.run(debug=True, host='0.0.0.0', port=5000)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)