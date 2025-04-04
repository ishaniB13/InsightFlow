# Use an official Python image as the base image
FROM python:3.8-slim

# Update the package list and install PHP CLI
RUN apt-get update && \
    apt-get install -y php-cli

# Set the working directory to /app in the container
WORKDIR /app

# Copy all application files from your local machine to the /app folder in the container
COPY . /app

# Install the Python dependencies from requirements.txt
RUN pip install -r requirements.txt

# Set the command to start the Flask app with Gunicorn
CMD ["gunicorn", "wsgi:app"]
