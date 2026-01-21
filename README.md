# Excalidraw UI

This application provides a web-based interface for Excalidraw.

## Technology Stack

*   **Backend**: Python (Flask)
*   **Database**: SQLite
*   **Frontend**: HTML, JavaScript, React (for Excalidraw component)
*   **Containerization**: Docker

## Data Storage & Architecture

The application uses **SQLite** for data persistence.

*   **Schema-Agnostic Design**: The database models (`Excalidraw` and `Instance`) utilize a `JSON` column (`data`) to store the majority of their attributes. This allows for a flexible, schema-less approach where new fields can be added without migration headaches, ensuring forward and backward compatibility.
*   **File Storage**: Excalidraw drawings and metadata are stored within the `data/` directory.

## Syncing & Collaboration

This application supports a **"Pull-based" synchronization** mechanism to share data between instances:

1.  **Add Instances**: You can register other running instances of this application (Nodes) by their URL.
2.  **Pull Data**: You can initiate a "Pull" from a registered remote instance.
    *   This process downloads a full export (Zip archive) of the remote instance's data.
    *   It **replaces** the local data with the remote data, effectively syncing the state.
    *   **Note**: This is a destructive sync (it overwrites local data with the remote state), useful for keeping mirrors up to date.

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
