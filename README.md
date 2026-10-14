# SmartLocality
Smart Locality Issue Reporting and Monitoring System
# SmartLocality — Smart Locality Issue Reporting and Monitoring System

## Project Overview

SmartLocality is a web-based application designed to help citizens report local issues and help administrators monitor and manage reported complaints in one place.

The project aims to improve communication between citizens and local administrators by providing a centralized system for complaint reporting and status tracking.

## Objectives

- Provide a convenient way to report local issues.
- Help administrators review and manage complaints.
- Improve visibility into complaint status and priority.
- Support more organized monitoring of locality-related issues.

## Technologies Used

- **Python** — application programming
- **Flask** — web application framework
- **SQLite** — database
- **HTML, CSS and JavaScript** — web interface

## Main Application

The main application source code is available in [`app.py`](app.py).

## Project Repository

GitHub: https://github.com/MOKSHITH122/SmartLocality



## Running the Project

### Prerequisites
- Python 3.10 or newer
- pip (Python package installer)

### Setup Instructions

1. Clone or download this repository.
2. Open a terminal in the project folder.
3. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

4. Activate the environment.

   **Windows:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS/Linux:**
   ```bash
   source .venv/bin/activate
   ```

5. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

6. Start the application:

   ```bash
   python app.py
   ```

7. Open the local address printed in the terminal in your web browser.

### Notes
- The SQLite database and uploaded complaint images are stored locally and should not be committed to the public repository.
- Some features may require an internet connection.
- Follow any additional configuration required by the application.

## Privacy and Data

The local complaint database and uploaded complaint images are not intended to be shared in this public repository. Do not commit real citizen information, passwords, secret keys, or private configuration files.

## Future Enhancements

- Android application for citizens.
- Improved complaint tracking and notifications.
- Enhanced analytics and locality monitoring.
- Further improvements to the user interface.

## Author

Developed as an internship project.
