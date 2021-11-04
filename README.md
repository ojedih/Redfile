https://redfile.me

# What is Redfile
Redfile is a user-friendly service to transfer any type of files between devices. That simple.

# How it works
After the user inputs a file and hits the "Upload" button, files go through an encryption algorythm which outputs encrypted bytes that are instantly uploaded to a Google Cloud Storage bucket. 

It then generates a code to access that file.

The user is then redirected to the page where they can either copy a URL or scan a QR to access the file from any device with a web browser installed.

Once the file is downloaded, it gets instantly deleted from Google Cloud Storage alongside with its database instance. No trace of information regarding that file is left behind.

# Technology
- Backend: Python (Flask framework)
- Frontend: HTML, CSS, JS (with AJAX)
- Database: MySQL (SQLAlchemy)
- Web Server: Google App Engines
