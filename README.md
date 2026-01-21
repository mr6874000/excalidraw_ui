# Excalidraw UI

This application provides a web-based interface for Excalidraw.

## Running Locally (Python)

To run the application directly on your host machine using Python:

1.  **Clone the repository**:
    
    ```bash
    git clone git@github.com:mr6874000/excalidraw_ui.git
    cd excalidraw_ui
    ```

2.  **Install dependencies**:
    
    Ensure you have Python 3 and pip installed.
    
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application**:
    
    ```bash
    python3 app.py
    ```

4.  **Access the application**:
    
    Open your web browser and navigate to: http://localhost:5000

## Running with Docker

To run the application using a Docker container:

1.  **Pull the image**:

    ```bash
    docker pull ghcr.io/mr6874000/excalidraw_ui:latest
    ```

2.  **Run the container**:

    ```bash
    docker run -d -p 5000:5000 --name excalidraw-ui ghcr.io/mr6874000/excalidraw_ui:latest
    ```

3.  **Access the application**:
    
    Open your web browser and navigate to: http://localhost:5000

## Running with Docker Compose

To run the application using Docker Compose, create a `docker-compose.yaml` file with the following content:

```yaml
services:
  excalidraw:
    image: ghcr.io/mr6874000/excalidraw_ui:latest
    ports:
      - "5000:5000"
    restart: unless-stopped
    volumes:
      - ./data:/app/data
```

Start the service:

```bash
docker-compose up -d
```
