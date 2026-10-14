
from flask import (
    Flask, request, redirect, render_template_string,
    url_for, session, send_from_directory
)
import sqlite3
from pathlib import Path
from werkzeug.utils import secure_filename
import uuid

try:
    from PIL import Image
except ImportError:
    Image = None

app = Flask(__name__)
app.secret_key = "smart-locality-demo-change-before-deployment"

DB_PATH = Path(__file__).with_name("locality.db")
UPLOAD_FOLDER = Path(__file__).with_name("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_SIZE


def validate_image_upload(uploaded_file, extension):
    """Reject files whose content is not a real, readable image."""
    try:
        uploaded_file.stream.seek(0)
        header = uploaded_file.stream.read(12)
        uploaded_file.stream.seek(0)

        # Check that the file's actual bytes match its extension.
        if extension == "png" and not header.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
            return False
        if extension in {"jpg", "jpeg"} and not header.startswith(b"\\xff\\xd8\\xff"):
            return False
        if extension == "gif" and not header.startswith((b"GIF87a", b"GIF89a")):
            return False
        if extension == "webp" and not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
            return False

        # Pillow verifies the image structure when installed, preventing
        # fake/corrupt files with a copied image extension from being accepted.
        if Image is not None:
            uploaded_file.stream.seek(0)
            with Image.open(uploaded_file.stream) as image:
                if image.format not in {
                    "PNG", "JPEG", "GIF", "WEBP"
                }:
                    return False
                image.verify()

        uploaded_file.stream.seek(0)
        return True
    except Exception:
        try:
            uploaded_file.stream.seek(0)
        except Exception:
            pass
        return False

# Demo credentials for local testing only
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "locality123"

CATEGORIES = [
    "Pothole", "Garbage", "Drainage",
    "Streetlight", "Water leakage",
    "Air Pollution", "Overflowing Dustbin", "Other"
]
STATUSES = ["Pending", "In Progress", "Resolved"]
PRIORITIES = ["Low", "Medium", "High"]


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending'
            )
        """)

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(complaints)"
            )
        }

        if "priority" not in columns:
            conn.execute("""
                ALTER TABLE complaints
                ADD COLUMN priority TEXT NOT NULL DEFAULT 'Medium'
            """)
            columns.add("priority")

        if "image_path" not in columns:
            conn.execute("""
                ALTER TABLE complaints
                ADD COLUMN image_path TEXT
            """)
            columns.add("image_path")

        if "latitude" not in columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN latitude REAL")
            columns.add("latitude")

        if "longitude" not in columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN longitude REAL")
            columns.add("longitude")

        # Preserve existing rows while adding a timestamp for age-based alerts.
        if "created_at" not in columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN created_at TEXT")
            conn.execute(
                "UPDATE complaints SET created_at = datetime('now') WHERE created_at IS NULL"
            )
            columns.add("created_at")

        # In-app notifications are stored separately; existing complaints are untouched.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                is_read INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (complaint_id) REFERENCES complaints(id)
            )
        """)


HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Locality</title>
<style>
* { box-sizing: border-box; }
body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f1f5f9;
    color: #1e293b;
}
header {
    background: #166534;
    color: white;
    text-align: center;
    padding: 25px 15px;
}
header h1 { margin-top: 0; }
nav { margin-top: 18px; }
nav a {
    color: white;
    text-decoration: none;
    margin: 8px;
    font-weight: bold;
}
main { max-width: 950px; margin: 28px auto; padding: 0 16px; }
.card {
    background: white;
    padding: 24px;
    margin-bottom: 22px;
    border-radius: 12px;
    box-shadow: 0 3px 12px #0000000c;
}
label { display: block; margin-top: 14px; font-weight: bold; }
input, select, textarea {
    display: block;
    width: 100%;
    padding: 12px;
    margin-top: 7px;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    font: inherit;
}
textarea { min-height: 100px; }
button, .button {
    display: inline-block;
    margin-top: 16px;
    padding: 12px 18px;
    background: #166534;
    color: white;
    border: 0;
    border-radius: 6px;
    cursor: pointer;
    text-decoration: none;
}
button:hover, .button:hover { background: #14532d; }
.issue { border-top: 1px solid #e2e8f0; padding: 16px 0; }
.status { color: #166534; font-weight: bold; }
.notice { background: #dcfce7; padding: 14px; border-radius: 6px; }
.error { background: #fee2e2; padding: 14px; border-radius: 6px; }
.muted { color: #64748b; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td {
    padding: 12px;
    border-bottom: 1px solid #e2e8f0;
    text-align: left;
    vertical-align: top;
}
footer { text-align: center; padding: 20px; color: #64748b; }
</style>
</head>
<body>

<header>
    <h1>Smart Locality</h1>
    <p>Report local problems. Help improve your community.</p>
    <nav>
        <a href="{{ url_for('home') }}">Report Issue</a>
        <a href="{{ url_for('track') }}">Track Complaint</a>
        <a href="{{ url_for('admin') }}">Admin Dashboard</a>
        <a href="{{ url_for('sensors') }}">IoT Sensors</a>
        <a href="{{ url_for('complaint_map') }}">Complaint Map</a>
    </nav>
</header>

<main>
    {% if message %}
        <div class="card notice">{{ message }}</div>
    {% endif %}
    {% if error %}
        <div class="card error">{{ error }}</div>
    {% endif %}

    {% if page == "home" %}
    <div class="card">
        <h2>Report a Local Issue</h2>
        <form method="post" action="{{ url_for('home') }}" enctype="multipart/form-data">
            <label>Your name</label>
            <input name="name" maxlength="80" required>

            <label>Issue category</label>
            <select name="category" required>
                {% for c in categories %}
                <option value="{{ c }}">{{ c }}</option>
                {% endfor %}
            </select>

            <label>Locality or address</label>
            <input name="location" maxlength="200" required>

            <label>Pin the exact issue location on the map (optional)</label>
            <p class="muted">Click the map to place a marker. This helps show the complaint on the dashboard map.</p>
            <div id="report-map" style="height:300px;border-radius:8px;border:1px solid #cbd5e1;"></div>
            <input type="hidden" name="latitude" id="latitude">
            <input type="hidden" name="longitude" id="longitude">
            <button type="button" id="clear-map-pin" style="background:#475569;">Clear map pin</button>

            <label>Describe the problem</label>
            <textarea name="description" maxlength="2000" required></textarea>

            <label for="complaint_image">Upload an issue photo (optional)</label>
            <input type="file" id="complaint_image" name="complaint_image"
                   accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp">
            <p class="muted">Accepted images: PNG, JPG, JPEG, GIF, WEBP. Maximum 5 MB.</p>

            <button type="submit">Submit Complaint</button>
        </form>
    </div>

    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
    (function () {
        const mapElement = document.getElementById("report-map");
        if (!mapElement || typeof L === "undefined") return;
        const map = L.map(mapElement).setView([20.5937, 78.9629], 5);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);
        let marker = null;
        const latInput = document.getElementById("latitude");
        const lonInput = document.getElementById("longitude");
        function setPin(latlng) {
            if (marker) marker.setLatLng(latlng);
            else marker = L.marker(latlng).addTo(map);
            latInput.value = latlng.lat.toFixed(7);
            lonInput.value = latlng.lng.toFixed(7);
            marker.bindPopup("Selected complaint location").openPopup();
        }
        map.on("click", function (event) { setPin(event.latlng); });
        document.getElementById("clear-map-pin").addEventListener("click", function () {
            if (marker) map.removeLayer(marker);
            marker = null;
            latInput.value = "";
            lonInput.value = "";
        });
        setTimeout(function () { map.invalidateSize(); }, 200);
    })();
    </script>

    <div class="card">
        <h2>Recent Complaints ({{ complaints|length }})</h2>
        {% for c in complaints %}
        <div class="issue">
            <h3>Complaint #{{ c['id'] }} — {{ c['category'] }}</h3>
            <p><b>Locality:</b> {{ c['location'] }}</p>
            <p>{{ c['description'] }}</p>
            {% if c['image_path'] %}
            <p><b>Issue photo:</b><br><a href="{{ url_for('uploaded_file', filename=c['image_path']) }}" target="_blank" rel="noopener"><img src="{{ url_for('uploaded_file', filename=c['image_path']) }}" alt="Photo for complaint #{{ c['id'] }}" style="max-width:100%;max-height:260px;border-radius:8px;margin-top:8px;"></a></p>
            {% endif %}
            <p>Status: <span class="status">{{ c['status'] }}</span></p>
            <p>Priority: {{ c['priority'] }}</p>
            <a href="{{ url_for('track', id=c['id']) }}">Track complaint</a>
        </div>
        {% else %}
        <p class="muted">No complaints have been submitted yet.</p>
        {% endfor %}
    </div>

    {% elif page == "track" %}
    <div class="card">
        <h2>Track Your Complaint</h2>
        <form method="get" action="{{ url_for('track') }}">
            <label>Complaint ID</label>
            <input type="number" name="id" min="1"
                   value="{{ search_id or '' }}" required>
            <button type="submit">Track Complaint</button>
        </form>

        {% if complaint %}
        <div class="issue">
            <h3>Complaint #{{ complaint['id'] }}</h3>
            <p><b>Category:</b> {{ complaint['category'] }}</p>
            <p><b>Locality:</b> {{ complaint['location'] }}</p>
            <p><b>Description:</b> {{ complaint['description'] }}</p>
            <p><b>Status:</b>
                <span class="status">{{ complaint['status'] }}</span>
            </p>
            <p><b>Priority:</b> {{ complaint['priority'] }}</p>
            {% if complaint['image_path'] %}
            <p><b>Issue photo:</b><br><a href="{{ url_for('uploaded_file', filename=complaint['image_path']) }}" target="_blank" rel="noopener"><img src="{{ url_for('uploaded_file', filename=complaint['image_path']) }}" alt="Photo for complaint #{{ complaint['id'] }}" style="max-width:100%;max-height:300px;border-radius:8px;margin-top:8px;"></a></p>
            {% endif %}
        </div>
        <div class="card">
            <h3>🔔 Status Notifications</h3>
            <p class="muted">Check here for updates posted by the administrator for this complaint.</p>
            {% for n in notifications %}
            <div class="issue">
                <p><b>{{ n['message'] }}</b></p>
                <p class="muted">{{ n['created_at'] }}</p>
            </div>
            {% else %}
            <p>No status notifications yet. Check again later using this complaint ID.</p>
            {% endfor %}
        </div>
        {% elif search_id %}
        <p>No complaint found with ID #{{ search_id }}.</p>
        {% endif %}
    </div>

    {% elif page == "login" %}
    <div class="card">
        <h2>Admin Login</h2>
        <form method="post" action="{{ url_for('login') }}">
            <label>Username</label>
            <input name="username" autocomplete="username" required>

            <label>Password</label>
            <input type="password" name="password"
                   autocomplete="current-password" required>

            <button type="submit">Login</button>
        </form>
        <p class="muted">Demo username: admin</p>
        <p class="muted">Demo password: locality123</p>
    </div>

    {% elif page == "admin" %}
    <div class="card">
        
    <h2>Admin Dashboard</h2>

    <style>
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
            margin: 20px 0;
        }
        .stat-card {
            padding: 20px;
            border-radius: 10px;
            background: #e0f2fe;
        }
        .stat-card h3 {
            margin: 0 0 10px;
            font-size: 16px;
        }
        .stat-number {
            font-size: 30px;
            font-weight: bold;
        }
        .stat-pending { background: #fef3c7; }
        .stat-progress { background: #dbeafe; }
        .stat-resolved { background: #dcfce7; }
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
            margin: 20px 0;
        }
        .chart-card {
            min-width: 0;
            padding: 18px;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #fff;
        }
        .chart-card canvas { width: 100% !important; max-height: 300px; }
        .alert-list { display: grid; gap: 10px; margin: 16px 0 24px; }
        .alert-item {
            padding: 14px;
            border-left: 5px solid #dc2626;
            border-radius: 6px;
            background: #fee2e2;
        }
        .alert-item.medium-age { border-left-color: #d97706; background: #fef3c7; }
        .priority-tag { font-weight: bold; }
        .filter-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            align-items: end;
            margin: 18px 0;
        }
        .filter-grid label { margin-top: 0; }
        .filter-actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .filter-actions button, .filter-actions a { margin-top: 16px; }
        .filter-actions a { padding: 12px 18px; background: #e2e8f0; color: #1e293b; border-radius: 6px; text-decoration: none; }
        .results-note { margin: 12px 0 18px; color: #475569; }

        @media (max-width: 700px) {
            .filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 500px) {
            .filter-grid { grid-template-columns: 1fr; }
            .stats-grid { grid-template-columns: 1fr; }
            .charts-grid { grid-template-columns: 1fr; }
        }
    </style>

    <div class="stats-grid">
        <div class="stat-card">
            <h3>Total Complaints</h3>
            <div class="stat-number">{{ total }}</div>
        </div>

        <div class="stat-card stat-pending">
            <h3>Pending</h3>
            <div class="stat-number">{{ pending }}</div>
        </div>

        <div class="stat-card stat-progress">
            <h3>In Progress</h3>
            <div class="stat-number">{{ in_progress }}</div>
        </div>

        <div class="stat-card stat-resolved">
            <h3>Resolved</h3>
            <div class="stat-number">{{ resolved }}</div>
        </div>
    </div>

    <h3>Complaint Analytics</h3>
    <div class="charts-grid">
        <div class="chart-card">
            <h4>Complaints by Status</h4>
            <canvas id="statusChart" aria-label="Pie chart of complaints by status"></canvas>
        </div>
        <div class="chart-card">
            <h4>Complaints by Category</h4>
            <canvas id="categoryChart" aria-label="Bar chart of complaints by category"></canvas>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
    (function () {
        if (typeof Chart === "undefined") return;
        const statusLabels = {{ chart_status_labels|tojson }};
        const statusValues = {{ chart_status_values|tojson }};
        const categoryLabels = {{ chart_category_labels|tojson }};
        const categoryValues = {{ chart_category_values|tojson }};
        new Chart(document.getElementById("statusChart"), {
            type: "pie",
            data: { labels: statusLabels, datasets: [{ data: statusValues }] },
            options: { responsive: true, plugins: { legend: { position: "bottom" } } }
        });
        new Chart(document.getElementById("categoryChart"), {
            type: "bar",
            data: { labels: categoryLabels, datasets: [{ label: "Complaints", data: categoryValues }] },
            options: {
                responsive: true,
                scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                plugins: { legend: { display: false } }
            }
        });
    })();
    </script>

    <h3>Priority Alerts</h3>
    <p class="muted">High-priority open complaints and unresolved complaints older than 3 days are listed here.</p>
    <div class="alert-list">
        {% for alert in priority_alerts %}
          <div class="alert-item {% if alert['priority'] != 'High' %}medium-age{% endif %}">
            <b>Complaint #{{ alert['id'] }} — {{ alert['category'] }}</b>
            <p>{{ alert['location'] }} · <span class="priority-tag">{{ alert['priority'] }} priority</span> · {{ alert['status'] }}</p>
            <p>{{ alert['description'] }}</p>
            <p class="muted">Reported: {{ alert['created_at'] or 'Date unavailable' }}</p>
          </div>
        {% else %}
          <p class="notice">No urgent or overdue unresolved complaints right now.</p>
        {% endfor %}
    </div>

    <p>Manage complaints and monitor locality issues.</p>
    <a href="{{ url_for('logout') }}">Log out</a>

    <h3>Search and Filter Complaints</h3>
    <form method="get" action="{{ url_for('admin') }}">
        <div class="filter-grid">
            <div>
                <label for="q">Search</label>
                <input id="q" name="q" type="search" maxlength="200"
                       placeholder="ID, name, locality, description"
                       value="{{ search_text }}">
            </div>
            <div>
                <label for="category_filter">Category</label>
                <select id="category_filter" name="category">
                    <option value="">All categories</option>
                    {% for category_option in categories %}
                    <option value="{{ category_option }}"
                    {% if filter_category == category_option %}selected{% endif %}>
                        {{ category_option }}
                    </option>
                    {% endfor %}
                </select>
            </div>
            <div>
                <label for="status_filter">Status</label>
                <select id="status_filter" name="status">
                    <option value="">All statuses</option>
                    {% for status_option in statuses %}
                    <option value="{{ status_option }}"
                    {% if filter_status == status_option %}selected{% endif %}>
                        {{ status_option }}
                    </option>
                    {% endfor %}
                </select>
            </div>
            <div>
                <label for="priority_filter">Priority</label>
                <select id="priority_filter" name="priority">
                    <option value="">All priorities</option>
                    {% for priority_option in priorities %}
                    <option value="{{ priority_option }}"
                    {% if filter_priority == priority_option %}selected{% endif %}>
                        {{ priority_option }}
                    </option>
                    {% endfor %}
                </select>
            </div>
        </div>
        <div class="filter-actions">
            <button type="submit">Apply Search and Filters</button>
            <a href="{{ url_for('admin') }}">Clear Filters</a>
        </div>
    </form>
    <p class="results-note">Showing {{ complaints|length }} matching complaint(s). Summary cards above show all complaints.</p>

        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Complaint</th>
                    <th>Details</th>
                    <th>Manage</th>
                </tr>
            </thead>
            <tbody>
            {% for c in complaints %}
                <tr>
                    <td>
                        #{{ c['id'] }}<br>
                        {{ c['category'] }}<br>
                        <b>{{ c['status'] }}</b>
                    </td>
                    <td>
                        {{ c['name'] }}<br>
                        {{ c['location'] }}<br>
                        {{ c['description'] }}<br>
                        Priority: {{ c['priority'] }}<br>
                        {% if c['image_path'] %}
                        <b>Issue photo:</b><br><a href="{{ url_for('uploaded_file', filename=c['image_path']) }}" target="_blank" rel="noopener"><img src="{{ url_for('uploaded_file', filename=c['image_path']) }}" alt="Photo for complaint #{{ c['id'] }}" style="max-width:180px;max-height:140px;border-radius:6px;margin-top:6px;"></a>
                        {% else %}<span class="muted">No photo uploaded</span>{% endif %}
                    </td>
                    <td>
                        <form method="post"
                              action="{{ url_for('update_complaint', complaint_id=c['id']) }}">
                            <label>Status</label>
                            <select name="status">
                                {% for s in statuses %}
                                <option value="{{ s }}"
                                {% if c['status'] == s %}selected{% endif %}>
                                    {{ s }}
                                </option>
                                {% endfor %}
                            </select>

                            <label>Priority</label>
                            <select name="priority">
                                {% for p in priorities %}
                                <option value="{{ p }}"
                                {% if c['priority'] == p %}selected{% endif %}>
                                    {{ p }}
                                </option>
                                {% endfor %}
                            </select>

                            <button type="submit">Save Changes</button>
                        </form>
                    </td>
                </tr>
            {% else %}
                <tr><td colspan="3">No complaints found.</td></tr>
            {% endfor %}
            </tbody>
        </table>
        </div>
    </div>

    {% elif page == "map" %}
    <div class="card">
        <h2>Interactive Complaint Map</h2>
        <p class="muted">Use the filters to explore pinned complaints. Older complaints remain saved and appear in the unpinned list below.</p>
        <div class="filter-grid" style="grid-template-columns:repeat(3,minmax(0,1fr));">
            <div>
                <label for="map-category">Category</label>
                <select id="map-category">
                    <option value="">All categories</option>
                    {% for category_option in categories %}<option value="{{ category_option }}">{{ category_option }}</option>{% endfor %}
                </select>
            </div>
            <div>
                <label for="map-status">Status</label>
                <select id="map-status">
                    <option value="">All statuses</option>
                    {% for status_option in statuses %}<option value="{{ status_option }}">{{ status_option }}</option>{% endfor %}
                </select>
            </div>
            <div>
                <label for="map-priority">Priority</label>
                <select id="map-priority">
                    <option value="">All priorities</option>
                    {% for priority_option in priorities %}<option value="{{ priority_option }}">{{ priority_option }}</option>{% endfor %}
                </select>
            </div>
        </div>
        <div id="complaint-map" style="height:500px;border-radius:8px;border:1px solid #cbd5e1;"></div>
        <p id="map-summary" class="muted"></p>
    </div>
    <div class="card">
        <h3>Complaints without a map pin ({{ unpinned|length }})</h3>
        {% for c in unpinned %}
          <div class="issue">
            <b>Complaint #{{ c['id'] }} — {{ c['category'] }}</b>
            <p>{{ c['location'] }} · {{ c['status'] }} · Priority: {{ c['priority'] }}</p>
          </div>
        {% else %}
          <p class="muted">All complaints have map pins.</p>
        {% endfor %}
    </div>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
    (function () {
        const data = {{ mapped_complaints|tojson }};
        const element = document.getElementById("complaint-map");
        if (!element || typeof L === "undefined") {
            document.getElementById("map-summary").textContent = "Map library could not load. Check your internet connection.";
            return;
        }
        const map = L.map(element).setView([20.5937, 78.9629], 5);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);
        let markerLayers = [];
        function safeText(value) {
            return String(value).replace(/[&<>"']/g, function (char) {
                return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char];
            });
        }
        function renderMarkers() {
            markerLayers.forEach(function (marker) { map.removeLayer(marker); });
            markerLayers = [];
            const category = document.getElementById("map-category").value;
            const status = document.getElementById("map-status").value;
            const priority = document.getElementById("map-priority").value;
            const visible = data.filter(function (c) {
                return (!category || c.category === category) &&
                    (!status || c.status === status) &&
                    (!priority || c.priority === priority);
            });
            const bounds = [];
            visible.forEach(function (c) {
                const color = c.priority === "High" ? "#dc2626" :
                    (c.status === "Resolved" ? "#16a34a" : "#2563eb");
                const marker = L.circleMarker([c.latitude, c.longitude], {
                    radius: 9, color: color, fillColor: color, fillOpacity: 0.8, weight: 2
                }).addTo(map);
                const popup = "<b>Complaint #" + safeText(c.id) + " — " + safeText(c.category) +
                    "</b><br>" + safeText(c.location) + "<br>" + safeText(c.description || "") +
                    "<br>Status: " + safeText(c.status) +
                    "<br>Priority: " + safeText(c.priority);
                marker.bindPopup(popup);
                markerLayers.push(marker);
                bounds.push([c.latitude, c.longitude]);
            });
            if (bounds.length) map.fitBounds(bounds, {padding: [30, 30], maxZoom: 15});
            document.getElementById("map-summary").textContent =
                visible.length + " of " + data.length + " pinned complaint(s) match the filters. Red = high priority; green = resolved; blue = other.";
        }
        ["map-category", "map-status", "map-priority"].forEach(function (id) {
            document.getElementById(id).addEventListener("change", renderMarkers);
        });
        renderMarkers();
        setTimeout(function () { map.invalidateSize(); }, 200);
    })();
    </script>

    {% elif page == "sensors" %}
    <style>
        .sensor-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
            margin: 20px 0;
        }
        .sensor-card {
            padding: 20px;
            border-radius: 10px;
            background: #e0f2fe;
        }
        .sensor-alert { background: #fef3c7; }
        .sensor-number { font-size: 30px; font-weight: bold; }
        @media (max-width: 500px) {
            .sensor-grid { grid-template-columns: 1fr; }
        }
    </style>
    <div class="card">
        <h2>IoT Sensor Monitoring</h2>
        <p class="muted">
            These are simulated readings for demonstration purposes, not live hardware data.
        </p>

        <div class="sensor-grid">
            <div class="sensor-card {% if air_value > 120 %}sensor-alert{% endif %}">
                <h3>Air Pollution Sensor</h3>
                <div class="sensor-number">{{ air_value }}</div>
                <p>Simulated air-quality index</p>
                {% if air_value > 120 %}
                <p><b>Alert: High pollution detected</b></p>
                {% else %}
                <p>Reading is within the demo threshold.</p>
                {% endif %}
            </div>

            <div class="sensor-card {% if bin_value > 80 %}sensor-alert{% endif %}">
                <h3>Smart Dustbin Sensor</h3>
                <div class="sensor-number">{{ bin_value }}%</div>
                <p>Simulated dustbin fill level</p>
                {% if bin_value > 80 %}
                <p><b>Alert: Dustbin is nearly full</b></p>
                {% else %}
                <p>Dustbin is below the demo threshold.</p>
                {% endif %}
            </div>
        </div>

        <form method="post" action="{{ url_for('sensors') }}">
            <button type="submit">Check Readings and Create Alerts</button>
        </form>

        <p class="muted">
            Press the button to generate a new set of readings. If a reading crosses
            its threshold, the system adds a high-priority complaint to the database.
            Refreshing this page alone does not create complaints.
        </p>
    </div>

    {% endif %}
</main>

<footer>Smart Locality Issue Reporting and Monitoring System</footer>
</body>
</html>
"""


def render_page(page, **kwargs):
    # Fix: build one context dictionary and merge route values.
    # This prevents duplicate keyword arguments such as 'complaint'.
    context = {
        "page": page,
        "message": request.args.get("message"),
        "error": None,
        "complaint": None,
        "complaints": [],
        "search_id": None,
        "search_text": "",
        "filter_category": "",
        "filter_status": "",
        "filter_priority": "",
        "categories": CATEGORIES,
        "statuses": STATUSES,
        "priorities": PRIORITIES,
        "mapped_complaints": [],
        "unpinned": [],
    }
    context.update(kwargs)
    return render_template_string(HTML, **context)




@app.errorhandler(413)
def upload_too_large(error):
    return render_page(
        "home",
        error="Upload rejected. The maximum image size is 5 MB.",
    ), 413

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()

        if not (
            name and location and description
            and category in CATEGORIES
        ):
            return render_page(
                "home", error="Please fill in all fields correctly."
            ), 400

        latitude_raw = request.form.get("latitude", "").strip()
        longitude_raw = request.form.get("longitude", "").strip()
        latitude = longitude = None
        if latitude_raw or longitude_raw:
            try:
                latitude = float(latitude_raw)
                longitude = float(longitude_raw)
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise ValueError
            except (TypeError, ValueError):
                return render_page(
                    "home", error="The map location is invalid. Please select the location again."
                ), 400

        image = request.files.get("complaint_image")
        image_filename = None
        if image and image.filename:
            original_name = secure_filename(image.filename)
            extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
            if extension not in ALLOWED_EXTENSIONS:
                return render_page(
                    "home",
                    error="Upload rejected. Please choose a PNG, JPG, JPEG, GIF, or WEBP image.",
                ), 400

            image.seek(0, 2)
            image_size = image.tell()
            image.seek(0)
            if image_size > MAX_IMAGE_SIZE:
                return render_page(
                    "home",
                    error="Upload rejected. The maximum image size is 5 MB.",
                ), 413

            if not validate_image_upload(image, extension):
                return render_page(
                    "home",
                    error="Upload rejected. This file is not a valid image. Please choose a genuine PNG, JPG, JPEG, GIF, or WEBP file.",
                ), 400

            image_filename = f"{uuid.uuid4().hex}.{extension}"
            image.save(UPLOAD_FOLDER / image_filename)

        try:
            with connect_db() as conn:
                cur = conn.execute(
                    """INSERT INTO complaints
                       (name, category, location, description, image_path, latitude, longitude, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (name, category, location, description, image_filename, latitude, longitude),
                )
                complaint_id = cur.lastrowid
        except Exception:
            if image_filename:
                (UPLOAD_FOLDER / image_filename).unlink(missing_ok=True)
            raise

        return redirect(url_for(
            "track",
            id=complaint_id,
            message=f"Complaint submitted successfully. Your ID is #{complaint_id}."
        ))

    with connect_db() as conn:
        complaints = conn.execute(
            "SELECT * FROM complaints ORDER BY id DESC"
        ).fetchall()

    return render_page("home", complaints=complaints)

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # Only serve files from the dedicated uploads directory.
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/map")
def complaint_map():
    with connect_db() as conn:
        mapped = conn.execute(
            """SELECT id, category, location, description, status, priority, latitude, longitude
               FROM complaints
               WHERE latitude IS NOT NULL AND longitude IS NOT NULL
               ORDER BY id DESC"""
        ).fetchall()
        unpinned = conn.execute(
            """SELECT id, category, location, status, priority
               FROM complaints
               WHERE latitude IS NULL OR longitude IS NULL
               ORDER BY id DESC"""
        ).fetchall()

    mapped_complaints = [
        {
            "id": row["id"],
            "category": row["category"],
            "location": row["location"],
            "description": row["description"],
            "status": row["status"],
            "priority": row["priority"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
        }
        for row in mapped
    ]
    return render_page(
        "map",
        mapped_complaints=mapped_complaints,
        unpinned=unpinned,
    )


@app.route("/sensors", methods=["GET", "POST"])
def sensors():
    import random

    air_value = random.randint(20, 180)
    bin_value = random.randint(10, 100)
    message = None

    if request.method == "POST":
        with connect_db() as conn:
            # Create at most one unresolved air-pollution sensor complaint.
            if air_value > 120:
                existing_air_complaint = conn.execute(
                    """
                    SELECT id FROM complaints
                    WHERE category = ?
                      AND name = ?
                      AND status != ?
                    LIMIT 1
                    """,
                    ("Air Pollution", "IoT Sensor", "Resolved"),
                ).fetchone()

                if existing_air_complaint is None:
                    conn.execute(
                        """
                        INSERT INTO complaints
                            (name, category, location, description, priority, created_at)
                        VALUES (?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (
                            "IoT Sensor",
                            "Air Pollution",
                            "Smart Locality Sensor Zone",
                            f"High simulated air pollution reading: {air_value}",
                            "High",
                        ),
                    )

            # Create at most one unresolved overflowing-dustbin complaint.
            if bin_value > 80:
                existing_bin_complaint = conn.execute(
                    """
                    SELECT id FROM complaints
                    WHERE category = ?
                      AND name = ?
                      AND status != ?
                    LIMIT 1
                    """,
                    ("Overflowing Dustbin", "IoT Sensor", "Resolved"),
                ).fetchone()

                if existing_bin_complaint is None:
                    conn.execute(
                        """
                        INSERT INTO complaints
                            (name, category, location, description, priority, created_at)
                        VALUES (?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (
                            "IoT Sensor",
                            "Overflowing Dustbin",
                            "Smart Locality Waste Bin",
                            f"Dustbin is {bin_value}% full according to simulated sensor",
                            "High",
                        ),
                    )

        message = "Sensor readings checked. Any detected issues were reported."

    return render_page(
        "sensors",
        message=message,
        air_value=air_value,
        bin_value=bin_value,
    )


@app.route("/track")
def track():
    search_id = request.args.get("id", default=None, type=int)
    complaint = None
    notifications = []

    if search_id and search_id > 0:
        with connect_db() as conn:
            complaint = conn.execute(
                "SELECT * FROM complaints WHERE id = ?",
                (search_id,),
            ).fetchone()
            if complaint:
                notifications = conn.execute(
                    "SELECT * FROM notifications WHERE complaint_id = ? ORDER BY id DESC LIMIT 30",
                    (search_id,),
                ).fetchall()
                # Mark only this complaint's notifications as read after viewing them.
                conn.execute(
                    "UPDATE notifications SET is_read = 1 WHERE complaint_id = ?",
                    (search_id,),
                )

    return render_page(
        "track",
        complaint=complaint,
        search_id=search_id,
        notifications=notifications,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for(
                "admin", message="Login successful."
            ))

        return render_page(
            "login", error="Incorrect username or password."
        ), 401

    return render_page("login")



@app.route("/admin")
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    # Read and validate filters. Empty values mean "all" for that field.
    search_text = request.args.get("q", "").strip()[:200]
    filter_category = request.args.get("category", "").strip()
    filter_status = request.args.get("status", "").strip()
    filter_priority = request.args.get("priority", "").strip()

    if filter_category not in CATEGORIES:
        filter_category = ""
    if filter_status not in STATUSES:
        filter_status = ""
    if filter_priority not in PRIORITIES:
        filter_priority = ""

    where_parts = []
    params = []
    if search_text:
        search_pattern = f"%{search_text}%"
        # Cast ID to text so users can search by a complaint number too.
        where_parts.append(
            "(CAST(id AS TEXT) LIKE ? OR name LIKE ? OR location LIKE ? OR description LIKE ?)"
        )
        params.extend([search_pattern] * 4)
    if filter_category:
        where_parts.append("category = ?")
        params.append(filter_category)
    if filter_status:
        where_parts.append("status = ?")
        params.append(filter_status)
    if filter_priority:
        where_parts.append("priority = ?")
        params.append(filter_priority)

    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    with connect_db() as conn:
        # Only the table query is filtered; summary cards remain global.
        complaints = conn.execute(
            "SELECT * FROM complaints" + where_sql + " ORDER BY id DESC",
            params,
        ).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) FROM complaints"
        ).fetchone()[0]

        pending = conn.execute(
            "SELECT COUNT(*) FROM complaints WHERE status = ?",
            ("Pending",)
        ).fetchone()[0]

        in_progress = conn.execute(
            "SELECT COUNT(*) FROM complaints WHERE status = ?",
            ("In Progress",)
        ).fetchone()[0]

        resolved = conn.execute(
            "SELECT COUNT(*) FROM complaints WHERE status = ?",
            ("Resolved",)
        ).fetchone()[0]

        chart_status_rows = conn.execute(
            "SELECT status, COUNT(*) AS amount FROM complaints GROUP BY status"
        ).fetchall()
        chart_category_rows = conn.execute(
            "SELECT category, COUNT(*) AS amount FROM complaints GROUP BY category ORDER BY amount DESC, category"
        ).fetchall()
        priority_alerts = conn.execute(
            """SELECT id, category, location, description, status, priority, created_at
               FROM complaints
               WHERE status != 'Resolved'
                 AND (
                     priority = 'High'
                     OR datetime(created_at) <= datetime('now', '-3 days')
                 )
               ORDER BY CASE WHEN priority = 'High' THEN 0 ELSE 1 END,
                        datetime(created_at) ASC
               LIMIT 20"""
        ).fetchall()

    chart_status_labels = [row["status"] for row in chart_status_rows]
    chart_status_values = [row["amount"] for row in chart_status_rows]
    chart_category_labels = [row["category"] for row in chart_category_rows]
    chart_category_values = [row["amount"] for row in chart_category_rows]

    return render_page(
        "admin",
        complaints=complaints,
        total=total,
        pending=pending,
        in_progress=in_progress,
        resolved=resolved,
        search_text=search_text,
        filter_category=filter_category,
        filter_status=filter_status,
        filter_priority=filter_priority,
        chart_status_labels=chart_status_labels,
        chart_status_values=chart_status_values,
        chart_category_labels=chart_category_labels,
        chart_category_values=chart_category_values,
        priority_alerts=priority_alerts,
    )

@app.route("/admin/update/<int:complaint_id>", methods=["POST"])
def update_complaint(complaint_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    status = request.form.get("status", "")
    priority = request.form.get("priority", "")

    if status not in STATUSES or priority not in PRIORITIES:
        return redirect(url_for(
            "admin", message="Invalid status or priority."
        ))

    with connect_db() as conn:
        existing = conn.execute(
            "SELECT status, priority FROM complaints WHERE id = ?",
            (complaint_id,),
        ).fetchone()
        if existing is None:
            return redirect(url_for("admin", message="Complaint not found."))

        old_status = existing["status"]
        conn.execute(
            "UPDATE complaints SET status = ?, priority = ? WHERE id = ?",
            (status, priority, complaint_id),
        )

        # Notify the citizen only when the status actually changes.
        if old_status != status:
            notification_message = (
                f"Your complaint #{complaint_id} status changed from "
                f"{old_status} to {status}."
            )
            conn.execute(
                """INSERT INTO notifications
                   (complaint_id, message, old_status, new_status)
                   VALUES (?, ?, ?, ?)""",
                (complaint_id, notification_message, old_status, status),
            )

    return redirect(url_for(
        "admin", message=(
            f"Complaint #{complaint_id} updated. "
            + ("A status notification was created for the citizen." if old_status != status
               else "Status was unchanged, so no new notification was created.")
        )
    ))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home", message="You have logged out."))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)