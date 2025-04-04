# InsightFlow

InsightFlow is a research automation tool designed to fetch, summarize, and organize academic papers. This guide provides a step-by-step process for setting up the project on your local machine.

## Local Setup and Execution

Follow these steps to install dependencies, configure API keys, set up Firebase, and run the application.

## Prerequisites

Ensure your system has the following installed:

- **Python 3.x** - [Download here](https://www.python.org/downloads/)
- **pip (Python Package Installer)** - [Installation guide](https://pip.pypa.io/en/stable/installation/)
- **Git** - [Download here](https://git-scm.com/downloads)
- **VSCode or any other IDE** - [Download here](https://code.visualstudio.com/download)

### Optional: Using Anaconda for Environment Management

Anaconda helps manage Python environments and dependencies.

#### Installation and Setup

1. **Download & Install Anaconda** - [Download here](https://www.anaconda.com/download/)
2. Add the following paths to the system path:
   ```sh
   path/to/anaconda3/Library/bin/
   path/to/anaconda3/Scripts/
   ```
3. Verify installation:
   ```sh
   conda --version
   ```

#### Creating and Activating Environment

**Via Anaconda Navigator**
1. Open Anaconda Navigator → Environments → Create
2. Name the environment (e.g., `InsightFlow`)
3. Select Python 3.x → Click Create

**Via Terminal**
```sh
conda create --name insightflow
conda activate insightflow
```

#### Installing Packages
```sh
conda install packagename
# or
pip install packagename
```

To deactivate the environment:
```sh
conda deactivate
```

## Cloning the Repository

#### Using Git (Recommended)
```sh
cd path/to/your/folder
git clone https://github.com/ishaniB13/Web-Scraper.git
cd Web-Scraper
```

#### Downloading ZIP File
1. Go to [GitHub Repository](https://github.com/ishaniB13/Web-Scraper)
2. Click **Code** → Download ZIP
3. Extract and open in VSCode

## Installing Dependencies
```sh
pip install -r requirements.txt
```

## Configuring API Keys
Replace `"Enter your API"` in `app.py` with your API keys.

### Springer API Key
1. Sign up at [Springer API](https://dev.springernature.com/)
2. Generate an API key and replace it in `app.py`

### OpenAI API Key
1. Sign up at [OpenAI](https://platform.openai.com/signup/)
2. Navigate to API keys → Generate a new key
3. Replace it in `app.py`

## Setting Up Firebase

1. Create a Firebase project: [Firebase Console](https://console.firebase.google.com/)
2. **Project Settings** → Service Accounts → Generate private key (`firebase_key.json`)
3. Place `firebase_key.json` in the project root folder.
4. Copy and replace `"FIREBASE_DB_URL"` in `app.py` with your Firebase database URL.

## Automating Newsletter Scheduling with GitHub Actions

1. Upload repository to GitHub.
2. Configure GitHub Secrets:
   - **Firebase_Key**: Service Account Key
   - **Firebase_DB_URL**: Firebase Realtime Database URL
   - **firebase_key_base64**: Base64-encoded `firebase_key.json`

### Generating Base64-encoded Firebase Key
```sh
base64 firebase_key.json > firebase_key_base64.txt
```
Copy the content of `firebase_key_base64.txt` and add it to GitHub Secrets.

## Configuring Email for Newsletter Delivery

By default, newsletters are sent from `universitatsiegenishanithesis@gmail.com`. You can configure a different email.

### Generating a Gmail App Password
1. Go to [Google Account Security](https://myaccount.google.com/)
2. Navigate to **Security** → **App Passwords**
3. Generate an App Password for "InsightFlow"
4. Add it to `.env`:
   ```sh
   EMAIL_PASSWORD=your_generated_app_password
   ```

## Running the Application
```sh
python app.py
```

The app will be accessible at:
[http://127.0.0.1:5000/](http://127.0.0.1:5000/) 


This link will be shown in your terminal after running app.py. Since the link may change, it is recommended to use the one displayed in your terminal after running the file.
