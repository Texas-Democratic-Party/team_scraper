FROM selenium/standalone-chrome:latest

# Tip from https://stackoverflow.com/a/78936680/1870832 regarding this particular base image
ENV SE_OFFLINE=false

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy your application files
COPY . .

# Install Python and pip
USER root
RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

# Create a virtual environment
RUN python3 -m venv /usr/src/app/venv

# Activate the virtual environment and install dependencies
RUN . /usr/src/app/venv/bin/activate && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create directory for downloads with appropriate permissions
RUN mkdir -p /usr/src/app/downloaded_files && \
    chmod 777 /usr/src/app/downloaded_files

# Keep running as root since we need write permissions for file operations
# (os.remove, CSV downloads, etc.)

# Set the entrypoint to activate the venv and run your script
# Uses tx_election_scraper_all_dates.py as the main script
CMD ["/bin/bash", "-c", "source /usr/src/app/venv/bin/activate && python tx_election_scraper_all_dates.py --upload-to-gbq"]
