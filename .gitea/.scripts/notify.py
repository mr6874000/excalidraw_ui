import requests
import sys

def send_gotify_notification(branch_name, job_status, repo_name):
    """
    Sends a notification to Gotify based on the job status.

    :param branch_name: The name of the branch where the job is running.
    :param job_status: The status of the pipeline job (success or failure).
    :param repo_name: The name of the repository.
    """
    GOTIFY_URL = "https://push.1tushar.com/message"
    GOTIFY_TOKEN = "AHC9J5trW9UxbeG"  # Replace with your token

    # Construct message based on job status
    if job_status.lower() == "success":
        title = f"✅ {repo_name} pipeline success"
        message = (
            f"{repo_name} - on branch {branch_name} was successful!"
        )
    else:
        title = f"❌ {repo_name} pipeline failure"
        message = (
            f"{repo_name} - on branch {branch_name} failed!"
        )

    # Prepare payload
    payload = {
        "title": title,
        "message": message,
        "priority": 5
    }

    # Send the POST request to Gotify
    try:
        response = requests.post(
            GOTIFY_URL,
            json=payload,
            headers={"Authorization": f"Bearer {GOTIFY_TOKEN}"}
        )
        if response.status_code == 200:
            print("Notification sent successfully.")
        else:
            print(f"Failed to send notification. Status code: {response.status_code}, Response: {response.text}")
    except requests.RequestException as e:
        print(f"An error occurred while sending the notification: {e}")

# Example usage
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 notify.py <branch_name> <job_status> <repo_name>")
        sys.exit(1)

    branch_name = sys.argv[1]
    job_status = sys.argv[2]
    repo_name = sys.argv[3]

    send_gotify_notification(branch_name, job_status, repo_name)
