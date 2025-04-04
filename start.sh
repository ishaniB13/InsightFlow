#!/bin/bash

# Update package list and install PHP using sudo
echo "Updating package list..."
sudo apt-get update -y

echo "Installing PHP..."
sudo apt-get install -y php-cli

# Check if PHP was installed successfully
echo "Checking PHP installation..."
php -v  # Prints PHP version to confirm installation
which php  # Prints the PHP path

# Check PHP installation success
if ! command -v php &> /dev/null
then
    echo "PHP could not be installed."
    exit 1
else
    echo "PHP installed successfully."
fi

# Start the Flask application with Gunicorn
echo "Starting Flask application with Gunicorn..."
gunicorn wsgi:app
